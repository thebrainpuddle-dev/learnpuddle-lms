# tests/webhooks/test_webhook_tasks.py
"""
Tests for apps/webhooks/tasks.py — Celery async delivery tasks.

Covers:
1. deliver_webhook()        — single delivery dispatch (all status branches)
2. retry_failed_webhooks()  — batch re-queue of pending retries
3. cleanup_old_deliveries() — pruning of old success/failed records

NOTE ON PATCH TARGETS:
`apps/webhooks/tasks.py::deliver_webhook` performs a *function-local* import:

    def deliver_webhook(self, delivery_id):
        from .models import WebhookDelivery
        from .services import execute_delivery   # <-- imported lazily, in-body

Because that import happens inside the function, `execute_delivery` is NOT an
attribute of the `apps.webhooks.tasks` module. Patching
`apps.webhooks.tasks.execute_delivery` raises:

    AttributeError: <module 'apps.webhooks.tasks' ...> does not have the
    attribute 'execute_delivery'

The correct patch target is the *source* module, i.e.
`apps.webhooks.services.execute_delivery`. Do not "fix" this back to the
tasks module — this comment exists to prevent that regression.
"""

import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase
from django.utils import timezone

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.webhooks.models import WebhookDelivery, WebhookEndpoint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant(name, subdomain):
    return Tenant.objects.create(
        name=name, slug=subdomain, subdomain=subdomain,
        email=f"admin@{subdomain}.example.com", is_active=True,
    )


def _make_user(email, tenant, role="SCHOOL_ADMIN"):
    return User.objects.create_user(
        email=email, password="Pass!123",
        first_name="Test", last_name="User",
        tenant=tenant, role=role, is_active=True,
    )


def _make_endpoint(tenant, user, name="Test Hook",
                   url="https://hooks.example.com/test",
                   events=None, is_active=True):
    return WebhookEndpoint.objects.create(
        tenant=tenant,
        name=name,
        url=url,
        events=events or ["course.created"],
        created_by=user,
        is_active=is_active,
    )


def _make_delivery(endpoint, status="pending", next_retry_at=None):
    return WebhookDelivery.objects.create(
        endpoint=endpoint,
        event_type="course.created",
        payload={"test": True},
        status=status,
        next_retry_at=next_retry_at,
    )


# ===========================================================================
# 1. deliver_webhook()
# ===========================================================================

@pytest.mark.django_db
class DeliverWebhookTaskTestCase(TestCase):
    """Tests for the deliver_webhook Celery task."""

    def setUp(self):
        self.tenant = _make_tenant("Task School", "task")
        self.admin = _make_user("admin@task.com", self.tenant)
        self.endpoint = _make_endpoint(self.tenant, self.admin)
        self.delivery = _make_delivery(self.endpoint)

    def test_logs_and_returns_when_delivery_not_found(self):
        """Non-existent delivery_id → logs error and returns without raising."""
        from apps.webhooks.tasks import deliver_webhook

        nonexistent_id = str(uuid.uuid4())
        # Should not raise; should return gracefully
        result = deliver_webhook(nonexistent_id)
        self.assertIsNone(result)

    def test_skips_already_succeeded_delivery(self):
        """Delivery already 'success' → returns early without calling execute_delivery."""
        from apps.webhooks.tasks import deliver_webhook

        self.delivery.status = "success"
        self.delivery.save()

        with patch("apps.webhooks.services.execute_delivery") as mock_exec:
            deliver_webhook(str(self.delivery.id))
            mock_exec.assert_not_called()

    def test_marks_failed_when_endpoint_is_inactive(self):
        """Disabled endpoint → delivery marked 'failed' with appropriate error_message."""
        from apps.webhooks.tasks import deliver_webhook

        self.endpoint.is_active = False
        self.endpoint.save()

        deliver_webhook(str(self.delivery.id))

        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, "failed")
        self.assertIn("disabled", self.delivery.error_message.lower())

    def test_calls_execute_delivery_for_active_endpoint(self):
        """Active endpoint + pending delivery → execute_delivery is called."""
        from apps.webhooks.tasks import deliver_webhook

        with patch("apps.webhooks.services.execute_delivery", return_value=True) as mock_exec:
            deliver_webhook(str(self.delivery.id))
            mock_exec.assert_called_once_with(self.delivery)

    def test_success_does_not_raise_retry(self):
        """Successful delivery → no retry is triggered."""
        from apps.webhooks.tasks import deliver_webhook

        self.delivery.status = "success"
        self.delivery.save()

        # Task should return without raising
        result = deliver_webhook(str(self.delivery.id))
        self.assertIsNone(result)

    def test_retrying_status_triggers_self_retry(self):
        """
        When execute_delivery returns False and delivery.status='retrying',
        the task must call self.retry(...). In synchronous (non-eager direct call)
        execution, Celery's bound `self.retry()` raises celery.exceptions.Retry —
        the task body explicitly does `raise self.retry(...)`.

        Strict assertion: we expect `Retry` to be raised. We do NOT swallow other
        exceptions — that would mask production bugs (e.g. a typo causing
        ValueError) behind a fake-pass.
        """
        from apps.webhooks.tasks import deliver_webhook
        from celery.exceptions import Retry

        # Set up a retrying delivery with a next_retry_at in the future
        self.delivery.next_retry_at = timezone.now() + timedelta(seconds=60)
        self.delivery.save()

        def _make_retrying(delivery):
            delivery.status = "retrying"
            delivery.save()
            return False

        with patch(
            "apps.webhooks.services.execute_delivery", side_effect=_make_retrying
        ):
            with pytest.raises(Retry):
                deliver_webhook(str(self.delivery.id))

        # execute_delivery must have flipped the delivery into 'retrying' state
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, "retrying")

    def test_execute_delivery_called_with_loaded_delivery_object(self):
        """
        The delivery object passed to execute_delivery must be a fully-loaded
        WebhookDelivery instance with the correct id.
        """
        from apps.webhooks.tasks import deliver_webhook

        captured = []

        def _capture(delivery):
            captured.append(delivery)
            return True

        with patch("apps.webhooks.services.execute_delivery", side_effect=_capture):
            deliver_webhook(str(self.delivery.id))

        self.assertEqual(len(captured), 1)
        self.assertEqual(str(captured[0].id), str(self.delivery.id))


# ===========================================================================
# 2. retry_failed_webhooks()
# ===========================================================================

@pytest.mark.django_db
class RetryFailedWebhooksTaskTestCase(TestCase):
    """Tests for the retry_failed_webhooks periodic Celery task."""

    def setUp(self):
        self.tenant = _make_tenant("Retry School", "retryschool")
        self.admin = _make_user("admin@retryschool.com", self.tenant)
        self.endpoint = _make_endpoint(self.tenant, self.admin)

    def test_returns_zero_when_no_pending_retries(self):
        """No retrying deliveries → returns 0."""
        from apps.webhooks.tasks import retry_failed_webhooks

        count = retry_failed_webhooks()
        self.assertEqual(count, 0)

    def test_queues_retrying_deliveries_with_past_next_retry_at(self):
        """
        Deliveries in 'retrying' status with next_retry_at in the past
        must be re-queued via deliver_webhook.delay().
        """
        from apps.webhooks.tasks import retry_failed_webhooks

        past_time = timezone.now() - timedelta(seconds=10)
        _make_delivery(self.endpoint, status="retrying", next_retry_at=past_time)
        _make_delivery(self.endpoint, status="retrying", next_retry_at=past_time)

        with patch("apps.webhooks.tasks.deliver_webhook") as mock_task:
            mock_task.delay = MagicMock()
            count = retry_failed_webhooks()

        self.assertEqual(count, 2)
        self.assertEqual(mock_task.delay.call_count, 2)

    def test_skips_deliveries_with_future_next_retry_at(self):
        """Retrying deliveries scheduled for the future must NOT be re-queued yet."""
        from apps.webhooks.tasks import retry_failed_webhooks

        future_time = timezone.now() + timedelta(hours=1)
        _make_delivery(self.endpoint, status="retrying", next_retry_at=future_time)

        with patch("apps.webhooks.tasks.deliver_webhook") as mock_task:
            mock_task.delay = MagicMock()
            count = retry_failed_webhooks()

        self.assertEqual(count, 0)
        mock_task.delay.assert_not_called()

    def test_skips_deliveries_for_inactive_endpoints(self):
        """Retrying deliveries whose endpoint is now disabled must be skipped."""
        from apps.webhooks.tasks import retry_failed_webhooks

        past_time = timezone.now() - timedelta(seconds=10)
        inactive_endpoint = _make_endpoint(
            self.tenant, self.admin, name="Inactive Hook",
            url="https://dead.example.com/", is_active=False,
        )
        _make_delivery(inactive_endpoint, status="retrying", next_retry_at=past_time)

        with patch("apps.webhooks.tasks.deliver_webhook") as mock_task:
            mock_task.delay = MagicMock()
            count = retry_failed_webhooks()

        self.assertEqual(count, 0)
        mock_task.delay.assert_not_called()

    def test_does_not_re_queue_already_succeeded_deliveries(self):
        """Deliveries with status='success' must never be re-queued."""
        from apps.webhooks.tasks import retry_failed_webhooks

        past_time = timezone.now() - timedelta(seconds=10)
        _make_delivery(self.endpoint, status="success", next_retry_at=past_time)

        with patch("apps.webhooks.tasks.deliver_webhook") as mock_task:
            mock_task.delay = MagicMock()
            count = retry_failed_webhooks()

        self.assertEqual(count, 0)
        mock_task.delay.assert_not_called()

    def test_does_not_re_queue_already_failed_deliveries(self):
        """Deliveries with status='failed' must never be re-queued by this task."""
        from apps.webhooks.tasks import retry_failed_webhooks

        past_time = timezone.now() - timedelta(seconds=10)
        _make_delivery(self.endpoint, status="failed", next_retry_at=past_time)

        with patch("apps.webhooks.tasks.deliver_webhook") as mock_task:
            mock_task.delay = MagicMock()
            count = retry_failed_webhooks()

        self.assertEqual(count, 0)
        mock_task.delay.assert_not_called()


# ===========================================================================
# 3. cleanup_old_deliveries()
# ===========================================================================

@pytest.mark.django_db
class CleanupOldDeliveriesTaskTestCase(TestCase):
    """Tests for the cleanup_old_deliveries periodic Celery task."""

    def setUp(self):
        self.tenant = _make_tenant("Cleanup School", "cleanupschool")
        self.admin = _make_user("admin@cleanupschool.com", self.tenant)
        self.endpoint = _make_endpoint(self.tenant, self.admin)

    def _make_old_delivery(self, status="success", days_old=60):
        """Create a delivery with created_at in the past."""
        delivery = WebhookDelivery(
            endpoint=self.endpoint,
            event_type="course.created",
            payload={"test": True},
            status=status,
        )
        delivery.save()
        # Manually set the created_at to a past date using a direct update
        past = timezone.now() - timedelta(days=days_old)
        WebhookDelivery.objects.filter(pk=delivery.pk).update(created_at=past)
        return delivery

    def test_returns_zero_when_no_old_deliveries(self):
        """No deliveries older than cutoff → returns 0."""
        from apps.webhooks.tasks import cleanup_old_deliveries

        count = cleanup_old_deliveries(days=30)
        self.assertEqual(count, 0)

    def test_deletes_old_successful_deliveries(self):
        """Old 'success' deliveries must be deleted."""
        from apps.webhooks.tasks import cleanup_old_deliveries

        old_delivery = self._make_old_delivery(status="success", days_old=60)

        count = cleanup_old_deliveries(days=30)

        self.assertEqual(count, 1)
        self.assertFalse(
            WebhookDelivery.objects.filter(pk=old_delivery.pk).exists(),
            "Old successful delivery must be deleted",
        )

    def test_deletes_old_failed_deliveries(self):
        """Old 'failed' deliveries must be deleted."""
        from apps.webhooks.tasks import cleanup_old_deliveries

        old_delivery = self._make_old_delivery(status="failed", days_old=60)

        count = cleanup_old_deliveries(days=30)

        self.assertEqual(count, 1)
        self.assertFalse(
            WebhookDelivery.objects.filter(pk=old_delivery.pk).exists(),
            "Old failed delivery must be deleted",
        )

    def test_preserves_recent_deliveries(self):
        """Deliveries within the cutoff window must NOT be deleted."""
        from apps.webhooks.tasks import cleanup_old_deliveries

        # Create a delivery that's only 5 days old — well within the 30-day window
        recent_delivery = _make_delivery(self.endpoint, status="success")

        count = cleanup_old_deliveries(days=30)

        self.assertEqual(count, 0)
        self.assertTrue(
            WebhookDelivery.objects.filter(pk=recent_delivery.pk).exists(),
            "Recent delivery must be preserved",
        )

    def test_preserves_old_retrying_deliveries(self):
        """
        Old 'retrying' and 'pending' deliveries must NOT be deleted
        (they may still be in flight or scheduled for retry).
        """
        from apps.webhooks.tasks import cleanup_old_deliveries

        retrying_delivery = self._make_old_delivery(status="retrying", days_old=60)
        pending_delivery = self._make_old_delivery(status="pending", days_old=60)

        count = cleanup_old_deliveries(days=30)

        self.assertEqual(count, 0)
        self.assertTrue(
            WebhookDelivery.objects.filter(pk=retrying_delivery.pk).exists(),
            "Retrying delivery must be preserved",
        )
        self.assertTrue(
            WebhookDelivery.objects.filter(pk=pending_delivery.pk).exists(),
            "Pending delivery must be preserved",
        )

    def test_uses_default_30_day_window(self):
        """When called without args, uses the default 30-day window."""
        from apps.webhooks.tasks import cleanup_old_deliveries

        # 31 days old — should be cleaned up by default
        old_delivery = self._make_old_delivery(status="success", days_old=31)

        count = cleanup_old_deliveries()  # No args — uses default days=30

        self.assertEqual(count, 1)
        self.assertFalse(
            WebhookDelivery.objects.filter(pk=old_delivery.pk).exists(),
        )

    def test_returns_count_of_deleted_records(self):
        """Return value must equal the number of records actually deleted."""
        from apps.webhooks.tasks import cleanup_old_deliveries

        self._make_old_delivery(status="success", days_old=60)
        self._make_old_delivery(status="success", days_old=90)
        self._make_old_delivery(status="failed", days_old=45)

        count = cleanup_old_deliveries(days=30)

        self.assertEqual(count, 3)
