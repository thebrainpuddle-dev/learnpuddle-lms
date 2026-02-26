"""
Webhook endpoints for external service integrations (Cal.com, etc.).
These endpoints are public (no JWT auth) but verified via shared secrets.
"""

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


def _verify_cal_signature(payload_body: bytes, signature: str) -> bool:
    secret = getattr(settings, "CAL_WEBHOOK_SECRET", "")
    if not secret:
        return False
    expected = hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def cal_webhook(request):
    """
    Receive Cal.com webhook events for demo bookings.
    Handles: BOOKING_CREATED, BOOKING_CANCELLED, BOOKING_RESCHEDULED
    """
    cal_secret = getattr(settings, "CAL_WEBHOOK_SECRET", "")
    if cal_secret:
        signature = request.headers.get("X-Cal-Signature-256", "")
        if not _verify_cal_signature(request.body, signature):
            logger.warning("cal_webhook: invalid signature")
            return Response({"error": "Invalid signature"}, status=status.HTTP_403_FORBIDDEN)

    try:
        payload = request.data if isinstance(request.data, dict) else json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return Response({"error": "Invalid JSON"}, status=status.HTTP_400_BAD_REQUEST)

    trigger_event = payload.get("triggerEvent", "")
    booking_payload = payload.get("payload", {})

    logger.info("cal_webhook: event=%s", trigger_event)

    if trigger_event == "BOOKING_CREATED":
        return _handle_booking_created(booking_payload)
    elif trigger_event == "BOOKING_CANCELLED":
        return _handle_booking_cancelled(booking_payload)
    elif trigger_event == "BOOKING_RESCHEDULED":
        return _handle_booking_rescheduled(booking_payload)
    else:
        logger.info("cal_webhook: ignoring event=%s", trigger_event)
        return Response({"ok": True, "ignored": True})


def _extract_attendee(payload: dict) -> dict:
    """Extract primary attendee info from Cal.com booking payload."""
    attendees = payload.get("attendees", [])
    if attendees:
        a = attendees[0]
        return {
            "name": a.get("name", ""),
            "email": a.get("email", ""),
        }
    responses = payload.get("responses", {})
    return {
        "name": responses.get("name", {}).get("value", "") if isinstance(responses.get("name"), dict) else responses.get("name", ""),
        "email": responses.get("email", {}).get("value", "") if isinstance(responses.get("email"), dict) else responses.get("email", ""),
    }


def _handle_booking_created(payload: dict):
    from apps.tenants.models import DemoBooking

    cal_uid = str(payload.get("uid", "") or payload.get("id", ""))
    attendee = _extract_attendee(payload)
    name = attendee["name"] or "Unknown"
    email = attendee["email"] or ""
    start_time = payload.get("startTime") or payload.get("start_time", "")
    scheduled_at = parse_datetime(str(start_time)) if start_time else None

    if not email:
        logger.warning("cal_webhook: BOOKING_CREATED missing email, uid=%s", cal_uid)
        return Response({"error": "Missing attendee email"}, status=status.HTTP_400_BAD_REQUEST)

    if cal_uid and DemoBooking.objects.filter(cal_event_id=cal_uid).exists():
        logger.info("cal_webhook: duplicate booking uid=%s", cal_uid)
        return Response({"ok": True, "duplicate": True})

    responses = payload.get("responses", {})
    company = ""
    if isinstance(responses.get("company"), dict):
        company = responses["company"].get("value", "")
    elif isinstance(responses.get("company"), str):
        company = responses["company"]

    phone = ""
    if isinstance(responses.get("phone"), dict):
        phone = responses["phone"].get("value", "")
    elif isinstance(responses.get("phone"), str):
        phone = responses["phone"]

    booking = DemoBooking.objects.create(
        name=name,
        email=email,
        company=company,
        phone=phone,
        source="cal_webhook",
        cal_event_id=cal_uid,
        scheduled_at=scheduled_at,
        notes=payload.get("description", "") or "",
        status="scheduled",
    )

    from apps.notifications.tasks import send_demo_followup_email
    send_demo_followup_email.delay(str(booking.id))

    logger.info("cal_webhook: booking created id=%s email=%s", booking.id, email)
    return Response({"ok": True, "booking_id": str(booking.id)}, status=status.HTTP_201_CREATED)


def _handle_booking_cancelled(payload: dict):
    from apps.tenants.models import DemoBooking

    cal_uid = str(payload.get("uid", "") or payload.get("id", ""))
    if not cal_uid:
        return Response({"ok": True, "ignored": True})

    updated = DemoBooking.objects.filter(cal_event_id=cal_uid).update(status="cancelled")
    logger.info("cal_webhook: booking cancelled uid=%s updated=%d", cal_uid, updated)
    return Response({"ok": True, "updated": updated})


def _handle_booking_rescheduled(payload: dict):
    from apps.tenants.models import DemoBooking

    cal_uid = str(payload.get("uid", "") or payload.get("id", ""))
    new_start = payload.get("startTime") or payload.get("start_time", "")
    new_scheduled = parse_datetime(str(new_start)) if new_start else None

    if not cal_uid:
        return Response({"ok": True, "ignored": True})

    updates = {"status": "scheduled"}
    if new_scheduled:
        updates["scheduled_at"] = new_scheduled

    updated = DemoBooking.objects.filter(cal_event_id=cal_uid).update(**updates)
    logger.info("cal_webhook: booking rescheduled uid=%s updated=%d", cal_uid, updated)
    return Response({"ok": True, "updated": updated})
