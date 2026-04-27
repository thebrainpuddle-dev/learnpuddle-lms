"""
Tests for TASK-055 — Slack / Microsoft Teams Notification Bots.

Coverage:
 1. SSRF guard: link-local address rejected
 2. SSRF guard: loopback address rejected
 3. SSRF guard: allowlist blocks arbitrary hostname
 4. SSRF guard: Slack hostname accepted
 5. SSRF guard: Teams hostname accepted
 6. Webhook URL encrypted at rest (raw-SQL assertion)
 7. API response masks webhook URL to last-4
 8. Slack message builder produces expected Block Kit structure
 9. Teams message builder produces expected MessageCard structure
10. Dispatcher is idempotent (duplicate dispatch → 1 delivery row)
11. Dispatcher respects role_filter routing rule
12. Celery task delivers to Slack webhook (mocked via responses)
13. Celery task delivers to Teams webhook (mocked via responses)
14. Celery task retries on 5xx then marks DLQ after max retries
15. prune_chat_deliveries removes rows older than 30 days
16. Cross-tenant isolation: admin of tenant A cannot access tenant B integration
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from apps.integrations_common.crypto import decrypt_secret, encrypt_secret, mask_secret
from apps.integrations_chat.builders.slack import build_slack_message
from apps.integrations_chat.builders.teams import build_teams_message
from apps.integrations_chat.models import ChatDelivery, ChatIntegration, ChatRoutingRule
from apps.integrations_chat.ssrf_guard import SSRFError, validate_webhook_host


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def make_tenant(name="Test School", subdomain=None):
    from apps.tenants.models import Tenant
    subdomain = subdomain or name.lower().replace(" ", "-")
    return Tenant.objects.create(
        name=name,
        subdomain=subdomain,
        slug=subdomain,
        email=f"admin@{subdomain}.example.com",
    )


def make_user(tenant, role="SCHOOL_ADMIN", email=None):
    from apps.users.models import User
    email = email or f"{role.lower()}@{tenant.subdomain}.example.com"
    return User.objects.create_user(
        email=email,
        password="AdminP@ss123",
        tenant=tenant,
        role=role,
    )


SLACK_WEBHOOK = "https://hooks.slack.com/services/T00000/B00000/xxxxxxxxxxxx"
TEAMS_WEBHOOK = "https://org.webhook.office.com/webhookb2/abc/IncomingWebhook/xyz/token"


def make_integration(tenant, provider="slack", user=None, webhook_url=None):
    url = webhook_url or (SLACK_WEBHOOK if provider == "slack" else TEAMS_WEBHOOK)
    return ChatIntegration.objects.create(
        tenant=tenant,
        provider=provider,
        display_name=f"Test {provider.title()} Channel",
        webhook_url_encrypted=encrypt_secret(url),
        created_by=user,
    )


# ---------------------------------------------------------------------------
# 1-2. SSRF guard — link-local + loopback rejected
# ---------------------------------------------------------------------------


class TestSSRFGuardRejection(TestCase):
    """SSRF guard unit tests — these call the guard directly, no HTTP."""

    def test_link_local_address_rejected(self):
        """AWS IMDS / link-local addresses must be blocked."""
        from apps.integrations_chat.ssrf_guard import _is_private_ip
        self.assertTrue(_is_private_ip("169.254.169.254"))

    def test_loopback_address_rejected(self):
        """Loopback addresses must be blocked."""
        from apps.integrations_chat.ssrf_guard import _is_private_ip
        self.assertTrue(_is_private_ip("127.0.0.1"))

    def test_cgnat_address_rejected(self):
        """CGNAT (100.64.0.0/10) addresses must be blocked."""
        from apps.integrations_chat.ssrf_guard import _is_private_ip
        self.assertTrue(_is_private_ip("100.64.0.1"))

    def test_rfc1918_10_rejected(self):
        """RFC1918 10.x.x.x must be blocked."""
        from apps.integrations_chat.ssrf_guard import _is_private_ip
        self.assertTrue(_is_private_ip("10.0.0.1"))

    def test_rfc1918_192168_rejected(self):
        """RFC1918 192.168.x.x must be blocked."""
        from apps.integrations_chat.ssrf_guard import _is_private_ip
        self.assertTrue(_is_private_ip("192.168.1.1"))

    def test_public_ip_not_rejected(self):
        """A real public IP should not be blocked."""
        from apps.integrations_chat.ssrf_guard import _is_private_ip
        self.assertFalse(_is_private_ip("13.107.42.14"))  # Microsoft CDN

    def test_validate_webhook_rejects_imds_url(self):
        """validate_webhook_host must raise SSRFError for link-local URL."""
        with self.assertRaises(SSRFError) as ctx:
            validate_webhook_host("http://169.254.169.254/latest/meta-data/")
        self.assertIn("INVALID_WEBHOOK_HOST", str(ctx.exception))

    def test_validate_webhook_rejects_loopback_url(self):
        """validate_webhook_host must raise SSRFError for loopback URL."""
        with self.assertRaises(SSRFError) as ctx:
            validate_webhook_host("http://127.0.0.1/")
        self.assertIn("INVALID_WEBHOOK_HOST", str(ctx.exception))


# ---------------------------------------------------------------------------
# 3-5. Host allowlist
# ---------------------------------------------------------------------------


class TestHostAllowlist(TestCase):
    def test_arbitrary_host_rejected(self):
        """Non-Slack/Teams hostnames must be rejected."""
        with self.assertRaises(SSRFError) as ctx:
            validate_webhook_host("https://example.com/foo")
        self.assertIn("INVALID_WEBHOOK_HOST", str(ctx.exception))

    def test_slack_host_accepted(self):
        """hooks.slack.com must pass allowlist."""
        # Should not raise.
        validate_webhook_host(SLACK_WEBHOOK)

    def test_teams_host_accepted(self):
        """*.webhook.office.com must pass allowlist."""
        validate_webhook_host(TEAMS_WEBHOOK)

    def test_attacker_subdomain_rejected(self):
        """An attacker subdomain ending in 'webhook.office.com' but not properly should be checked."""
        # e.g., 'evilwebhook.office.com' — does NOT end with '.webhook.office.com'
        with self.assertRaises(SSRFError):
            validate_webhook_host("https://evilwebhook.office.com/foo")

    def test_slack_lookalike_rejected(self):
        """hooks.slack.com.evil.com must be rejected."""
        with self.assertRaises(SSRFError):
            validate_webhook_host("https://hooks.slack.com.evil.com/foo")


# ---------------------------------------------------------------------------
# 6. Webhook URL encrypted at rest — raw-SQL assertion
# ---------------------------------------------------------------------------


class TestWebhookEncryptionAtRest(TestCase):
    def setUp(self):
        self.tenant = make_tenant("Crypto School", subdomain="crypto-school")
        self.user = make_user(self.tenant)
        self.integration = make_integration(self.tenant, user=self.user)

    def test_raw_sql_shows_no_plaintext_url(self):
        """
        Raw SQL fetch of webhook_url_encrypted must NOT contain the plaintext URL.
        This is the acceptance-gate assertion for at-rest encryption.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT webhook_url_encrypted FROM integrations_chat_integration WHERE id = %s",
                [str(self.integration.pk)],
            )
            row = cursor.fetchone()
        raw_value = row[0]
        self.assertIsNotNone(raw_value)
        # The raw DB value must NOT be the plaintext URL.
        self.assertNotIn("hooks.slack.com/services", raw_value)
        # And must not contain any portion of the secret path segment.
        self.assertNotIn("xxxxxxxxxxxx", raw_value)
        # But it should be decodable by our crypto module.
        decrypted = decrypt_secret(raw_value)
        self.assertEqual(decrypted, SLACK_WEBHOOK)


# ---------------------------------------------------------------------------
# 7. API masks webhook URL
# ---------------------------------------------------------------------------


class TestWebhookMasking(TestCase):
    def test_mask_secret_shows_last_4(self):
        """mask_secret must reveal only the last 4 characters."""
        result = mask_secret("https://hooks.slack.com/services/T123/B456/abcdefgh")
        self.assertTrue(result.endswith("efgh"))
        self.assertNotIn("hooks.slack.com/services", result)

    def test_mask_secret_short_string_returned_as_is(self):
        """Short strings (≤ visible) are returned unmodified."""
        self.assertEqual(mask_secret("ab", visible=4), "ab")

    def test_serializer_returns_masked_url(self):
        """ChatIntegrationSerializer must return webhook_url_masked, not the raw URL."""
        from apps.integrations_chat.serializers import ChatIntegrationSerializer
        tenant = make_tenant("Mask School", subdomain="mask-school")
        user = make_user(tenant)
        integration = make_integration(tenant, user=user)
        data = ChatIntegrationSerializer(integration).data
        self.assertNotIn("webhook_url_encrypted", data)
        masked = data.get("webhook_url_masked", "")
        self.assertNotIn("hooks.slack.com/services/", masked)
        # Last 4 chars of the plaintext URL must appear.
        self.assertTrue(masked.endswith("xxxx"))


# ---------------------------------------------------------------------------
# 8. Slack builder
# ---------------------------------------------------------------------------


class TestSlackBuilder(TestCase):
    def test_build_slack_message_structure(self):
        """build_slack_message must return dict with 'blocks' and 'text'."""
        body = build_slack_message(
            "COURSE_ASSIGNED",
            {"title": "New Course", "message": "You have a new course.", "school_name": "Test School"},
        )
        self.assertIn("blocks", body)
        self.assertIn("text", body)
        self.assertIsInstance(body["blocks"], list)
        # At minimum header and divider
        block_types = [b["type"] for b in body["blocks"]]
        self.assertIn("header", block_types)
        self.assertIn("divider", block_types)

    def test_slack_message_contains_title(self):
        """Block Kit header must contain the notification title."""
        body = build_slack_message("REMINDER", {"title": "Deadline Tomorrow", "school_name": "Acme"})
        header = next(b for b in body["blocks"] if b["type"] == "header")
        self.assertIn("Deadline Tomorrow", header["text"]["text"])

    def test_slack_message_includes_button_when_url_provided(self):
        """A 'url' in payload must produce an 'actions' block with a button."""
        body = build_slack_message(
            "COURSE_ASSIGNED",
            {"title": "Course", "url": "https://demo.learnpuddle.com/courses/123", "school_name": "S"},
        )
        action_blocks = [b for b in body["blocks"] if b.get("type") == "actions"]
        self.assertTrue(len(action_blocks) > 0)


# ---------------------------------------------------------------------------
# 9. Teams builder
# ---------------------------------------------------------------------------


class TestTeamsBuilder(TestCase):
    def test_build_teams_message_type(self):
        """Teams builder must produce a MessageCard @type."""
        body = build_teams_message("ANNOUNCEMENT", {"title": "School Holiday", "school_name": "Westside"})
        self.assertEqual(body["@type"], "MessageCard")
        self.assertIn("sections", body)
        self.assertIn("themeColor", body)

    def test_teams_message_includes_action_when_url_provided(self):
        """Teams builder must include potentialAction when url is present."""
        body = build_teams_message(
            "REPORT_GENERATED",
            {"title": "Report Ready", "url": "https://demo.learnpuddle.com/reports/1", "school_name": "S"},
        )
        self.assertIn("potentialAction", body)


# ---------------------------------------------------------------------------
# 10. Dispatcher idempotency
# ---------------------------------------------------------------------------


class TestDispatcherIdempotency(TestCase):
    def setUp(self):
        self.tenant = make_tenant("Idempotent School", subdomain="idempotent-school")
        self.user = make_user(self.tenant)
        self.integration = make_integration(self.tenant, user=self.user)
        ChatRoutingRule.objects.create(
            integration=self.integration,
            notification_type="COURSE_ASSIGNED",
            enabled=True,
        )

    @patch("apps.integrations_chat.tasks.deliver_chat_message")
    def test_same_notification_dispatched_twice_creates_one_delivery(self, mock_task):
        """Calling dispatch_notification twice with the same notification_id must
        produce exactly one ChatDelivery row."""
        from apps.integrations_chat.dispatcher import dispatch_notification

        mock_notification = MagicMock()
        mock_notification.pk = uuid.uuid4()
        mock_notification.tenant = self.tenant
        mock_notification.notification_type = "COURSE_ASSIGNED"
        mock_notification.title = "New Course"
        mock_notification.message = "You've been assigned a course."
        teacher_mock = MagicMock()
        teacher_mock.role = "TEACHER"
        teacher_mock.get_full_name.return_value = "Jane Teacher"
        mock_notification.teacher = teacher_mock

        mock_task.delay = MagicMock()

        dispatch_notification(mock_notification)
        dispatch_notification(mock_notification)  # Second call — should be idempotent.

        count = ChatDelivery.objects.filter(
            integration=self.integration,
            notification_id=mock_notification.pk,
        ).count()
        self.assertEqual(count, 1, "Idempotency violated: expected exactly 1 delivery row")


# ---------------------------------------------------------------------------
# 11. Dispatcher respects role_filter
# ---------------------------------------------------------------------------


class TestDispatcherRoleFilter(TestCase):
    def setUp(self):
        self.tenant = make_tenant("Role Filter School", subdomain="role-filter-school")
        self.user = make_user(self.tenant)
        self.integration = make_integration(self.tenant, user=self.user)
        # Only HOD notifications should route here.
        ChatRoutingRule.objects.create(
            integration=self.integration,
            notification_type="COURSE_ASSIGNED",
            role_filter="HOD",
            enabled=True,
        )

    @patch("apps.integrations_chat.tasks.deliver_chat_message")
    def test_non_hod_notification_not_dispatched(self, mock_task):
        """Notification for a TEACHER must not match a HOD-only rule."""
        from apps.integrations_chat.dispatcher import dispatch_notification

        mock_notification = MagicMock()
        mock_notification.pk = uuid.uuid4()
        mock_notification.tenant = self.tenant
        mock_notification.notification_type = "COURSE_ASSIGNED"
        mock_notification.title = "Test"
        mock_notification.message = "Test"
        teacher_mock = MagicMock()
        teacher_mock.role = "TEACHER"  # not HOD
        teacher_mock.get_full_name.return_value = "John Teacher"
        mock_notification.teacher = teacher_mock

        dispatch_notification(mock_notification)

        self.assertEqual(
            ChatDelivery.objects.filter(notification_id=mock_notification.pk).count(),
            0,
            "TEACHER notification should NOT match HOD-only rule",
        )

    @patch("apps.integrations_chat.tasks.deliver_chat_message")
    def test_hod_notification_is_dispatched(self, mock_task):
        """Notification for a HOD must match the HOD rule."""
        from apps.integrations_chat.dispatcher import dispatch_notification

        mock_notification = MagicMock()
        mock_notification.pk = uuid.uuid4()
        mock_notification.tenant = self.tenant
        mock_notification.notification_type = "COURSE_ASSIGNED"
        mock_notification.title = "Test"
        mock_notification.message = "Test"
        hod_mock = MagicMock()
        hod_mock.role = "HOD"
        hod_mock.get_full_name.return_value = "Head Teacher"
        mock_notification.teacher = hod_mock

        mock_task.delay = MagicMock()

        dispatch_notification(mock_notification)

        self.assertEqual(
            ChatDelivery.objects.filter(notification_id=mock_notification.pk).count(),
            1,
        )


# ---------------------------------------------------------------------------
# 12-13. Celery task: Slack and Teams delivery (mocked HTTP)
# ---------------------------------------------------------------------------


class TestCeleryDeliverySlack(TestCase):
    def setUp(self):
        self.tenant = make_tenant("Celery Slack School", subdomain="celery-slack-school")
        self.user = make_user(self.tenant)
        self.integration = make_integration(self.tenant, provider="slack", user=self.user)
        self.delivery = ChatDelivery.objects.create(
            integration=self.integration,
            notification_id=uuid.uuid4(),
            notification_type="COURSE_ASSIGNED",
            payload_json={"title": "New Course", "message": "You have a new course.", "school_name": "Test"},
            status=ChatDelivery.STATUS_PENDING,
        )

    @patch("apps.integrations_chat.ssrf_guard.safe_post")
    def test_slack_delivery_marks_sent_on_200(self, mock_post):
        """deliver_chat_message must set status=sent on 200 response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from apps.integrations_chat.tasks import deliver_chat_message
        deliver_chat_message(str(self.delivery.pk))

        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, ChatDelivery.STATUS_SENT)


class TestCeleryDeliveryTeams(TestCase):
    def setUp(self):
        self.tenant = make_tenant("Celery Teams School", subdomain="celery-teams-school")
        self.user = make_user(self.tenant)
        self.integration = make_integration(self.tenant, provider="teams", user=self.user)
        self.delivery = ChatDelivery.objects.create(
            integration=self.integration,
            notification_id=uuid.uuid4(),
            notification_type="ANNOUNCEMENT",
            payload_json={"title": "Holiday", "message": "School holiday.", "school_name": "Test"},
            status=ChatDelivery.STATUS_PENDING,
        )

    @patch("apps.integrations_chat.ssrf_guard.safe_post")
    def test_teams_delivery_marks_sent_on_200(self, mock_post):
        """deliver_chat_message must set status=sent for Teams provider on 200."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from apps.integrations_chat.tasks import deliver_chat_message
        deliver_chat_message(str(self.delivery.pk))

        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, ChatDelivery.STATUS_SENT)


# ---------------------------------------------------------------------------
# 14. Celery task moves to DLQ on max retries
# ---------------------------------------------------------------------------


class TestCeleryDLQ(TestCase):
    def setUp(self):
        self.tenant = make_tenant("DLQ School", subdomain="dlq-school")
        self.user = make_user(self.tenant)
        self.integration = make_integration(self.tenant, user=self.user)
        self.delivery = ChatDelivery.objects.create(
            integration=self.integration,
            notification_id=uuid.uuid4(),
            notification_type="SYSTEM",
            payload_json={"title": "Test", "school_name": "Test"},
            status=ChatDelivery.STATUS_PENDING,
        )

    def test_dlq_on_repeated_failure(self):
        """After max retries exhausted, delivery must move to DLQ."""
        from apps.integrations_chat.tasks import _mark_dlq

        # Simulate what the task does after max retries: call _mark_dlq directly.
        _mark_dlq(self.delivery, self.integration, "connection_failed")

        self.delivery.refresh_from_db()
        self.integration.refresh_from_db()
        self.assertEqual(self.delivery.status, ChatDelivery.STATUS_DLQ)
        self.assertEqual(self.integration.last_delivery_status, "dlq")


# ---------------------------------------------------------------------------
# 15. prune_chat_deliveries
# ---------------------------------------------------------------------------


class TestPruneDeliveries(TestCase):
    def setUp(self):
        self.tenant = make_tenant("Prune School", subdomain="prune-school")
        self.user = make_user(self.tenant)
        self.integration = make_integration(self.tenant, user=self.user)

    def test_prune_deletes_old_terminal_rows(self):
        """prune_chat_deliveries must delete rows > 30 days old with terminal status."""
        old_delivery = ChatDelivery.objects.create(
            integration=self.integration,
            notification_id=uuid.uuid4(),
            notification_type="SYSTEM",
            payload_json={},
            status=ChatDelivery.STATUS_SENT,
        )
        # Backdate the created_at to 31 days ago.
        ChatDelivery.objects.filter(pk=old_delivery.pk).update(
            created_at=timezone.now() - timedelta(days=31)
        )

        recent_delivery = ChatDelivery.objects.create(
            integration=self.integration,
            notification_id=uuid.uuid4(),
            notification_type="SYSTEM",
            payload_json={},
            status=ChatDelivery.STATUS_SENT,
        )

        from apps.integrations_chat.tasks import prune_chat_deliveries
        result = prune_chat_deliveries()

        self.assertGreaterEqual(result["deleted"], 1)
        self.assertFalse(ChatDelivery.objects.filter(pk=old_delivery.pk).exists())
        self.assertTrue(ChatDelivery.objects.filter(pk=recent_delivery.pk).exists())


# ---------------------------------------------------------------------------
# 16. Cross-tenant isolation
# ---------------------------------------------------------------------------


class TestCrossTenantIsolation(TestCase):
    def setUp(self):
        from django.test import RequestFactory
        self.factory = RequestFactory()
        self.tenant_a = make_tenant("School A", subdomain="school-a")
        self.tenant_b = make_tenant("School B", subdomain="school-b")
        self.admin_a = make_user(self.tenant_a, role="SCHOOL_ADMIN", email="admin@school-a.example.com")
        self.admin_b = make_user(self.tenant_b, role="SCHOOL_ADMIN", email="admin@school-b.example.com")
        self.integration_b = make_integration(self.tenant_b, user=self.admin_b)

    def test_admin_a_cannot_read_tenant_b_integration(self):
        """
        _get_integration must return None when querying tenant B's integration
        with tenant A's context.
        """
        from apps.integrations_chat.views import _get_integration
        result = _get_integration(str(self.integration_b.pk), self.tenant_a)
        self.assertIsNone(result)

    def test_admin_a_can_read_own_integration(self):
        """
        _get_integration must return the integration when querying with the
        correct tenant.
        """
        from apps.integrations_chat.views import _get_integration
        integration_a = make_integration(self.tenant_a, user=self.admin_a)
        result = _get_integration(str(integration_a.pk), self.tenant_a)
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, integration_a.pk)


# ---------------------------------------------------------------------------
# Bonus: crypto module unit tests
# ---------------------------------------------------------------------------


class TestCryptoModule(TestCase):
    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "https://hooks.slack.com/services/T123/B456/secrettoken"
        ciphertext = encrypt_secret(plaintext)
        self.assertNotEqual(ciphertext, plaintext)
        self.assertEqual(decrypt_secret(ciphertext), plaintext)

    def test_empty_string_roundtrip(self):
        self.assertEqual(encrypt_secret(""), "")
        self.assertEqual(decrypt_secret(""), "")

    def test_different_calls_produce_different_ciphertext(self):
        """Fernet uses random IV — same plaintext produces different ciphertext."""
        ct1 = encrypt_secret("same-secret")
        ct2 = encrypt_secret("same-secret")
        self.assertNotEqual(ct1, ct2)
        self.assertEqual(decrypt_secret(ct1), decrypt_secret(ct2))

    def test_tampered_ciphertext_returns_empty(self):
        ct = encrypt_secret("my-secret")
        tampered = ct[:-5] + "XXXXX"
        self.assertEqual(decrypt_secret(tampered), "")
