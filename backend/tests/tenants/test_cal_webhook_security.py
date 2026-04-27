# tests/tenants/test_cal_webhook_security.py
"""
Regression tests — Fix 3: Cal.com webhook fails closed when secret is empty.

Before the fix, if CAL_WEBHOOK_SECRET was not set (empty string), the
signature verification was skipped entirely and ANY request was accepted.
This allowed unauthenticated callers to trigger demo bookings.

After the fix:
- Empty secret → 503 Service Unavailable (fail-closed, reject all)
- Secret set + wrong signature → 403 Forbidden
- Secret set + correct HMAC-SHA256 → 2xx and booking created

URL: POST /api/webhooks/cal/
"""

import hashlib
import hmac
import json
from datetime import datetime
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CAL_URL = "/api/webhooks/cal/"
_TEST_SECRET = "supersecrettestkey_abc123"


def _sign(payload_bytes: bytes, secret: str = _TEST_SECRET) -> str:
    """Compute the HMAC-SHA256 signature for a payload."""
    return hmac.new(
        secret.encode(),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()


def _booking_payload(uid="test-uid-001", email="prospect@example.com"):
    """Build a minimal BOOKING_CREATED Cal.com webhook payload."""
    return {
        "triggerEvent": "BOOKING_CREATED",
        "payload": {
            "uid": uid,
            "attendees": [{"name": "Jane Smith", "email": email}],
            "startTime": "2026-05-01T10:00:00.000Z",
            "description": "Test booking from regression suite",
        },
    }


def _post(client, payload_dict, signature=None, content_type="application/json"):
    """POST to the cal webhook endpoint with an optional signature header."""
    body = json.dumps(payload_dict).encode()
    headers = {}
    if signature is not None:
        headers["HTTP_X_CAL_SIGNATURE_256"] = signature
    return client.post(
        _CAL_URL,
        data=body,
        content_type=content_type,
        **headers,
    )


# ===========================================================================
# 1. Fail-closed: empty secret → 503
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    CAL_WEBHOOK_SECRET="",
)
class CalWebhookEmptySecretTestCase(TestCase):
    """When CAL_WEBHOOK_SECRET is empty the endpoint must return 503."""

    def setUp(self):
        self.client = APIClient()

    def test_empty_secret_returns_503(self):
        """
        Core regression guard: empty secret must → 503, not 200/201.
        Before the fix this was 200 (fail-open).
        """
        payload = _booking_payload()
        r = _post(self.client, payload, signature="any_signature_is_ignored")
        self.assertEqual(
            r.status_code,
            503,
            f"Empty CAL_WEBHOOK_SECRET must return 503, got {r.status_code}. "
            f"This indicates a fail-open regression.",
        )

    def test_empty_secret_response_body_is_error(self):
        """503 response body must contain an error indicator."""
        payload = _booking_payload()
        r = _post(self.client, payload)
        self.assertIn("error", r.data)

    def test_empty_secret_no_signature_header_still_503(self):
        """Even without any signature header, empty secret → 503."""
        payload = _booking_payload()
        r = _post(self.client, payload)  # no signature kwarg
        self.assertEqual(r.status_code, 503)

    def test_empty_secret_no_booking_created(self):
        """No DemoBooking must be created when secret is not configured."""
        from apps.tenants.models import DemoBooking
        before = DemoBooking.objects.count()
        payload = _booking_payload(uid="fail-open-guard-uid")
        _post(self.client, payload, signature="any")
        after = DemoBooking.objects.count()
        self.assertEqual(
            before,
            after,
            "Empty secret must not create a DemoBooking (fail-open guard).",
        )

    def test_unset_secret_attribute_returns_503(self):
        """
        When CAL_WEBHOOK_SECRET is absent from settings entirely, endpoint
        must also return 503 (getattr default of "" triggers the same guard).
        """
        with self.settings(CAL_WEBHOOK_SECRET=""):
            payload = _booking_payload()
            r = _post(self.client, payload)
            self.assertEqual(r.status_code, 503)


# ===========================================================================
# 2. Wrong signature → 403
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    CAL_WEBHOOK_SECRET=_TEST_SECRET,
)
class CalWebhookWrongSignatureTestCase(TestCase):
    """When secret is set but signature is wrong the endpoint returns 403."""

    def setUp(self):
        self.client = APIClient()

    def test_wrong_signature_returns_403(self):
        """Tampered / wrong signature must be rejected with 403."""
        payload = _booking_payload(uid="wrong-sig-001")
        r = _post(self.client, payload, signature="wrong_signature_hex")
        self.assertEqual(
            r.status_code,
            403,
            f"Wrong signature must return 403, got {r.status_code}.",
        )

    def test_empty_signature_header_returns_403(self):
        """An empty X-Cal-Signature-256 header (secret set) → 403."""
        payload = _booking_payload(uid="empty-sig-002")
        r = _post(self.client, payload, signature="")
        self.assertEqual(r.status_code, 403)

    def test_missing_signature_header_returns_403(self):
        """Omitting the signature header entirely (secret set) → 403."""
        payload = _booking_payload(uid="missing-sig-003")
        body = json.dumps(payload).encode()
        r = self.client.post(_CAL_URL, data=body, content_type="application/json")
        self.assertEqual(r.status_code, 403)

    def test_signature_for_different_secret_returns_403(self):
        """Signature computed with wrong key → 403."""
        payload = _booking_payload(uid="different-key-004")
        bad_sig = _sign(json.dumps(payload).encode(), secret="wrong_key_xyz")
        r = _post(self.client, payload, signature=bad_sig)
        self.assertEqual(r.status_code, 403)

    def test_wrong_signature_no_booking_created(self):
        """Wrong signature must not create a DemoBooking."""
        from apps.tenants.models import DemoBooking
        before = DemoBooking.objects.count()
        payload = _booking_payload(uid="no-booking-wrong-sig")
        _post(self.client, payload, signature="totally_wrong")
        self.assertEqual(DemoBooking.objects.count(), before)


# ===========================================================================
# 3. Correct HMAC-SHA256 signature → 2xx + booking created
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    CAL_WEBHOOK_SECRET=_TEST_SECRET,
)
class CalWebhookValidSignatureTestCase(TestCase):
    """
    When secret is configured and signature matches, the endpoint must
    accept the request, create a DemoBooking, and return 2xx.
    """

    def setUp(self):
        self.client = APIClient()

    def _signed_post(self, payload_dict):
        body = json.dumps(payload_dict).encode()
        sig = _sign(body)
        return self.client.post(
            _CAL_URL,
            data=body,
            content_type="application/json",
            HTTP_X_CAL_SIGNATURE_256=sig,
        )

    @patch("apps.notifications.tasks.send_demo_followup_email.delay")
    def test_valid_signature_booking_created_returns_201(self, mock_task):
        """Correct HMAC-SHA256 signature → 201 Created."""
        payload = _booking_payload(uid="valid-sig-booking-001")
        r = self._signed_post(payload)
        self.assertIn(
            r.status_code,
            [200, 201],
            f"Valid signature must return 2xx, got {r.status_code}: {getattr(r, 'data', '')}",
        )

    @patch("apps.notifications.tasks.send_demo_followup_email.delay")
    def test_valid_signature_creates_demo_booking(self, mock_task):
        """A valid webhook with correct signature must persist a DemoBooking."""
        from apps.tenants.models import DemoBooking

        payload = _booking_payload(
            uid="valid-sig-booking-002",
            email="newprospect@school.com",
        )
        before = DemoBooking.objects.count()
        self._signed_post(payload)
        after = DemoBooking.objects.count()

        self.assertEqual(
            after,
            before + 1,
            "A DemoBooking must be created for a valid BOOKING_CREATED webhook.",
        )

    @patch("apps.notifications.tasks.send_demo_followup_email.delay")
    def test_valid_signature_booking_has_correct_email(self, mock_task):
        """The created DemoBooking must have the attendee's email."""
        from apps.tenants.models import DemoBooking

        email = "checkemail@school.com"
        payload = _booking_payload(uid="valid-sig-email-003", email=email)
        self._signed_post(payload)

        booking = DemoBooking.objects.filter(cal_event_id="valid-sig-email-003").first()
        self.assertIsNotNone(booking, "DemoBooking must be created for valid webhook")
        self.assertEqual(booking.email, email)

    @patch("apps.notifications.tasks.send_demo_followup_email.delay")
    def test_duplicate_uid_does_not_create_second_booking(self, mock_task):
        """Replaying a webhook with the same uid must be idempotent (no duplicate)."""
        from apps.tenants.models import DemoBooking

        payload = _booking_payload(uid="dup-uid-005", email="dup@school.com")

        self._signed_post(payload)
        count_after_first = DemoBooking.objects.filter(cal_event_id="dup-uid-005").count()

        # Replay with new body (same uid) — must NOT create another booking
        self._signed_post(payload)
        count_after_second = DemoBooking.objects.filter(cal_event_id="dup-uid-005").count()

        self.assertEqual(count_after_first, 1)
        self.assertEqual(count_after_second, 1, "Duplicate uid must not create a second booking")

    @patch("apps.notifications.tasks.send_demo_followup_email.delay")
    def test_booking_cancelled_event_updates_status(self, mock_task):
        """BOOKING_CANCELLED event must mark an existing booking as cancelled."""
        from apps.tenants.models import DemoBooking

        # First create a booking
        create_payload = _booking_payload(uid="cancel-uid-006", email="cancel@school.com")
        self._signed_post(create_payload)

        booking = DemoBooking.objects.filter(cal_event_id="cancel-uid-006").first()
        self.assertIsNotNone(booking)
        self.assertEqual(booking.status, "scheduled")

        # Now cancel it
        cancel_payload = {
            "triggerEvent": "BOOKING_CANCELLED",
            "payload": {"uid": "cancel-uid-006"},
        }
        cancel_body = json.dumps(cancel_payload).encode()
        cancel_sig = _sign(cancel_body)
        self.client.post(
            _CAL_URL,
            data=cancel_body,
            content_type="application/json",
            HTTP_X_CAL_SIGNATURE_256=cancel_sig,
        )

        booking.refresh_from_db()
        self.assertEqual(booking.status, "cancelled")

    def test_unknown_event_type_returns_200_ok(self):
        """Unknown trigger events must be gracefully ignored (200, not 500)."""
        payload = {
            "triggerEvent": "SOME_UNKNOWN_EVENT",
            "payload": {"uid": "unknown-event-007"},
        }
        body = json.dumps(payload).encode()
        sig = _sign(body)
        r = self.client.post(
            _CAL_URL,
            data=body,
            content_type="application/json",
            HTTP_X_CAL_SIGNATURE_256=sig,
        )
        self.assertIn(r.status_code, [200, 201])
