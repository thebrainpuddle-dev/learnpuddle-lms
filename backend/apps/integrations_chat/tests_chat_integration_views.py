"""
HTTP-level view tests for the integrations_chat app.

Covers the REST API endpoints:
  GET    /api/v1/admin/chat-integrations/           — list integrations
  POST   /api/v1/admin/chat-integrations/           — create integration
  GET    /api/v1/admin/chat-integrations/{pk}/      — retrieve
  PATCH  /api/v1/admin/chat-integrations/{pk}/      — update
  DELETE /api/v1/admin/chat-integrations/{pk}/      — soft-delete
  GET    /api/v1/admin/chat-integrations/{pk}/deliveries/ — delivery history
  GET/POST /api/v1/admin/chat-integrations/{pk}/rules/    — routing rules

Security invariants tested:
  - All endpoints require SCHOOL_ADMIN or higher
  - TEACHER cannot access any endpoint
  - Unauthenticated requests return 401
  - Cross-tenant access returns 404 (no 403 enumeration leak)
  - Soft-delete sets is_active=False, does not hard-delete
  - webhook_url is never returned in plaintext (masked to last-4)
"""

from __future__ import annotations

import uuid

import pytest
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.integrations_common.crypto import encrypt_secret
from apps.integrations_chat.models import ChatDelivery, ChatIntegration, ChatRoutingRule
from apps.tenants.models import Tenant
from apps.users.models import User

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SLACK_WEBHOOK = "https://hooks.slack.com/services/T00000/B00000/xxxxxxxxxxxxxxxxxxx"
TEAMS_WEBHOOK = "https://org.webhook.office.com/webhookb2/abc/IncomingWebhook/xyz/token"

PLATFORM_DOMAIN = "lms.com"
ALLOWED_HOSTS = ["*.lms.com", "testserver", "localhost"]


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return uuid.uuid4().hex[:8]


def make_tenant(name: str = None, subdomain: str = None) -> Tenant:
    uid = _uid()
    subdomain = subdomain or f"school-{uid}"
    return Tenant.objects.create(
        name=name or f"School {uid}",
        subdomain=subdomain,
        slug=subdomain,
        email=f"admin@{subdomain}.example.com",
        is_active=True,
    )


def make_user(tenant: Tenant, role: str = "SCHOOL_ADMIN", email: str = None) -> User:
    email = email or f"{role.lower()}-{_uid()}@{tenant.subdomain}.example.com"
    return User.objects.create_user(
        email=email,
        password="AdminPass123!",
        tenant=tenant,
        role=role,
        first_name="Test",
        last_name="User",
        is_active=True,
    )


def make_integration(
    tenant: Tenant,
    user: User = None,
    provider: str = ChatIntegration.PROVIDER_SLACK,
    webhook_url: str = None,
    display_name: str = None,
    is_active: bool = True,
) -> ChatIntegration:
    url = webhook_url or (SLACK_WEBHOOK if provider == "slack" else TEAMS_WEBHOOK)
    return ChatIntegration.objects.create(
        tenant=tenant,
        provider=provider,
        display_name=display_name or f"Test {provider.title()} {_uid()}",
        webhook_url_encrypted=encrypt_secret(url),
        created_by=user,
        is_active=is_active,
    )


def auth_client(user: User, tenant: Tenant) -> APIClient:
    """Return an authenticated APIClient with the correct Host header."""
    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
    return client


def anon_client(tenant: Tenant) -> APIClient:
    """Return an unauthenticated APIClient with the correct Host header."""
    client = APIClient()
    client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
    return client


LIST_URL = "/api/v1/admin/chat-integrations/"


def detail_url(pk) -> str:
    return f"/api/v1/admin/chat-integrations/{pk}/"


def rules_url(pk) -> str:
    return f"/api/v1/admin/chat-integrations/{pk}/rules/"


def deliveries_url(pk) -> str:
    return f"/api/v1/admin/chat-integrations/{pk}/deliveries/"


# ---------------------------------------------------------------------------
# 1. Authentication & authorisation guards
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=ALLOWED_HOSTS, PLATFORM_DOMAIN=PLATFORM_DOMAIN)
@pytest.mark.django_db
class TestChatIntegrationAuthGuards(TestCase):
    """All endpoints require SCHOOL_ADMIN or SUPER_ADMIN."""

    def setUp(self):
        self.tenant = make_tenant()
        self.admin = make_user(self.tenant, role="SCHOOL_ADMIN")
        self.teacher = make_user(self.tenant, role="TEACHER")
        self.integration = make_integration(self.tenant, user=self.admin)

    def test_list_unauthenticated_returns_401(self):
        client = anon_client(self.tenant)
        resp = client.get(LIST_URL)
        self.assertEqual(resp.status_code, 401, "Unauthenticated list must be 401")

    def test_create_unauthenticated_returns_401(self):
        client = anon_client(self.tenant)
        resp = client.post(
            LIST_URL,
            {"provider": "slack", "display_name": "X", "webhook_url": SLACK_WEBHOOK},
            format="json",
        )
        self.assertEqual(resp.status_code, 401, "Unauthenticated create must be 401")

    def test_detail_unauthenticated_returns_401(self):
        client = anon_client(self.tenant)
        resp = client.get(detail_url(self.integration.pk))
        self.assertEqual(resp.status_code, 401, "Unauthenticated detail must be 401")

    def test_teacher_cannot_list_integrations(self):
        client = auth_client(self.teacher, self.tenant)
        resp = client.get(LIST_URL)
        self.assertEqual(
            resp.status_code, 403,
            "TEACHER must not access chat-integrations list",
        )

    def test_teacher_cannot_create_integration(self):
        client = auth_client(self.teacher, self.tenant)
        resp = client.post(
            LIST_URL,
            {"provider": "slack", "display_name": "X", "webhook_url": SLACK_WEBHOOK},
            format="json",
        )
        self.assertEqual(
            resp.status_code, 403,
            "TEACHER must not create chat integrations",
        )

    def test_teacher_cannot_delete_integration(self):
        client = auth_client(self.teacher, self.tenant)
        resp = client.delete(detail_url(self.integration.pk))
        self.assertEqual(
            resp.status_code, 403,
            "TEACHER must not delete chat integrations",
        )

    def test_admin_can_list_integrations(self):
        client = auth_client(self.admin, self.tenant)
        resp = client.get(LIST_URL)
        self.assertEqual(resp.status_code, 200, "SCHOOL_ADMIN must be able to list integrations")


# ---------------------------------------------------------------------------
# 2. List endpoint
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=ALLOWED_HOSTS, PLATFORM_DOMAIN=PLATFORM_DOMAIN)
@pytest.mark.django_db
class TestChatIntegrationList(TestCase):
    """GET /api/v1/admin/chat-integrations/ — list and tenant isolation."""

    def setUp(self):
        self.tenant = make_tenant()
        self.admin = make_user(self.tenant, role="SCHOOL_ADMIN")
        self.client = auth_client(self.admin, self.tenant)

    def test_empty_list_returns_200_empty_array(self):
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, [])

    def test_list_returns_own_integrations(self):
        make_integration(self.tenant, user=self.admin)
        make_integration(self.tenant, user=self.admin)
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 2)

    def test_list_does_not_return_other_tenant_integrations(self):
        """Tenant isolation: other tenant's integrations must not appear."""
        other_tenant = make_tenant()
        other_admin = make_user(other_tenant, role="SCHOOL_ADMIN")
        make_integration(other_tenant, user=other_admin)

        # Our tenant has no integrations
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, [], "Must not return other tenant's integrations")

    def test_list_response_masks_webhook_url(self):
        """webhook_url must NEVER appear in list response (only masked version)."""
        make_integration(self.tenant, user=self.admin, webhook_url=SLACK_WEBHOOK)
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, 200)
        item = resp.data[0]
        # Masked URL field should exist and be non-empty (not silently empty)
        self.assertIn("webhook_url_masked", item, "List must include masked URL field")
        self.assertTrue(item["webhook_url_masked"], "webhook_url_masked must be non-empty")
        # The masked value must contain asterisks
        masked = item["webhook_url_masked"]
        self.assertIn("*", masked, "Masked URL should contain asterisks")
        # Full plaintext URL must NOT appear anywhere in the serialized response
        self.assertNotIn("webhook_url_encrypted", str(item))
        self.assertNotIn(SLACK_WEBHOOK, str(item), "Plaintext webhook URL must not appear in list response")

    def test_list_includes_soft_deleted_integration(self):
        """
        Behavior-pin: the list endpoint queryset has no is_active=True filter.
        Soft-deleted (is_active=False) integrations STILL appear in list responses.

        This test documents the current contract. If future work adds an is_active
        filter to the list queryset, this test will fail and should be updated to
        test_list_excludes_soft_deleted instead.
        """
        integration = make_integration(self.tenant, user=self.admin)
        # Soft-delete: set is_active=False
        integration.is_active = False
        integration.save(update_fields=["is_active"])

        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, 200)
        # Soft-deleted integration still appears (no is_active filter on queryset)
        ids_in_response = [str(item["id"]) for item in resp.data]
        self.assertIn(
            str(integration.id),
            ids_in_response,
            "Soft-deleted integration appears in list (queryset has no is_active filter)",
        )


# ---------------------------------------------------------------------------
# 3. Create endpoint
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=ALLOWED_HOSTS, PLATFORM_DOMAIN=PLATFORM_DOMAIN)
@pytest.mark.django_db
class TestChatIntegrationCreate(TestCase):
    """POST /api/v1/admin/chat-integrations/ — create integration."""

    def setUp(self):
        self.tenant = make_tenant()
        self.admin = make_user(self.tenant, role="SCHOOL_ADMIN")
        self.client = auth_client(self.admin, self.tenant)

    def test_create_slack_integration_returns_201(self):
        resp = self.client.post(
            LIST_URL,
            {
                "provider": ChatIntegration.PROVIDER_SLACK,
                "display_name": "My Slack Channel",
                "webhook_url": SLACK_WEBHOOK,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, f"Create must return 201, got {resp.status_code}")
        self.assertEqual(resp.data["provider"], "slack")
        self.assertEqual(resp.data["display_name"], "My Slack Channel")

    def test_create_teams_integration_returns_201(self):
        resp = self.client.post(
            LIST_URL,
            {
                "provider": ChatIntegration.PROVIDER_TEAMS,
                "display_name": "My Teams Channel",
                "webhook_url": TEAMS_WEBHOOK,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["provider"], "teams")

    def test_create_without_webhook_url_returns_400(self):
        resp = self.client.post(
            LIST_URL,
            {
                "provider": "slack",
                "display_name": "No Webhook",
                # webhook_url missing
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400, "Missing webhook_url must return 400")

    def test_create_with_ssrf_url_returns_400(self):
        """Webhook URL pointing to private/internal hosts must be rejected (SSRF protection)."""
        resp = self.client.post(
            LIST_URL,
            {
                "provider": "slack",
                "display_name": "SSRF Test",
                "webhook_url": "https://hooks.slack.com.evil.example.com/ssrf",
            },
            format="json",
        )
        self.assertEqual(
            resp.status_code, 400,
            "SSRF webhook URL must be rejected with 400 (DRF validation error)",
        )

    def test_created_integration_belongs_to_request_tenant(self):
        """Integration created must be scoped to the request tenant, not any other."""
        resp = self.client.post(
            LIST_URL,
            {
                "provider": "slack",
                "display_name": "Tenant-scoped Channel",
                "webhook_url": SLACK_WEBHOOK,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        integration_id = resp.data["id"]
        integration = ChatIntegration.objects.all_tenants().get(pk=integration_id)
        self.assertEqual(integration.tenant, self.tenant)

    def test_created_integration_webhook_url_not_in_response(self):
        """Plaintext webhook_url must not be returned after creation."""
        resp = self.client.post(
            LIST_URL,
            {
                "provider": "slack",
                "display_name": "Secret Webhook",
                "webhook_url": SLACK_WEBHOOK,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        # The full SLACK_WEBHOOK URL must not appear in the response body
        self.assertNotIn(
            SLACK_WEBHOOK,
            str(resp.data),
            "Plaintext webhook URL must not be returned in response",
        )


# ---------------------------------------------------------------------------
# 4. Detail endpoint (GET, PATCH, DELETE)
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=ALLOWED_HOSTS, PLATFORM_DOMAIN=PLATFORM_DOMAIN)
@pytest.mark.django_db
class TestChatIntegrationDetail(TestCase):
    """GET/PATCH/DELETE /api/v1/admin/chat-integrations/{pk}/."""

    def setUp(self):
        self.tenant = make_tenant()
        self.admin = make_user(self.tenant, role="SCHOOL_ADMIN")
        self.integration = make_integration(self.tenant, user=self.admin)
        self.client = auth_client(self.admin, self.tenant)

    def test_get_returns_200_with_integration_data(self):
        resp = self.client.get(detail_url(self.integration.pk))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(str(resp.data["id"]), str(self.integration.pk))
        self.assertEqual(resp.data["provider"], self.integration.provider)
        self.assertEqual(resp.data["display_name"], self.integration.display_name)

    def test_get_nonexistent_returns_404(self):
        resp = self.client.get(detail_url(uuid.uuid4()))
        self.assertEqual(resp.status_code, 404)

    def test_patch_display_name_returns_200(self):
        resp = self.client.patch(
            detail_url(self.integration.pk),
            {"display_name": "Updated Name"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["display_name"], "Updated Name")
        self.integration.refresh_from_db()
        self.assertEqual(self.integration.display_name, "Updated Name")

    def test_delete_soft_deletes_integration(self):
        """DELETE must set is_active=False (soft-delete), not hard-delete the row."""
        resp = self.client.delete(detail_url(self.integration.pk))
        self.assertEqual(resp.status_code, 204)

        # Row still exists in DB
        self.integration.refresh_from_db()
        self.assertFalse(
            self.integration.is_active,
            "DELETE must soft-delete (is_active=False), not hard-delete",
        )

    def test_delete_nonexistent_returns_404(self):
        resp = self.client.delete(detail_url(uuid.uuid4()))
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# 5. Cross-tenant isolation at HTTP level
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=ALLOWED_HOSTS, PLATFORM_DOMAIN=PLATFORM_DOMAIN)
@pytest.mark.django_db
class TestChatIntegrationCrossTenantIsolation(TestCase):
    """
    Cross-tenant isolation: admin from tenant A must not access tenant B's integrations.

    The view must return 404 (not 403) to avoid leaking whether the integration
    exists in another tenant.
    """

    def setUp(self):
        self.tenant_a = make_tenant()
        self.tenant_b = make_tenant()
        self.admin_a = make_user(self.tenant_a, role="SCHOOL_ADMIN")
        self.admin_b = make_user(self.tenant_b, role="SCHOOL_ADMIN")
        self.integration_b = make_integration(self.tenant_b, user=self.admin_b)
        self.client_a = auth_client(self.admin_a, self.tenant_a)

    def test_admin_a_cannot_read_tenant_b_integration_via_http(self):
        """GET on tenant B's integration with tenant A credentials → 404."""
        resp = self.client_a.get(detail_url(self.integration_b.pk))
        self.assertEqual(
            resp.status_code, 404,
            "Cross-tenant GET must return 404 (no 403 enumeration leak)",
        )

    def test_admin_a_cannot_patch_tenant_b_integration(self):
        """PATCH on tenant B's integration with tenant A credentials → 404."""
        resp = self.client_a.patch(
            detail_url(self.integration_b.pk),
            {"display_name": "Hacked"},
            format="json",
        )
        self.assertEqual(
            resp.status_code, 404,
            "Cross-tenant PATCH must return 404",
        )
        # Verify nothing changed
        self.integration_b.refresh_from_db()
        self.assertNotEqual(self.integration_b.display_name, "Hacked")

    def test_admin_a_cannot_delete_tenant_b_integration(self):
        """DELETE on tenant B's integration with tenant A credentials → 404."""
        resp = self.client_a.delete(detail_url(self.integration_b.pk))
        self.assertEqual(
            resp.status_code, 404,
            "Cross-tenant DELETE must return 404",
        )
        # Integration B must still be active
        self.integration_b.refresh_from_db()
        self.assertTrue(
            self.integration_b.is_active,
            "Cross-tenant DELETE must not modify the target integration",
        )

    def test_admin_a_list_does_not_include_tenant_b_items(self):
        """List for tenant A must not include tenant B's integrations."""
        # Give tenant A one of its own
        make_integration(self.tenant_a, user=self.admin_a)

        resp = self.client_a.get(LIST_URL)
        self.assertEqual(resp.status_code, 200)

        returned_ids = [str(item["id"]) for item in resp.data]
        self.assertNotIn(
            str(self.integration_b.pk),
            returned_ids,
            "Tenant B integration must not appear in Tenant A's list",
        )


# ---------------------------------------------------------------------------
# 6. Delivery history endpoint
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=ALLOWED_HOSTS, PLATFORM_DOMAIN=PLATFORM_DOMAIN)
@pytest.mark.django_db
class TestChatDeliveryList(TestCase):
    """GET /api/v1/admin/chat-integrations/{pk}/deliveries/."""

    def setUp(self):
        self.tenant = make_tenant()
        self.admin = make_user(self.tenant, role="SCHOOL_ADMIN")
        self.integration = make_integration(self.tenant, user=self.admin)
        self.client = auth_client(self.admin, self.tenant)

    def test_empty_deliveries_returns_200_empty_list(self):
        resp = self.client.get(deliveries_url(self.integration.pk))
        self.assertEqual(resp.status_code, 200)
        # Response is a list or paginated result
        data = resp.data
        if isinstance(data, dict):
            # Paginated
            results = data.get("results", [])
        else:
            results = data
        self.assertEqual(results, [])

    def test_deliveries_for_integration_are_returned(self):
        ChatDelivery.objects.create(
            integration=self.integration,
            notification_id=uuid.uuid4(),
            notification_type="COURSE_PUBLISHED",
            payload_json={"title": "Test Course"},
            status=ChatDelivery.STATUS_SENT,
        )

        resp = self.client.get(deliveries_url(self.integration.pk))
        self.assertEqual(resp.status_code, 200)
        data = resp.data
        if isinstance(data, dict):
            results = data.get("results", [])
        else:
            results = data
        self.assertGreaterEqual(len(results), 1)

    def test_deliveries_endpoint_returns_404_for_nonexistent_integration(self):
        resp = self.client.get(deliveries_url(uuid.uuid4()))
        self.assertEqual(resp.status_code, 404)

    def test_teacher_cannot_access_deliveries(self):
        teacher = make_user(self.tenant, role="TEACHER")
        client = auth_client(teacher, self.tenant)
        resp = client.get(deliveries_url(self.integration.pk))
        self.assertEqual(resp.status_code, 403)

    def test_admin_cannot_access_other_tenant_deliveries(self):
        """
        Cross-tenant isolation: admin from tenant A must get 404 when requesting
        delivery history for an integration belonging to tenant B.

        This prevents enumeration of another tenant's notification history.
        """
        other_tenant = make_tenant()
        other_admin = make_user(other_tenant, role="SCHOOL_ADMIN")
        other_integration = make_integration(other_tenant, user=other_admin)

        # Add a delivery to other tenant's integration to ensure there is data
        ChatDelivery.objects.create(
            integration=other_integration,
            notification_id=uuid.uuid4(),
            notification_type="COURSE_PUBLISHED",
            payload_json={"title": "Secret Course"},
            status=ChatDelivery.STATUS_SENT,
        )

        # Tenant A's admin tries to access tenant B's deliveries
        resp = self.client.get(deliveries_url(other_integration.pk))
        self.assertEqual(
            resp.status_code, 404,
            "Cross-tenant deliveries access must return 404 (no 403 enumeration leak)",
        )


# ---------------------------------------------------------------------------
# 7. Routing rules endpoint
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=ALLOWED_HOSTS, PLATFORM_DOMAIN=PLATFORM_DOMAIN)
@pytest.mark.django_db
class TestChatRoutingRules(TestCase):
    """GET/POST /api/v1/admin/chat-integrations/{pk}/rules/."""

    def setUp(self):
        self.tenant = make_tenant()
        self.admin = make_user(self.tenant, role="SCHOOL_ADMIN")
        self.integration = make_integration(self.tenant, user=self.admin)
        self.client = auth_client(self.admin, self.tenant)

    def test_list_empty_rules_returns_200(self):
        resp = self.client.get(rules_url(self.integration.pk))
        self.assertEqual(resp.status_code, 200)

    def test_create_routing_rule_returns_201(self):
        resp = self.client.post(
            rules_url(self.integration.pk),
            {"notification_type": "COURSE_PUBLISHED"},
            format="json",
        )
        self.assertEqual(
            resp.status_code, 201,
            f"Creating routing rule must return 201 Created, got {resp.status_code}: {resp.data}",
        )

    def test_routing_rule_cross_tenant_integration_returns_404(self):
        """Rules endpoint on another tenant's integration → 404."""
        other_tenant = make_tenant()
        other_admin = make_user(other_tenant, role="SCHOOL_ADMIN")
        other_integration = make_integration(other_tenant, user=other_admin)

        resp = self.client.get(rules_url(other_integration.pk))
        self.assertEqual(
            resp.status_code, 404,
            "Cross-tenant rules access must return 404",
        )

    def test_delete_routing_rule_returns_204(self):
        """DELETE on a routing rule must return 204 No Content and remove the rule."""
        # Create a rule first
        create_resp = self.client.post(
            rules_url(self.integration.pk),
            {"notification_type": "COURSE_PUBLISHED"},
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201)
        rule_pk = create_resp.data["id"]

        rule_detail = f"/api/v1/admin/chat-integrations/{self.integration.pk}/rules/{rule_pk}/"
        delete_resp = self.client.delete(rule_detail)
        self.assertEqual(
            delete_resp.status_code, 204,
            f"DELETE routing rule must return 204, got {delete_resp.status_code}",
        )

        # Verify rule is gone
        get_resp = self.client.get(rule_detail)
        self.assertEqual(get_resp.status_code, 404, "Deleted rule must return 404 on GET")

    def test_delete_routing_rule_cross_tenant_returns_404(self):
        """
        Cross-tenant isolation: admin from tenant A cannot delete a routing rule
        belonging to tenant B's integration. Must return 404 (no 403 enumeration leak).
        """
        other_tenant = make_tenant()
        other_admin = make_user(other_tenant, role="SCHOOL_ADMIN")
        other_integration = make_integration(other_tenant, user=other_admin)

        # Create a rule on other tenant's integration using other admin's client
        other_client = auth_client(other_admin, other_tenant)
        create_resp = other_client.post(
            rules_url(other_integration.pk),
            {"notification_type": "COURSE_PUBLISHED"},
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201)
        rule_pk = create_resp.data["id"]

        # Attempt to delete using tenant A's admin (wrong tenant)
        rule_detail = f"/api/v1/admin/chat-integrations/{other_integration.pk}/rules/{rule_pk}/"
        delete_resp = self.client.delete(rule_detail)
        self.assertEqual(
            delete_resp.status_code, 404,
            "Cross-tenant rule DELETE must return 404 (no enumeration leak)",
        )

        # Verify the rule still exists (was NOT deleted)
        still_exists = ChatRoutingRule.objects.filter(id=rule_pk).exists()
        self.assertTrue(still_exists, "Cross-tenant DELETE must not remove the target rule")
