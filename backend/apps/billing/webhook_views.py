import logging

import stripe
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework.throttling import ScopedRateThrottle

logger = logging.getLogger(__name__)

EVENT_HANDLERS = {
    "checkout.session.completed": "handle_checkout_session_completed",
    "customer.subscription.created": "handle_subscription_created",
    "customer.subscription.updated": "handle_subscription_updated",
    "customer.subscription.deleted": "handle_subscription_deleted",
    "invoice.paid": "handle_invoice_paid",
    "invoice.payment_failed": "handle_invoice_payment_failed",
}


class StripeWebhookThrottle(ScopedRateThrottle):
    """Per-IP throttle for Stripe webhook ingestion.

    Signature verification is the primary defense against forged events, but
    without rate-limiting an attacker can spam invalid-signature requests to
    burn CPU on HMAC verification / fill logs. Scoped at `stripe_webhook`
    (see REST_FRAMEWORK.DEFAULT_THROTTLE_RATES in settings).
    """
    scope = 'stripe_webhook'


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([StripeWebhookThrottle])
def stripe_webhook(request):
    """Receive and process Stripe webhook events."""
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    if not sig_header:
        return Response({"error": "Missing signature"}, status=status.HTTP_400_BAD_REQUEST)

    from .stripe_service import construct_webhook_event
    try:
        event = construct_webhook_event(payload, sig_header)
    except ValueError as e:
        # Malformed JSON payload or missing STRIPE_WEBHOOK_SECRET config.
        # Return 400 so Stripe does NOT retry (the request itself is bad;
        # retrying will not help until the config is corrected).
        logger.warning("Stripe webhook payload error: %s", e)
        return Response({"error": "Invalid payload"}, status=status.HTTP_400_BAD_REQUEST)
    except stripe.error.SignatureVerificationError as e:
        # HMAC mismatch — tampered request or wrong secret.  401 surfaces in
        # Stripe's delivery dashboard as a clear auth failure (distinct from
        # application errors).
        logger.warning("Stripe webhook signature verification failed: %s", e)
        return Response({"error": "Invalid signature"}, status=status.HTTP_401_UNAUTHORIZED)
    except Exception as e:
        # Unexpected runtime error (e.g. network issue constructing the event).
        # Return 500 so Stripe's automatic delivery retry kicks in.
        logger.exception("Unexpected error constructing Stripe webhook event: %s", e)
        return Response({"error": "Internal error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    handler_name = EVENT_HANDLERS.get(event.type)
    if handler_name:
        from . import webhook_handlers
        handler = getattr(webhook_handlers, handler_name, None)
        if handler:
            try:
                handler(event)
            except Exception:
                logger.exception("Error processing webhook event %s (type=%s)", event.id, event.type)
                # Return 200 to prevent Stripe retries for application errors
                # The error is logged for investigation
    else:
        logger.debug("Unhandled webhook event type: %s", event.type)

    return Response({"received": True}, status=status.HTTP_200_OK)
