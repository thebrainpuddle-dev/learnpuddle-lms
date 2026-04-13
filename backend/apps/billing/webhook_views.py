import logging

from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)

EVENT_HANDLERS = {
    "checkout.session.completed": "handle_checkout_session_completed",
    "customer.subscription.created": "handle_subscription_created",
    "customer.subscription.updated": "handle_subscription_updated",
    "customer.subscription.deleted": "handle_subscription_deleted",
    "invoice.paid": "handle_invoice_paid",
    "invoice.payment_failed": "handle_invoice_payment_failed",
}


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def stripe_webhook(request):
    """Receive and process Stripe webhook events."""
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    if not sig_header:
        return Response({"error": "Missing signature"}, status=status.HTTP_400_BAD_REQUEST)

    from .stripe_service import construct_webhook_event
    try:
        event = construct_webhook_event(payload, sig_header)
    except ValueError:
        logger.warning("Invalid webhook payload")
        return Response({"error": "Invalid payload"}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.warning("Webhook signature verification failed: %s", e)
        return Response({"error": "Invalid signature"}, status=status.HTTP_400_BAD_REQUEST)

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
