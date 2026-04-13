import logging
from datetime import datetime, timezone as dt_tz

from django.utils import timezone

logger = logging.getLogger(__name__)


def _record_event(event_id, event_type, summary=None):
    """Record that we processed this event (idempotency)."""
    from .models import StripeWebhookEvent
    StripeWebhookEvent.objects.get_or_create(
        stripe_event_id=event_id,
        defaults={'event_type': event_type, 'payload_summary': summary or {}},
    )


def _already_processed(event_id) -> bool:
    """Check if we already processed this event."""
    from .models import StripeWebhookEvent
    return StripeWebhookEvent.objects.filter(stripe_event_id=event_id).exists()


def _ts_to_dt(ts):
    """Convert Unix timestamp to timezone-aware datetime."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=dt_tz.utc)


def handle_checkout_session_completed(event):
    """
    Customer completed Stripe Checkout.
    - Create/update TenantSubscription
    - Apply plan preset to tenant
    - Set tenant.is_trial = False
    """
    if _already_processed(event.id):
        return

    session = event.data.object
    tenant_id = session.metadata.get('tenant_id')
    plan_code = session.metadata.get('plan_code')

    if not tenant_id or not plan_code:
        logger.warning("checkout.session.completed missing metadata: %s", event.id)
        _record_event(event.id, event.type, {'error': 'missing metadata'})
        return

    from apps.tenants.models import Tenant
    from apps.tenants.services import apply_plan_preset
    from .models import SubscriptionPlan, TenantSubscription

    try:
        tenant = Tenant.objects.get(id=tenant_id)
    except Tenant.DoesNotExist:
        logger.error("Tenant %s not found for checkout session %s", tenant_id, session.id)
        _record_event(event.id, event.type, {'error': f'tenant {tenant_id} not found'})
        return

    plan = SubscriptionPlan.objects.filter(plan_code=plan_code).first()
    if not plan:
        logger.error("Plan %s not found for checkout session %s", plan_code, session.id)
        _record_event(event.id, event.type, {'error': f'plan {plan_code} not found'})
        return

    # Update tenant
    tenant.stripe_customer_id = session.customer
    tenant.is_trial = False
    tenant.save(update_fields=['stripe_customer_id', 'is_trial', 'updated_at'])

    # Apply plan preset
    apply_plan_preset(tenant, plan_code)

    # Create/update subscription record
    stripe_sub_id = session.subscription
    if stripe_sub_id:
        TenantSubscription.objects.update_or_create(
            tenant=tenant,
            defaults={
                'plan': plan,
                'stripe_customer_id': session.customer,
                'stripe_subscription_id': stripe_sub_id,
                'status': 'active',
                'billing_interval': 'month',  # Will be updated by subscription.created/updated
            },
        )

    logger.info("Checkout completed: tenant=%s plan=%s", tenant_id, plan_code)
    _record_event(event.id, event.type, {'tenant_id': tenant_id, 'plan_code': plan_code})


def handle_subscription_created(event):
    """Subscription created -- sync details."""
    if _already_processed(event.id):
        return

    sub = event.data.object
    _sync_subscription(sub, event.id, event.type)


def handle_subscription_updated(event):
    """Subscription updated -- sync status, plan, period."""
    if _already_processed(event.id):
        return

    sub = event.data.object
    _sync_subscription(sub, event.id, event.type)


def handle_subscription_deleted(event):
    """Subscription canceled/deleted -- downgrade to FREE."""
    if _already_processed(event.id):
        return

    sub = event.data.object

    from .models import TenantSubscription

    try:
        ts = TenantSubscription.objects.get(stripe_subscription_id=sub.id)
    except TenantSubscription.DoesNotExist:
        logger.warning("No TenantSubscription for stripe sub %s", sub.id)
        _record_event(event.id, event.type, {'error': 'subscription not found'})
        return

    ts.status = 'canceled'
    ts.canceled_at = timezone.now()
    ts.save(update_fields=['status', 'canceled_at', 'updated_at'])

    # Downgrade to FREE
    from apps.tenants.services import apply_plan_preset
    apply_plan_preset(ts.tenant, 'FREE')

    logger.info("Subscription deleted: tenant=%s downgraded to FREE", ts.tenant_id)
    _record_event(event.id, event.type, {'tenant_id': str(ts.tenant_id), 'action': 'downgraded_to_free'})


def handle_invoice_paid(event):
    """Invoice paid -- record payment."""
    if _already_processed(event.id):
        return

    invoice = event.data.object

    from .models import PaymentHistory, TenantSubscription
    from apps.tenants.models import Tenant

    customer_id = invoice.customer
    tenant = Tenant.objects.filter(stripe_customer_id=customer_id).first()
    if not tenant:
        logger.warning("No tenant for customer %s on invoice %s", customer_id, invoice.id)
        _record_event(event.id, event.type, {'error': f'no tenant for customer {customer_id}'})
        return

    sub = TenantSubscription.objects.filter(tenant=tenant).first()

    PaymentHistory.objects.update_or_create(
        stripe_invoice_id=invoice.id,
        defaults={
            'tenant': tenant,
            'subscription': sub,
            'stripe_payment_intent_id': invoice.payment_intent or '',
            'stripe_charge_id': invoice.charge or '',
            'amount_cents': invoice.amount_paid,
            'currency': invoice.currency,
            'status': 'paid',
            'description': invoice.description or f'Invoice {invoice.number or invoice.id}',
            'invoice_url': invoice.hosted_invoice_url or '',
            'invoice_pdf_url': invoice.invoice_pdf or '',
            'period_start': _ts_to_dt(invoice.period_start),
            'period_end': _ts_to_dt(invoice.period_end),
        },
    )

    logger.info("Invoice paid: tenant=%s invoice=%s amount=%d",
                tenant.id, invoice.id, invoice.amount_paid)
    _record_event(event.id, event.type, {'tenant_id': str(tenant.id), 'amount': invoice.amount_paid})


def handle_invoice_payment_failed(event):
    """Invoice payment failed -- record and notify."""
    if _already_processed(event.id):
        return

    invoice = event.data.object

    from .models import PaymentHistory, TenantSubscription
    from apps.tenants.models import Tenant

    customer_id = invoice.customer
    tenant = Tenant.objects.filter(stripe_customer_id=customer_id).first()
    if not tenant:
        _record_event(event.id, event.type, {'error': f'no tenant for customer {customer_id}'})
        return

    sub = TenantSubscription.objects.filter(tenant=tenant).first()

    # Get failure reason from the charge
    failure_reason = ''
    if invoice.charge:
        try:
            from .stripe_service import _get_stripe
            s = _get_stripe()
            charge = s.Charge.retrieve(invoice.charge)
            failure_reason = getattr(charge, 'failure_message', '') or ''
            if not failure_reason and charge.outcome:
                failure_reason = getattr(charge.outcome, 'seller_message', '') or ''
        except Exception:
            logger.debug("Could not retrieve charge %s for failure reason", invoice.charge)

    PaymentHistory.objects.update_or_create(
        stripe_invoice_id=invoice.id,
        defaults={
            'tenant': tenant,
            'subscription': sub,
            'stripe_payment_intent_id': invoice.payment_intent or '',
            'stripe_charge_id': invoice.charge or '',
            'amount_cents': invoice.amount_due,
            'currency': invoice.currency,
            'status': 'failed',
            'description': f'Payment failed: Invoice {invoice.number or invoice.id}',
            'invoice_url': invoice.hosted_invoice_url or '',
            'invoice_pdf_url': invoice.invoice_pdf or '',
            'period_start': _ts_to_dt(invoice.period_start),
            'period_end': _ts_to_dt(invoice.period_end),
            'failure_reason': failure_reason,
        },
    )

    logger.error("Invoice payment failed: tenant=%s invoice=%s", tenant.id, invoice.id)
    _record_event(event.id, event.type, {'tenant_id': str(tenant.id), 'invoice': invoice.id})


def _sync_subscription(stripe_sub, event_id, event_type):
    """Shared logic for subscription.created and subscription.updated."""
    from django.db import models
    from .models import SubscriptionPlan, TenantSubscription
    from apps.tenants.models import Tenant
    from apps.tenants.services import apply_plan_preset

    tenant_id = stripe_sub.metadata.get('tenant_id')
    plan_code = stripe_sub.metadata.get('plan_code')
    customer_id = stripe_sub.customer

    # Find tenant
    tenant = None
    if tenant_id:
        tenant = Tenant.objects.filter(id=tenant_id).first()
    if not tenant:
        tenant = Tenant.objects.filter(stripe_customer_id=customer_id).first()
    if not tenant:
        logger.warning("Cannot find tenant for subscription %s", stripe_sub.id)
        _record_event(event_id, event_type, {'error': 'tenant not found'})
        return

    # Extract subscription items safely (Stripe objects support both attribute and dict access)
    try:
        items_data = stripe_sub['items']['data']
    except (KeyError, TypeError):
        items_data = []

    # Find plan
    plan = None
    if plan_code:
        plan = SubscriptionPlan.objects.filter(plan_code=plan_code).first()
    if not plan and items_data:
        # Try to match by Stripe price ID
        try:
            price_id = items_data[0]['price']['id']
        except (KeyError, TypeError, IndexError):
            price_id = ''
        if price_id:
            plan = SubscriptionPlan.objects.filter(
                models.Q(stripe_price_monthly_id=price_id) |
                models.Q(stripe_price_yearly_id=price_id)
            ).first()
    if not plan:
        logger.warning("Cannot find plan for subscription %s", stripe_sub.id)
        _record_event(event_id, event_type, {'error': 'plan not found'})
        return

    # Determine billing interval
    interval = 'month'
    if items_data:
        try:
            interval = items_data[0]['price']['recurring']['interval']
        except (KeyError, TypeError, IndexError):
            pass

    # Map Stripe status
    status = stripe_sub.status  # active, past_due, canceled, trialing, etc.

    # Create/update
    ts, created = TenantSubscription.objects.update_or_create(
        tenant=tenant,
        defaults={
            'plan': plan,
            'stripe_customer_id': customer_id,
            'stripe_subscription_id': stripe_sub.id,
            'status': status,
            'billing_interval': interval,
            'current_period_start': _ts_to_dt(stripe_sub.current_period_start),
            'current_period_end': _ts_to_dt(stripe_sub.current_period_end),
            'cancel_at_period_end': stripe_sub.cancel_at_period_end or False,
            'canceled_at': _ts_to_dt(stripe_sub.canceled_at),
            'trial_start': _ts_to_dt(stripe_sub.trial_start),
            'trial_end': _ts_to_dt(stripe_sub.trial_end),
        },
    )

    # Apply plan preset if plan changed
    if plan.plan_code != tenant.plan:
        try:
            apply_plan_preset(tenant, plan.plan_code)
        except ValueError:
            logger.error("Failed to apply plan preset %s for tenant %s", plan.plan_code, tenant.id)

    action = 'created' if created else 'updated'
    logger.info("Subscription %s: tenant=%s plan=%s status=%s", action, tenant.id, plan.plan_code, status)
    _record_event(event_id, event_type, {'tenant_id': str(tenant.id), 'plan': plan.plan_code, 'status': status})
