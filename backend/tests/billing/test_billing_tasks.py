# tests/billing/test_billing_tasks.py
"""
Tests for apps/billing/tasks.py — Celery periodic billing tasks.

Covers:
1. check_past_due_subscriptions()   — finds past_due subs >7 days; logs warning; returns count
2. cleanup_stale_webhook_events()   — deletes StripeWebhookEvent records older than 90 days
3. sync_subscription_status()       — Stripe sync (mocked at Stripe boundary)

All DB-touching tests are wrapped in django.test.TestCase (implicit transaction
rollback after each test) and decorated with @pytest.mark.django_db.

Stripe calls in task #3 are mocked via unittest.mock.patch at the
``stripe.Subscription.retrieve`` symbol so no network traffic is generated.

Total: 17 tests (7 + 5 + 5).

NOTE ON PATCH TARGETS for cleanup_stale_webhook_events:
``apps/billing/tasks.py`` performs function-local imports (``from django.utils
import timezone`` is inside the function body).  As a result ``timezone`` is NOT
an attribute of the ``apps.billing.tasks`` module — patching
``apps.billing.tasks.timezone.now`` would raise AttributeError.  The correct
patch target is ``django.utils.timezone.now``, which modifies the ``now``
callable on the already-loaded module object that the local binding references.
"""

import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.models import (
    StripeWebhookEvent,
    SubscriptionPlan,
    TenantSubscription,
)
from apps.tenants.models import Tenant


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_plan(code="TEST"):
    """Return a SubscriptionPlan; create if it doesn't already exist."""
    plan, _ = SubscriptionPlan.objects.get_or_create(
        plan_code=code,
        defaults=dict(
            name=f"Test Plan {code}",
            price_monthly_cents=0,
            price_yearly_cents=0,
            stripe_product_id=f"prod_{code.lower()}",
            is_active=True,
        ),
    )
    return plan


def _make_tenant(name="Test School", subdomain=""):
    uid = uuid.uuid4().hex[:8]
    subdomain = subdomain or f"school{uid}"
    return Tenant.objects.create(
        name=name,
        slug=subdomain,
        subdomain=subdomain,
        email=f"admin@{subdomain}.example.com",
        is_active=True,
    )


def _make_subscription(tenant, plan, status="past_due", stripe_sub_id=""):
    """Create a TenantSubscription and return it."""
    return TenantSubscription.objects.create(
        tenant=tenant,
        plan=plan,
        status=status,
        stripe_customer_id=f"cus_{uuid.uuid4().hex[:8]}",
        stripe_subscription_id=stripe_sub_id or f"sub_{uuid.uuid4().hex[:8]}",
    )


def _make_webhook_event(event_type="customer.subscription.updated", days_old=0):
    """Create a StripeWebhookEvent. ``days_old`` sets processed_at in the past."""
    event = StripeWebhookEvent.objects.create(
        stripe_event_id=f"evt_{uuid.uuid4().hex}",
        event_type=event_type,
        payload_summary={},
    )
    if days_old > 0:
        # auto_now_add prevents passing processed_at in create() — use update().
        StripeWebhookEvent.objects.filter(pk=event.pk).update(
            processed_at=timezone.now() - timedelta(days=days_old)
        )
    return event


# ===========================================================================
# 1. check_past_due_subscriptions()
# ===========================================================================

@pytest.mark.django_db
class CheckPastDueSubscriptionsTestCase(TestCase):
    """Tests for billing.check_past_due_subscriptions Celery task."""

    def _run(self):
        from apps.billing.tasks import check_past_due_subscriptions
        return check_past_due_subscriptions()

    def test_returns_zero_when_no_subscriptions_exist(self):
        """No subscriptions → task returns 0."""
        result = self._run()
        self.assertEqual(result, 0)

    def test_returns_zero_when_no_past_due_subscriptions(self):
        """Active subscription (not past_due) → not flagged, returns 0."""
        plan = _make_plan()
        tenant = _make_tenant()
        _make_subscription(tenant, plan, status="active")

        result = self._run()
        self.assertEqual(result, 0)

    def test_returns_zero_for_past_due_sub_under_threshold(self):
        """Freshly past_due subscription — well under the 7-day threshold — is not flagged."""
        plan = _make_plan()
        tenant = _make_tenant()
        _make_subscription(tenant, plan, status="past_due")
        # updated_at is auto_now=True so it's set to ~now; no back-dating needed.

        result = self._run()
        self.assertEqual(result, 0)

    def test_flags_past_due_sub_over_threshold(self):
        """past_due subscription with updated_at > 7 days ago → flagged, returns 1."""
        plan = _make_plan()
        tenant = _make_tenant()
        sub = _make_subscription(tenant, plan, status="past_due")
        # Back-date updated_at to 8 days ago via queryset update (auto_now blocks direct set).
        TenantSubscription.objects.filter(pk=sub.pk).update(
            updated_at=timezone.now() - timedelta(days=8)
        )

        result = self._run()
        self.assertEqual(result, 1)

    def test_counts_multiple_flagged_subscriptions(self):
        """Multiple past_due subs over threshold → all counted."""
        plan = _make_plan()
        for i in range(3):
            tenant = _make_tenant(f"School {i}", f"school{i}{uuid.uuid4().hex[:4]}")
            sub = _make_subscription(tenant, plan, status="past_due")
            TenantSubscription.objects.filter(pk=sub.pk).update(
                updated_at=timezone.now() - timedelta(days=10)
            )

        result = self._run()
        self.assertEqual(result, 3)

    def test_does_not_flag_trialing_status(self):
        """trialing subscription → never flagged regardless of age."""
        plan = _make_plan()
        tenant = _make_tenant()
        sub = _make_subscription(tenant, plan, status="trialing")
        TenantSubscription.objects.filter(pk=sub.pk).update(
            updated_at=timezone.now() - timedelta(days=20)
        )

        result = self._run()
        self.assertEqual(result, 0)

    def test_logs_warning_for_flagged_subscription(self):
        """Flagged subscription emits a WARNING log with tenant and plan info.

        Uses Django's built-in ``self.assertLogs()`` rather than the pytest
        ``caplog`` fixture, which cannot be injected into ``unittest.TestCase``
        test methods as positional arguments.
        """
        plan = _make_plan()
        tenant = _make_tenant("Log School", "logschool")
        sub = _make_subscription(tenant, plan, status="past_due")
        TenantSubscription.objects.filter(pk=sub.pk).update(
            updated_at=timezone.now() - timedelta(days=8)
        )

        with self.assertLogs("apps.billing.tasks", level="WARNING") as cm:
            self._run()

        self.assertTrue(
            any("Log School" in msg for msg in cm.output),
            f"Expected 'Log School' in WARNING logs. Got: {cm.output}",
        )


# ===========================================================================
# 2. cleanup_stale_webhook_events()
# ===========================================================================

@pytest.mark.django_db
class CleanupStaleWebhookEventsTestCase(TestCase):
    """Tests for billing.cleanup_stale_webhook_events Celery task."""

    def _run(self):
        from apps.billing.tasks import cleanup_stale_webhook_events
        return cleanup_stale_webhook_events()

    def test_returns_zero_when_no_events_exist(self):
        """No events in DB → task returns 0."""
        result = self._run()
        self.assertEqual(result, 0)

    def test_does_not_delete_recent_events(self):
        """Events processed <90 days ago → not deleted."""
        evt = _make_webhook_event(days_old=0)  # just now

        result = self._run()

        self.assertEqual(result, 0)
        self.assertTrue(
            StripeWebhookEvent.objects.filter(pk=evt.pk).exists(),
            "Recent event must NOT be deleted",
        )

    def test_deletes_events_over_90_days_old(self):
        """Events processed >90 days ago → deleted, count returned."""
        old_evt = _make_webhook_event(days_old=91)
        fresh_evt = _make_webhook_event(days_old=0)

        result = self._run()

        self.assertEqual(result, 1, "Only the old event should be deleted")
        self.assertFalse(
            StripeWebhookEvent.objects.filter(pk=old_evt.pk).exists(),
            "Old event must be deleted",
        )
        self.assertTrue(
            StripeWebhookEvent.objects.filter(pk=fresh_evt.pk).exists(),
            "Recent event must be preserved",
        )

    def test_deletes_multiple_stale_events(self):
        """Multiple old events → all deleted, correct count returned."""
        old_count = 4
        for _ in range(old_count):
            _make_webhook_event(days_old=100)
        _make_webhook_event(days_old=0)  # fresh — should survive

        result = self._run()

        self.assertEqual(result, old_count)
        self.assertEqual(StripeWebhookEvent.objects.count(), 1)

    def test_boundary_exactly_at_cutoff_is_not_deleted(self):
        """Event at exactly the 90-day cutoff is NOT deleted (task uses ``__lt``, not ``__lte``).

        We freeze ``django.utils.timezone.now`` so both the helper that sets
        ``processed_at`` and the task's ``cutoff`` computation see the same
        timestamp, making the boundary assertion fully deterministic.

        NOTE ON PATCH TARGET:
        ``cleanup_stale_webhook_events`` does ``from django.utils import
        timezone`` *inside* the function body — ``timezone`` is therefore NOT a
        module-level attribute of ``apps.billing.tasks``.  Patching
        ``django.utils.timezone.now`` directly modifies the callable on the
        already-loaded module object, which is what the local binding points to.
        """
        fixed_now = timezone.now()
        cutoff = fixed_now - timedelta(days=90)

        # Create an event and pin its processed_at to exactly the cutoff.
        evt_90 = _make_webhook_event(days_old=0)
        StripeWebhookEvent.objects.filter(pk=evt_90.pk).update(processed_at=cutoff)

        # Freeze time so the task's cutoff == our cutoff == evt_90.processed_at.
        with patch("django.utils.timezone.now", return_value=fixed_now):
            result = self._run()

        self.assertEqual(result, 0, "Event at exactly the cutoff must NOT be deleted (__lt, not __lte)")
        self.assertTrue(
            StripeWebhookEvent.objects.filter(pk=evt_90.pk).exists(),
            "Event at boundary must still exist",
        )


# ===========================================================================
# 3. sync_subscription_status()
# ===========================================================================

@pytest.mark.django_db
class SyncSubscriptionStatusTestCase(TestCase):
    """Tests for billing.sync_subscription_status Celery task."""

    def _run(self, tenant_id):
        from apps.billing.tasks import sync_subscription_status
        return sync_subscription_status(str(tenant_id))

    def test_returns_none_for_nonexistent_tenant(self):
        """Non-existent tenant_id → logs error and returns None (no crash)."""
        fake_id = uuid.uuid4()
        # Should not raise
        result = self._run(fake_id)
        self.assertIsNone(result)

    def test_returns_none_when_no_subscription(self):
        """Tenant with no subscription → logs info and returns None."""
        plan = _make_plan()
        tenant = _make_tenant()
        # No TenantSubscription created

        result = self._run(tenant.id)
        self.assertIsNone(result)

    def test_returns_none_when_subscription_has_no_stripe_id(self):
        """Subscription without stripe_subscription_id → returns None."""
        plan = _make_plan()
        tenant = _make_tenant()
        sub = _make_subscription(tenant, plan, status="active", stripe_sub_id="")
        # Force empty stripe_subscription_id
        TenantSubscription.objects.filter(pk=sub.pk).update(stripe_subscription_id="")

        result = self._run(tenant.id)
        self.assertIsNone(result)

    @override_settings(STRIPE_SECRET_KEY="sk_test_mock")
    def test_returns_none_when_stripe_retrieve_fails(self):
        """stripe.Subscription.retrieve raises Exception → logs and returns None (no crash)."""
        plan = _make_plan()
        tenant = _make_tenant()
        _make_subscription(tenant, plan, status="active")

        with patch("stripe.Subscription.retrieve", side_effect=Exception("Stripe down")):
            result = self._run(tenant.id)

        self.assertIsNone(result)

    @override_settings(STRIPE_SECRET_KEY="sk_test_mock")
    def test_calls_sync_subscription_on_success(self):
        """Happy path: stripe.Subscription.retrieve succeeds → _sync_subscription is called.

        NOTE ON PATCH TARGET:
        The task does ``from .webhook_handlers import _sync_subscription`` inside the
        function body, so the callable is looked up fresh from the source module each
        invocation.  We patch at the source module (apps.billing.webhook_handlers) rather
        than the tasks module, which does not bind _sync_subscription as an attribute.
        """
        plan = _make_plan()
        tenant = _make_tenant()
        sub = _make_subscription(tenant, plan, status="past_due")

        mock_stripe_sub = MagicMock()
        mock_stripe_sub.id = sub.stripe_subscription_id

        with patch("stripe.Subscription.retrieve", return_value=mock_stripe_sub) as mock_retrieve, \
             patch("apps.billing.webhook_handlers._sync_subscription") as mock_sync:
            self._run(tenant.id)

        mock_retrieve.assert_called_once_with(sub.stripe_subscription_id)
        mock_sync.assert_called_once()
        # Verify the stripe sub object was passed as first arg
        args = mock_sync.call_args[0]
        self.assertEqual(args[0], mock_stripe_sub)
