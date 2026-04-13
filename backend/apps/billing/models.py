import uuid

from django.db import models


class SubscriptionPlan(models.Model):
    """
    Defines available subscription tiers.
    Maps to Stripe Products/Prices.
    Global model — not tenant-scoped.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, help_text='Display name, e.g. "Professional"')
    plan_code = models.CharField(
        max_length=20,
        unique=True,
        help_text='Internal code: FREE, STARTER, PRO, ENTERPRISE',
    )
    description = models.TextField(blank=True, default="")

    # Pricing
    price_monthly_cents = models.PositiveIntegerField(default=0)
    price_yearly_cents = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default="usd")

    # Stripe mapping
    stripe_product_id = models.CharField(max_length=255, blank=True, default="")
    stripe_price_monthly_id = models.CharField(max_length=255, blank=True, default="")
    stripe_price_yearly_id = models.CharField(max_length=255, blank=True, default="")

    # Display & ordering
    is_active = models.BooleanField(default=True)
    is_recommended = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)
    features_json = models.JSONField(
        default=list,
        help_text='List of human-readable feature strings, e.g. ["Up to 50 teachers", "Video uploads"]',
    )
    is_custom_pricing = models.BooleanField(
        default=False,
        help_text="True for Enterprise — price negotiated per customer",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscription_plans"
        ordering = ["sort_order"]

    def __str__(self):
        return f"{self.name} ({self.plan_code})"


class TenantSubscription(models.Model):
    """
    Links a Tenant to a Stripe subscription.
    One-to-one relationship with Tenant.
    """

    STATUS_CHOICES = [
        ("active", "Active"),
        ("past_due", "Past Due"),
        ("canceled", "Canceled"),
        ("trialing", "Trialing"),
        ("incomplete", "Incomplete"),
        ("incomplete_expired", "Incomplete Expired"),
        ("unpaid", "Unpaid"),
        ("paused", "Paused"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.OneToOneField(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )

    # Stripe identifiers
    stripe_customer_id = models.CharField(max_length=255, db_index=True)
    stripe_subscription_id = models.CharField(
        max_length=255, unique=True, blank=True, default=""
    )

    # Subscription state
    status = models.CharField(
        max_length=30, choices=STATUS_CHOICES, default="trialing"
    )
    billing_interval = models.CharField(
        max_length=10,
        choices=[("month", "Monthly"), ("year", "Yearly")],
        default="month",
    )

    # Billing period
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)

    # Cancellation
    cancel_at_period_end = models.BooleanField(default=False)
    canceled_at = models.DateTimeField(null=True, blank=True)

    # Trial
    trial_start = models.DateTimeField(null=True, blank=True)
    trial_end = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenant_subscriptions"
        indexes = [
            models.Index(fields=["stripe_customer_id"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.tenant} — {self.plan.plan_code} ({self.status})"


class PaymentHistory(models.Model):
    """Record of invoices / payments from Stripe."""

    STATUS_CHOICES = [
        ("paid", "Paid"),
        ("failed", "Failed"),
        ("pending", "Pending"),
        ("refunded", "Refunded"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="payments",
    )
    subscription = models.ForeignKey(
        TenantSubscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )

    # Stripe identifiers
    stripe_invoice_id = models.CharField(max_length=255, unique=True)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, default="")
    stripe_charge_id = models.CharField(max_length=255, blank=True, default="")

    # Amount
    amount_cents = models.IntegerField()
    currency = models.CharField(max_length=3, default="usd")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    # Invoice details
    description = models.CharField(max_length=500, blank=True, default="")
    invoice_url = models.URLField(max_length=500, blank=True, default="")
    invoice_pdf_url = models.URLField(max_length=500, blank=True, default="")

    # Billing period
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)

    # Failure info
    failure_reason = models.TextField(blank=True, default="")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payment_history"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
        ]

    def __str__(self):
        return f"Invoice {self.stripe_invoice_id} — {self.amount_cents}¢ ({self.status})"


class StripeWebhookEvent(models.Model):
    """
    Idempotency log for processed Stripe webhook events.
    Prevents duplicate processing of the same event.
    """

    stripe_event_id = models.CharField(
        max_length=255, primary_key=True, help_text="Stripe event ID, e.g. evt_xxxx"
    )
    event_type = models.CharField(max_length=100)
    processed_at = models.DateTimeField(auto_now_add=True)
    payload_summary = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "stripe_webhook_events"

    def __str__(self):
        return f"{self.event_type} ({self.stripe_event_id})"
