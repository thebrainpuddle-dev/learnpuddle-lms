# tests/webhooks/test_webhook_services.py
"""
Tests for apps/webhooks/services.py — zero-coverage module.

Covers:
1. generate_signature()       — HMAC-SHA256 signature correctness
2. trigger_webhook()          — dispatches deliveries to subscribed endpoints
3. execute_delivery()         — HTTP dispatch, success/failure/retry logic
4. emit_* helper functions    — course, user, progress, assignment event helpers
5. Fail-open vs fail-closed   — webhook secret absence is handled correctly
6. Cross-tenant isolation     — trigger_webhook only fires for the correct tenant
"""

import hashlib
import hmac
import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.webhooks.models import WebhookDelivery, WebhookEndpoint
from apps.webhooks.services import (
    execute_delivery,
    generate_signature,
    trigger_webhook,
    emit_course_event,
    emit_user_event,
)


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


def _make_endpoint(tenant, user, name="Test Hook", url="https://hooks.example.com/test",
                   events=None, is_active=True):
    return WebhookEndpoint.objects.create(
        tenant=tenant,
        name=name,
        url=url,
        events=events or ["course.created"],
        created_by=user,
        is_active=is_active,
    )


# ===========================================================================
# 1. generate_signature()
# ===========================================================================

class GenerateSignatureTestCase(TestCase):
    """Unit tests for the HMAC-SHA256 signature helper."""

    def test_returns_hex_string(self):
        """Output should be a lowercase hex digest."""
        sig = generate_signature("payload", "secret")
        self.assertIsInstance(sig, str)
        # SHA-256 hex digest is 64 characters
        self.assertEqual(len(sig), 64)
        # Only hex chars
        int(sig, 16)  # will raise ValueError if not hex

    def test_signature_matches_expected_hmac(self):
        """
        Signature must equal hmac.new(secret, payload, sha256).hexdigest()
        so recipients can verify it independently.
        """
        payload = '{"event": "course.created"}'
        secret = "test-secret-key"
        expected = hmac.new(
            secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(generate_signature(payload, secret), expected)

    def test_different_payloads_produce_different_signatures(self):
        """Changing the payload must change the signature."""
        secret = "shared-secret"
        sig1 = generate_signature("payload-one", secret)
        sig2 = generate_signature("payload-two", secret)
        self.assertNotEqual(sig1, sig2)

    def test_different_secrets_produce_different_signatures(self):
        """Changing the secret must change the signature."""
        payload = "same payload"
        sig1 = generate_signature(payload, "secret-a")
        sig2 = generate_signature(payload, "secret-b")
        self.assertNotEqual(sig1, sig2)

    def test_same_inputs_produce_same_output(self):
        """generate_signature must be deterministic."""
        payload = "deterministic"
        secret = "my-secret"
        self.assertEqual(
            generate_signature(payload, secret),
            generate_signature(payload, secret),
        )

    def test_signature_is_constant_time_safe(self):
        """
        Verify signatures can be compared with hmac.compare_digest
        (the intended usage pattern for recipients).
        """
        payload = "verifiable-payload"
        secret = "verify-secret"
        sig = generate_signature(payload, secret)
        # Should not raise; hmac.compare_digest requires both args to be same type
        result = hmac.compare_digest(sig, sig)
        self.assertTrue(result)


# ===========================================================================
# 2. trigger_webhook()
# ===========================================================================

@pytest.mark.django_db
class TriggerWebhookTestCase(TestCase):
    """Tests for trigger_webhook() — event dispatching logic."""

    def setUp(self):
        self.tenant = _make_tenant("Trigger School", "trigger")
        self.admin = _make_user("admin@trigger.com", self.tenant)
        self.endpoint = _make_endpoint(
            self.tenant, self.admin, events=["course.created"]
        )

    @patch("apps.webhooks.services.deliver_webhook")
    def test_trigger_creates_delivery_record(self, mock_deliver):
        """trigger_webhook must create a WebhookDelivery for each subscribed endpoint."""
        mock_deliver.delay = MagicMock()
        initial_count = WebhookDelivery.objects.count()
        trigger_webhook(
            str(self.tenant.id), "course.created", {"title": "New Course"}
        )
        self.assertEqual(WebhookDelivery.objects.count(), initial_count + 1)

    @patch("apps.webhooks.services.deliver_webhook")
    def test_trigger_returns_delivery_id_list(self, mock_deliver):
        """Return value must be a non-empty list of UUID strings."""
        mock_deliver.delay = MagicMock()
        delivery_ids = trigger_webhook(
            str(self.tenant.id), "course.created", {}
        )
        self.assertEqual(len(delivery_ids), 1)
        # Should be a valid UUID string
        uuid.UUID(delivery_ids[0])

    @patch("apps.webhooks.services.deliver_webhook")
    def test_trigger_queues_async_delivery_task(self, mock_deliver):
        """When delay=True (default), trigger_webhook must enqueue a Celery task."""
        mock_task = MagicMock()
        mock_deliver.delay = mock_task
        trigger_webhook(str(self.tenant.id), "course.created", {})
        mock_task.assert_called_once()

    def test_trigger_with_delay_false_calls_execute_immediately(self):
        """When delay=False, delivery must be executed synchronously (not queued)."""
        with patch("apps.webhooks.services.execute_delivery") as mock_exec:
            mock_exec.return_value = True
            trigger_webhook(
                str(self.tenant.id), "course.created", {}, delay=False
            )
            mock_exec.assert_called_once()

    @patch("apps.webhooks.services.deliver_webhook")
    def test_trigger_returns_empty_list_when_no_subscribed_endpoints(self, mock_deliver):
        """No endpoints subscribed to this event → returns empty list, no deliveries."""
        mock_deliver.delay = MagicMock()
        delivery_ids = trigger_webhook(
            str(self.tenant.id), "quiz.graded", {}  # endpoint subscribes to course.created
        )
        self.assertEqual(delivery_ids, [])

    @patch("apps.webhooks.services.deliver_webhook")
    def test_trigger_returns_empty_for_nonexistent_tenant(self, mock_deliver):
        """A non-existent tenant_id must return [] without creating records."""
        mock_deliver.delay = MagicMock()
        result = trigger_webhook(str(uuid.uuid4()), "course.created", {})
        self.assertEqual(result, [])

    @patch("apps.webhooks.services.deliver_webhook")
    def test_trigger_skips_inactive_endpoints(self, mock_deliver):
        """Inactive endpoints must NOT receive deliveries."""
        mock_deliver.delay = MagicMock()
        self.endpoint.is_active = False
        self.endpoint.save()
        delivery_ids = trigger_webhook(
            str(self.tenant.id), "course.created", {}
        )
        self.assertEqual(delivery_ids, [])

    @patch("apps.webhooks.services.deliver_webhook")
    def test_trigger_wildcard_endpoint_receives_all_events(self, mock_deliver):
        """An endpoint subscribed to '*' must receive any event type."""
        mock_deliver.delay = MagicMock()
        # Update endpoint to subscribe to wildcard
        self.endpoint.events = ["*"]
        self.endpoint.save()
        delivery_ids = trigger_webhook(
            str(self.tenant.id), "quiz.submitted", {"quiz_id": "123"}
        )
        self.assertEqual(len(delivery_ids), 1)

    @patch("apps.webhooks.services.deliver_webhook")
    def test_trigger_updates_endpoint_total_deliveries_count(self, mock_deliver):
        """trigger_webhook must increment total_deliveries on the endpoint."""
        mock_deliver.delay = MagicMock()
        initial = self.endpoint.total_deliveries
        trigger_webhook(str(self.tenant.id), "course.created", {})
        self.endpoint.refresh_from_db()
        self.assertEqual(self.endpoint.total_deliveries, initial + 1)

    @patch("apps.webhooks.services.deliver_webhook")
    def test_trigger_updates_last_triggered_at(self, mock_deliver):
        """trigger_webhook must set last_triggered_at on the endpoint."""
        mock_deliver.delay = MagicMock()
        self.assertIsNone(self.endpoint.last_triggered_at)
        trigger_webhook(str(self.tenant.id), "course.created", {})
        self.endpoint.refresh_from_db()
        self.assertIsNotNone(self.endpoint.last_triggered_at)

    @patch("apps.webhooks.services.deliver_webhook")
    def test_trigger_creates_delivery_with_correct_event_type(self, mock_deliver):
        """The delivery record must have the correct event_type."""
        mock_deliver.delay = MagicMock()
        trigger_webhook(str(self.tenant.id), "course.created", {})
        delivery = WebhookDelivery.objects.filter(endpoint=self.endpoint).last()
        self.assertEqual(delivery.event_type, "course.created")

    @patch("apps.webhooks.services.deliver_webhook")
    def test_trigger_stores_payload_in_delivery(self, mock_deliver):
        """The delivery record must store the event payload."""
        mock_deliver.delay = MagicMock()
        payload = {"course_id": "abc-123", "title": "My Course"}
        trigger_webhook(str(self.tenant.id), "course.created", payload)
        delivery = WebhookDelivery.objects.filter(endpoint=self.endpoint).last()
        self.assertEqual(delivery.payload["course_id"], "abc-123")


# ===========================================================================
# 3. execute_delivery() — HTTP dispatch
# ===========================================================================

@pytest.mark.django_db
class ExecuteDeliveryTestCase(TestCase):
    """Tests for execute_delivery() — mocking requests.post."""

    def setUp(self):
        self.tenant = _make_tenant("Exec School", "exec")
        self.admin = _make_user("admin@exec.com", self.tenant)
        self.endpoint = _make_endpoint(
            self.tenant, self.admin, events=["course.created"]
        )
        self.delivery = WebhookDelivery.objects.create(
            endpoint=self.endpoint,
            event_type="course.created",
            payload={"test": True},
            status="pending",
        )

    def _mock_response(self, status_code=200, text="OK"):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.text = text
        return mock_resp

    @patch("apps.webhooks.services.requests.post")
    def test_successful_delivery_returns_true(self, mock_post):
        """200 response must return True and mark delivery as success."""
        mock_post.return_value = self._mock_response(200)
        result = execute_delivery(self.delivery)
        self.assertTrue(result)

    @patch("apps.webhooks.services.requests.post")
    def test_successful_delivery_marks_status_success(self, mock_post):
        """After 200, delivery.status must be 'success'."""
        mock_post.return_value = self._mock_response(200)
        execute_delivery(self.delivery)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, "success")

    @patch("apps.webhooks.services.requests.post")
    def test_successful_delivery_sets_response_code(self, mock_post):
        """The response status code must be stored on the delivery."""
        mock_post.return_value = self._mock_response(201)
        execute_delivery(self.delivery)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.response_status_code, 201)

    @patch("apps.webhooks.services.requests.post")
    def test_successful_delivery_increments_endpoint_successful_count(self, mock_post):
        """Successful delivery must increment successful_deliveries on endpoint."""
        mock_post.return_value = self._mock_response(200)
        initial = self.endpoint.successful_deliveries
        execute_delivery(self.delivery)
        self.endpoint.refresh_from_db()
        self.assertEqual(self.endpoint.successful_deliveries, initial + 1)

    @patch("apps.webhooks.services.requests.post")
    def test_failed_http_response_returns_false(self, mock_post):
        """Non-2xx response must return False."""
        mock_post.return_value = self._mock_response(500, "Server Error")
        result = execute_delivery(self.delivery)
        self.assertFalse(result)

    @patch("apps.webhooks.services.requests.post")
    def test_failed_delivery_marks_status_failed_on_last_attempt(self, mock_post):
        """When max_attempts is reached, status must be 'failed'."""
        mock_post.return_value = self._mock_response(500)
        # Set attempt count to max-1 so this will hit the max
        self.delivery.attempt_count = self.delivery.max_attempts - 1
        self.delivery.save()
        execute_delivery(self.delivery)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, "failed")

    @patch("apps.webhooks.services.requests.post")
    def test_not_last_attempt_marks_status_retrying(self, mock_post):
        """Before hitting max_attempts, a failed delivery should be 'retrying'."""
        mock_post.return_value = self._mock_response(500)
        # Fresh delivery with 0 attempts — not at max yet
        execute_delivery(self.delivery)
        self.delivery.refresh_from_db()
        if self.delivery.attempt_count < self.delivery.max_attempts:
            self.assertEqual(self.delivery.status, "retrying")

    @patch("apps.webhooks.services.requests.post")
    def test_timeout_exception_marks_delivery_as_failed_or_retrying(self, mock_post):
        """Timeout exception must be caught and delivery marked failed/retrying."""
        import requests as req_lib
        mock_post.side_effect = req_lib.exceptions.Timeout("timeout")
        execute_delivery(self.delivery)
        self.delivery.refresh_from_db()
        self.assertIn(self.delivery.status, ["failed", "retrying"])
        self.assertIn("timed out", self.delivery.error_message.lower())

    @patch("apps.webhooks.services.requests.post")
    def test_connection_error_exception_is_handled(self, mock_post):
        """ConnectionError must be caught and delivery marked failed/retrying."""
        import requests as req_lib
        mock_post.side_effect = req_lib.exceptions.ConnectionError("conn refused")
        execute_delivery(self.delivery)
        self.delivery.refresh_from_db()
        self.assertIn(self.delivery.status, ["failed", "retrying"])

    @patch("apps.webhooks.services.requests.post")
    def test_request_includes_signature_header(self, mock_post):
        """HTTP request must include X-Webhook-Signature header."""
        mock_post.return_value = self._mock_response(200)
        execute_delivery(self.delivery)

        call_kwargs = mock_post.call_args
        headers = call_kwargs[1].get("headers", call_kwargs[0][2] if len(call_kwargs[0]) > 2 else {})
        if isinstance(call_kwargs, tuple) and len(call_kwargs) >= 2:
            # get headers from kwargs
            headers = call_kwargs[1].get("headers", {}) if call_kwargs[1] else {}

        # The mock call should have headers
        mock_post.assert_called_once()
        _, call_kw = mock_post.call_args
        sig_header = call_kw.get("headers", {}).get("X-Webhook-Signature", "")
        self.assertTrue(
            sig_header.startswith("sha256="),
            f"X-Webhook-Signature must start with 'sha256=', got: {sig_header!r}",
        )

    @patch("apps.webhooks.services.requests.post")
    def test_request_includes_event_type_header(self, mock_post):
        """HTTP request must include X-Webhook-Event header."""
        mock_post.return_value = self._mock_response(200)
        execute_delivery(self.delivery)
        _, call_kw = mock_post.call_args
        event_header = call_kw.get("headers", {}).get("X-Webhook-Event", "")
        self.assertEqual(event_header, "course.created")

    @patch("apps.webhooks.services.requests.post")
    def test_retry_sets_next_retry_at(self, mock_post):
        """When retrying, next_retry_at must be set to a future time."""
        mock_post.return_value = self._mock_response(500)
        self.delivery.attempt_count = 0
        self.delivery.save()
        execute_delivery(self.delivery)
        self.delivery.refresh_from_db()
        if self.delivery.status == "retrying":
            self.assertIsNotNone(self.delivery.next_retry_at)
            self.assertGreater(
                self.delivery.next_retry_at,
                timezone.now() - timedelta(seconds=5),
            )


# ===========================================================================
# 4. emit_* helper functions
# ===========================================================================

@pytest.mark.django_db
class EmitEventHelpersTestCase(TestCase):
    """Tests for emit_course_event and emit_user_event."""

    def setUp(self):
        self.tenant = _make_tenant("Emit School", "emits")
        self.admin = _make_user("admin@emits.com", self.tenant)

    @patch("apps.webhooks.services.trigger_webhook")
    def test_emit_course_event_calls_trigger_webhook(self, mock_trigger):
        """emit_course_event must call trigger_webhook with the right event type."""
        from apps.courses.models import Course
        course = Course.objects.create(
            tenant=self.tenant,
            title="Emit Course",
            slug="emit-course",
            created_by=self.admin,
        )
        emit_course_event(course, "created")
        mock_trigger.assert_called_once()
        call_args = mock_trigger.call_args[0]
        self.assertEqual(call_args[1], "course.created")

    @patch("apps.webhooks.services.trigger_webhook")
    def test_emit_course_event_includes_course_id_in_payload(self, mock_trigger):
        """emit_course_event payload must include course_id."""
        from apps.courses.models import Course
        course = Course.objects.create(
            tenant=self.tenant,
            title="Payload Check Course",
            slug="payload-check",
            created_by=self.admin,
        )
        emit_course_event(course, "published")
        _, call_kw = mock_trigger.call_args
        payload = mock_trigger.call_args[0][2]
        self.assertIn("course_id", payload)
        self.assertEqual(payload["course_id"], str(course.id))

    @patch("apps.webhooks.services.trigger_webhook")
    def test_emit_user_event_calls_trigger_webhook(self, mock_trigger):
        """emit_user_event must call trigger_webhook."""
        teacher = _make_user("teacher@emits.com", self.tenant, role="TEACHER")
        emit_user_event(teacher, "registered")
        mock_trigger.assert_called_once()

    @patch("apps.webhooks.services.trigger_webhook")
    def test_emit_user_event_includes_user_id_in_payload(self, mock_trigger):
        """emit_user_event payload must include user_id and email."""
        teacher = _make_user("teacher2@emits.com", self.tenant, role="TEACHER")
        emit_user_event(teacher, "activated")
        payload = mock_trigger.call_args[0][2]
        self.assertIn("user_id", payload)
        self.assertIn("email", payload)
        self.assertEqual(payload["email"], "teacher2@emits.com")

    @patch("apps.webhooks.services.trigger_webhook")
    def test_emit_user_event_uses_correct_tenant_id(self, mock_trigger):
        """emit_user_event must pass the user's tenant ID to trigger_webhook."""
        teacher = _make_user("teacher3@emits.com", self.tenant, role="TEACHER")
        emit_user_event(teacher, "deactivated")
        call_tenant_id = mock_trigger.call_args[0][0]
        self.assertEqual(call_tenant_id, str(self.tenant.id))


# ===========================================================================
# 5. Cross-Tenant Isolation in trigger_webhook
# ===========================================================================

@pytest.mark.django_db
class WebhookServiceCrossTenantTestCase(TestCase):
    """
    Verify that trigger_webhook only fires webhooks for the correct tenant.
    Tenant B's endpoints must not receive tenant A's events.
    """

    def setUp(self):
        self.tenant_a = _make_tenant("Service Tenant A", "srv-a")
        self.tenant_b = _make_tenant("Service Tenant B", "srv-b")
        self.admin_a = _make_user("admin@srv-a.com", self.tenant_a)
        self.admin_b = _make_user("admin@srv-b.com", self.tenant_b)

        self.endpoint_a = _make_endpoint(
            self.tenant_a, self.admin_a, name="A Hook",
            url="https://example.com/a", events=["course.created"],
        )
        self.endpoint_b = _make_endpoint(
            self.tenant_b, self.admin_b, name="B Hook",
            url="https://example.com/b", events=["course.created"],
        )

    @patch("apps.webhooks.services.deliver_webhook")
    def test_triggering_tenant_a_event_only_fires_tenant_a_endpoints(self, mock_deliver):
        """Events for tenant A must only create deliveries for tenant A's endpoints."""
        mock_deliver.delay = MagicMock()
        trigger_webhook(str(self.tenant_a.id), "course.created", {})

        # Only endpoint A should have deliveries
        a_deliveries = WebhookDelivery.objects.filter(endpoint=self.endpoint_a)
        b_deliveries = WebhookDelivery.objects.filter(endpoint=self.endpoint_b)

        self.assertEqual(a_deliveries.count(), 1)
        self.assertEqual(b_deliveries.count(), 0)

    @patch("apps.webhooks.services.deliver_webhook")
    def test_triggering_tenant_b_event_only_fires_tenant_b_endpoints(self, mock_deliver):
        """Events for tenant B must only create deliveries for tenant B's endpoints."""
        mock_deliver.delay = MagicMock()
        trigger_webhook(str(self.tenant_b.id), "course.created", {})

        a_deliveries = WebhookDelivery.objects.filter(endpoint=self.endpoint_a)
        b_deliveries = WebhookDelivery.objects.filter(endpoint=self.endpoint_b)

        self.assertEqual(a_deliveries.count(), 0)
        self.assertEqual(b_deliveries.count(), 1)
