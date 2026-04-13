import logging

import stripe
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_stripe():
    """Configure and return stripe module."""
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def get_or_create_stripe_customer(tenant) -> str:
    """Get existing or create new Stripe Customer. Returns customer ID."""
    if tenant.stripe_customer_id:
        return tenant.stripe_customer_id

    s = _get_stripe()
    customer = s.Customer.create(
        name=tenant.name,
        metadata={
            'tenant_id': str(tenant.id),
            'subdomain': tenant.subdomain,
        },
    )
    tenant.stripe_customer_id = customer.id
    tenant.save(update_fields=['stripe_customer_id'])
    logger.info("Created Stripe customer %s for tenant %s", customer.id, tenant.id)
    return customer.id


def create_checkout_session(tenant, plan, interval, success_url, cancel_url) -> str:
    """Create Stripe Checkout Session. Returns session URL."""
    s = _get_stripe()
    customer_id = get_or_create_stripe_customer(tenant)

    price_id = plan.stripe_price_monthly_id if interval == 'month' else plan.stripe_price_yearly_id
    if not price_id:
        raise ValueError(f"No Stripe price ID configured for plan {plan.plan_code} interval {interval}")

    session = s.checkout.Session.create(
        customer=customer_id,
        mode='subscription',
        line_items=[{'price': price_id, 'quantity': 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            'tenant_id': str(tenant.id),
            'plan_code': plan.plan_code,
        },
        subscription_data={
            'metadata': {
                'tenant_id': str(tenant.id),
                'plan_code': plan.plan_code,
            },
        },
    )
    logger.info("Created checkout session %s for tenant %s plan %s", session.id, tenant.id, plan.plan_code)
    return session.url


def create_portal_session(tenant, return_url) -> str:
    """Create Stripe Customer Portal session. Returns portal URL."""
    s = _get_stripe()
    customer_id = get_or_create_stripe_customer(tenant)

    session = s.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return session.url


def preview_plan_change(tenant, new_plan, interval) -> dict:
    """Preview proration for plan change. Returns prorated amount and next billing date."""
    s = _get_stripe()
    from .models import TenantSubscription

    sub = TenantSubscription.objects.filter(tenant=tenant).first()
    if not sub or not sub.stripe_subscription_id:
        raise ValueError("No active subscription to change")

    price_id = new_plan.stripe_price_monthly_id if interval == 'month' else new_plan.stripe_price_yearly_id
    if not price_id:
        raise ValueError(f"No Stripe price ID for plan {new_plan.plan_code} interval {interval}")

    stripe_sub = s.Subscription.retrieve(sub.stripe_subscription_id)
    sub_item_id = stripe_sub.items.data[0].id

    # Preview the upcoming invoice with proration
    upcoming = s.Invoice.upcoming(
        customer=tenant.stripe_customer_id,
        subscription=sub.stripe_subscription_id,
        subscription_items=[{
            'id': sub_item_id,
            'price': price_id,
        }],
        subscription_proration_behavior='create_prorations',
    )

    return {
        'prorated_amount_cents': upcoming.amount_due,
        'next_billing_date': upcoming.period_end,
        'new_plan_name': new_plan.name,
    }


def cancel_subscription(tenant, at_period_end=True):
    """Cancel subscription."""
    s = _get_stripe()
    from .models import TenantSubscription

    sub = TenantSubscription.objects.filter(tenant=tenant).first()
    if not sub or not sub.stripe_subscription_id:
        raise ValueError("No active subscription to cancel")

    if at_period_end:
        s.Subscription.modify(
            sub.stripe_subscription_id,
            cancel_at_period_end=True,
        )
    else:
        s.Subscription.cancel(sub.stripe_subscription_id)

    logger.info("Canceled subscription %s for tenant %s (at_period_end=%s)",
                sub.stripe_subscription_id, tenant.id, at_period_end)


def construct_webhook_event(payload, sig_header):
    """Verify and construct webhook event from raw payload."""
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise ValueError("STRIPE_WEBHOOK_SECRET is not configured")
    s = _get_stripe()
    return s.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET,
    )
