from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task(name='billing.check_past_due_subscriptions')
def check_past_due_subscriptions():
    """Daily: find subscriptions past_due for >7 days and send notifications."""
    from datetime import timedelta
    from django.utils import timezone
    from .models import TenantSubscription

    threshold = timezone.now() - timedelta(days=7)
    past_due = TenantSubscription.objects.filter(
        status='past_due',
        updated_at__lte=threshold,
    ).select_related('tenant', 'plan')

    count = 0
    for sub in past_due:
        logger.warning(
            "Subscription past_due >7 days: tenant=%s plan=%s since=%s",
            sub.tenant.name, sub.plan.name, sub.updated_at,
        )
        count += 1

    logger.info("Past-due check complete: %d subscriptions flagged", count)
    return count


@shared_task(name='billing.cleanup_stale_webhook_events')
def cleanup_stale_webhook_events():
    """Weekly: delete StripeWebhookEvent records older than 90 days."""
    from datetime import timedelta
    from django.utils import timezone
    from .models import StripeWebhookEvent

    cutoff = timezone.now() - timedelta(days=90)
    deleted, _ = StripeWebhookEvent.objects.filter(processed_at__lt=cutoff).delete()
    logger.info("Cleaned up %d stale webhook events", deleted)
    return deleted


@shared_task(name='billing.sync_subscription_status')
def sync_subscription_status(tenant_id: str):
    """Fallback: sync subscription status from Stripe for a specific tenant."""
    from apps.tenants.models import Tenant
    from .models import TenantSubscription

    try:
        tenant = Tenant.objects.get(id=tenant_id)
    except Tenant.DoesNotExist:
        logger.error("Tenant %s not found for sync", tenant_id)
        return

    sub = TenantSubscription.objects.filter(tenant=tenant).first()
    if not sub or not sub.stripe_subscription_id:
        logger.info("No subscription to sync for tenant %s", tenant_id)
        return

    import stripe
    from django.conf import settings
    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        stripe_sub = stripe.Subscription.retrieve(sub.stripe_subscription_id)
    except Exception:
        logger.exception("Failed to retrieve subscription %s from Stripe", sub.stripe_subscription_id)
        return

    # Build a mock event to reuse _sync_subscription
    from .webhook_handlers import _sync_subscription
    _sync_subscription(stripe_sub, f'manual_sync_{tenant_id}', 'manual_sync')
    logger.info("Synced subscription for tenant %s", tenant_id)
