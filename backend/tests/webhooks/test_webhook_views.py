# tests/webhooks/test_webhook_views.py
"""
Tests for webhook management API endpoints.

Covers:
- GET/POST /api/v1/webhooks/           — list + create
- GET/PUT/DELETE /api/v1/webhooks/<id>/— detail operations
- POST /api/v1/webhooks/<id>/secret/   — regenerate HMAC secret
- GET /api/v1/webhooks/<id>/deliveries/— delivery history
- GET /api/v1/webhooks/events/         — available event types

Security:
- Role-based access (admin-only)
- Cross-tenant isolation (admin cannot access another tenant's webhooks)
"""

import uuid

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.webhooks.models import WebhookEndpoint, WebhookDelivery


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant(name, subdomain):
    return Tenant.objects.create(
        name=name, slug=subdomain, subdomain=subdomain,
        email=f"{subdomain}@example.com", is_active=True,
    )


def _make_user(email, tenant, role="SCHOOL_ADMIN"):
    return User.objects.create_user(
        email=email, password="Pass!123",
        first_name="Test", last_name="User",
        tenant=tenant, role=role, is_active=True,
    )


def _client_for(user, tenant_subdomain):
    c = APIClient()
    c.force_authenticate(user=user)
    c.defaults["HTTP_HOST"] = f"{tenant_subdomain}.lms.com"
    return c


def _anon_client(tenant_subdomain):
    c = APIClient()
    c.defaults["HTTP_HOST"] = f"{tenant_subdomain}.lms.com"
    return c


_BASE = "/api/v1/webhooks/"
_VALID_URL = "https://hooks.example.com/lms"


# ===========================================================================
# 1. List & Create
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class WebhookListCreateTestCase(TestCase):

    def setUp(self):
        self.tenant = _make_tenant("List School", "listhooks")
        self.admin = _make_user("admin@listhooks.com", self.tenant)
        self.teacher = _make_user("teacher@listhooks.com", self.tenant, role="TEACHER")

    # --- Authentication & Authorization ---

    def test_list_requires_authentication(self):
        c = _anon_client("listhooks")
        r = c.get(_BASE)
        self.assertEqual(r.status_code, 401)

    def test_list_forbidden_for_teacher_role(self):
        c = _client_for(self.teacher, "listhooks")
        r = c.get(_BASE)
        self.assertEqual(r.status_code, 403)

    def test_list_allowed_for_admin(self):
        c = _client_for(self.admin, "listhooks")
        r = c.get(_BASE)
        self.assertEqual(r.status_code, 200)

    def test_list_returns_empty_initially(self):
        c = _client_for(self.admin, "listhooks")
        r = c.get(_BASE)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, [])

    def test_list_returns_created_webhooks(self):
        WebhookEndpoint.objects.create(
            tenant=self.tenant, name="Test Hook",
            url=_VALID_URL, events=["course.created"],
            created_by=self.admin,
        )
        c = _client_for(self.admin, "listhooks")
        r = c.get(_BASE)
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]["name"], "Test Hook")

    # --- Create ---

    def test_create_with_valid_data_returns_201(self):
        c = _client_for(self.admin, "listhooks")
        r = c.post(_BASE, {
            "name": "My Webhook",
            "url": _VALID_URL,
            "events": ["course.created"],
        }, format="json")
        self.assertEqual(r.status_code, 201)

    def test_create_returns_secret_in_response(self):
        """Secret is only exposed at creation time for initial setup."""
        c = _client_for(self.admin, "listhooks")
        r = c.post(_BASE, {
            "name": "Secret Test",
            "url": _VALID_URL,
            "events": ["user.registered"],
        }, format="json")
        self.assertEqual(r.status_code, 201)
        secret = r.data.get("secret", "")
        self.assertGreater(len(secret), 20, "Secret should be a non-trivial hex string")

    def test_create_requires_name(self):
        c = _client_for(self.admin, "listhooks")
        r = c.post(_BASE, {
            "url": _VALID_URL, "events": ["course.created"]
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("name", str(r.data).lower())

    def test_create_requires_url(self):
        c = _client_for(self.admin, "listhooks")
        r = c.post(_BASE, {
            "name": "No URL", "events": ["course.created"]
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_create_requires_events(self):
        c = _client_for(self.admin, "listhooks")
        r = c.post(_BASE, {
            "name": "No Events", "url": _VALID_URL, "events": []
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_create_with_invalid_event_type_returns_400(self):
        c = _client_for(self.admin, "listhooks")
        r = c.post(_BASE, {
            "name": "Bad Events",
            "url": _VALID_URL,
            "events": ["made.up.event"],
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("valid_events", r.data)

    def test_create_with_wildcard_event_accepted(self):
        """'*' is a special wildcard event that subscribes to all events."""
        c = _client_for(self.admin, "listhooks")
        r = c.post(_BASE, {
            "name": "Wildcard",
            "url": _VALID_URL,
            "events": ["*"],
        }, format="json")
        self.assertEqual(r.status_code, 201)

    # --- SSRF Protection ---

    def test_create_with_http_url_returns_400(self):
        c = _client_for(self.admin, "listhooks")
        r = c.post(_BASE, {
            "name": "HTTP Webhook",
            "url": "http://example.com/webhook",
            "events": ["course.created"],
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("HTTPS", r.data.get("error", ""))

    def test_create_with_localhost_url_returns_400(self):
        c = _client_for(self.admin, "listhooks")
        r = c.post(_BASE, {
            "name": "Localhost SSRF",
            "url": "https://localhost/steal",
            "events": ["user.registered"],
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_create_with_private_ip_returns_400(self):
        c = _client_for(self.admin, "listhooks")
        r = c.post(_BASE, {
            "name": "Private IP SSRF",
            "url": "https://192.168.1.1/steal",
            "events": ["user.registered"],
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_create_with_docker_service_name_returns_400(self):
        c = _client_for(self.admin, "listhooks")
        r = c.post(_BASE, {
            "name": "Docker SSRF",
            "url": "https://redis/steal",
            "events": ["course.created"],
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_create_forbidden_for_teacher(self):
        c = _client_for(self.teacher, "listhooks")
        r = c.post(_BASE, {
            "name": "Teacher Hook",
            "url": _VALID_URL,
            "events": ["course.created"],
        }, format="json")
        self.assertEqual(r.status_code, 403)


# ===========================================================================
# 2. Detail (GET / PUT / DELETE)
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class WebhookDetailTestCase(TestCase):

    def setUp(self):
        self.tenant = _make_tenant("Detail School", "detailhooks")
        self.admin = _make_user("admin@detailhooks.com", self.tenant)
        self.endpoint = WebhookEndpoint.objects.create(
            tenant=self.tenant,
            name="Existing Webhook",
            url=_VALID_URL,
            events=["course.created"],
            created_by=self.admin,
        )
        self.client = _client_for(self.admin, "detailhooks")

    def _url(self, pk=None):
        pk = pk or self.endpoint.id
        return f"/api/v1/webhooks/{pk}/"

    def test_get_detail_returns_200_and_correct_data(self):
        r = self.client.get(self._url())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["name"], "Existing Webhook")
        self.assertEqual(r.data["url"], _VALID_URL)

    def test_get_nonexistent_webhook_returns_404(self):
        r = self.client.get(f"/api/v1/webhooks/{uuid.uuid4()}/")
        self.assertEqual(r.status_code, 404)

    def test_update_name_via_put(self):
        r = self.client.put(self._url(), {"name": "Renamed"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["name"], "Renamed")
        self.endpoint.refresh_from_db()
        self.assertEqual(self.endpoint.name, "Renamed")

    def test_update_events_via_put(self):
        r = self.client.put(
            self._url(),
            {"events": ["user.registered", "quiz.submitted"]},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.endpoint.refresh_from_db()
        self.assertIn("user.registered", self.endpoint.events)

    def test_update_is_active_via_put(self):
        r = self.client.put(self._url(), {"is_active": False}, format="json")
        self.assertEqual(r.status_code, 200)
        self.endpoint.refresh_from_db()
        self.assertFalse(self.endpoint.is_active)

    def test_update_url_with_ssrf_returns_400(self):
        r = self.client.put(
            self._url(), {"url": "https://localhost/steal"}, format="json"
        )
        self.assertEqual(r.status_code, 400)

    def test_update_url_with_http_returns_400(self):
        r = self.client.put(
            self._url(), {"url": "http://example.com/hook"}, format="json"
        )
        self.assertEqual(r.status_code, 400)

    def test_update_with_invalid_event_returns_400(self):
        r = self.client.put(
            self._url(), {"events": ["not.real.event"]}, format="json"
        )
        self.assertEqual(r.status_code, 400)

    def test_delete_webhook_returns_204(self):
        r = self.client.delete(self._url())
        self.assertEqual(r.status_code, 204)

    def test_delete_webhook_removes_it_from_database(self):
        endpoint_id = self.endpoint.id
        self.client.delete(self._url())
        self.assertFalse(WebhookEndpoint.objects.filter(id=endpoint_id).exists())

    def test_get_deleted_webhook_returns_404(self):
        self.client.delete(self._url())
        r = self.client.get(self._url())
        self.assertEqual(r.status_code, 404)


# ===========================================================================
# 3. Secret Regeneration
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class WebhookSecretTestCase(TestCase):

    def setUp(self):
        self.tenant = _make_tenant("Secret School", "secrethooks")
        self.admin = _make_user("admin@secrethooks.com", self.tenant)
        self.endpoint = WebhookEndpoint.objects.create(
            tenant=self.tenant,
            name="Secret Webhook",
            url=_VALID_URL,
            events=["course.created"],
            created_by=self.admin,
        )
        self.client = _client_for(self.admin, "secrethooks")

    def test_regenerate_secret_returns_200(self):
        r = self.client.post(f"/api/v1/webhooks/{self.endpoint.id}/secret/")
        self.assertEqual(r.status_code, 200)

    def test_regenerate_secret_returns_new_secret(self):
        old_secret = self.endpoint.secret
        r = self.client.post(f"/api/v1/webhooks/{self.endpoint.id}/secret/")
        new_secret = r.data.get("secret", "")
        self.assertNotEqual(new_secret, old_secret)
        self.assertGreater(len(new_secret), 20)

    def test_regenerate_secret_persists_to_database(self):
        r = self.client.post(f"/api/v1/webhooks/{self.endpoint.id}/secret/")
        new_secret = r.data["secret"]
        self.endpoint.refresh_from_db()
        self.assertEqual(self.endpoint.secret, new_secret)

    def test_regenerate_secret_for_nonexistent_endpoint_returns_404(self):
        r = self.client.post(f"/api/v1/webhooks/{uuid.uuid4()}/secret/")
        self.assertEqual(r.status_code, 404)


# ===========================================================================
# 4. Deliveries
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class WebhookDeliveriesTestCase(TestCase):

    def setUp(self):
        self.tenant = _make_tenant("Delivery School", "deliveryhooks")
        self.admin = _make_user("admin@deliveryhooks.com", self.tenant)
        self.endpoint = WebhookEndpoint.objects.create(
            tenant=self.tenant,
            name="Delivery Webhook",
            url=_VALID_URL,
            events=["course.created"],
            created_by=self.admin,
        )
        self.client = _client_for(self.admin, "deliveryhooks")

    def test_deliveries_list_returns_200(self):
        r = self.client.get(f"/api/v1/webhooks/{self.endpoint.id}/deliveries/")
        self.assertEqual(r.status_code, 200)

    def test_deliveries_list_empty_initially(self):
        r = self.client.get(f"/api/v1/webhooks/{self.endpoint.id}/deliveries/")
        self.assertEqual(list(r.data), [])

    def test_deliveries_list_includes_existing_deliveries(self):
        WebhookDelivery.objects.create(
            endpoint=self.endpoint,
            event_type="course.created",
            payload={"test": True},
            status="success",
        )
        r = self.client.get(f"/api/v1/webhooks/{self.endpoint.id}/deliveries/")
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]["event_type"], "course.created")
        self.assertEqual(r.data[0]["status"], "success")

    def test_deliveries_for_nonexistent_endpoint_returns_404(self):
        r = self.client.get(f"/api/v1/webhooks/{uuid.uuid4()}/deliveries/")
        self.assertEqual(r.status_code, 404)


# ===========================================================================
# 5. Events Listing
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class WebhookEventsTestCase(TestCase):

    def setUp(self):
        self.tenant = _make_tenant("Events School", "eventshooks")
        self.admin = _make_user("admin@eventshooks.com", self.tenant)
        self.client = _client_for(self.admin, "eventshooks")

    def test_events_list_returns_200(self):
        r = self.client.get("/api/v1/webhooks/events/")
        self.assertEqual(r.status_code, 200)

    def test_events_list_is_not_empty(self):
        r = self.client.get("/api/v1/webhooks/events/")
        self.assertGreater(len(r.data), 0)

    def test_events_list_contains_course_events(self):
        r = self.client.get("/api/v1/webhooks/events/")
        ids = [e["id"] for e in r.data]
        self.assertIn("course.created", ids)
        self.assertIn("course.published", ids)

    def test_events_list_contains_user_events(self):
        r = self.client.get("/api/v1/webhooks/events/")
        ids = [e["id"] for e in r.data]
        self.assertIn("user.registered", ids)

    def test_events_list_contains_progress_events(self):
        r = self.client.get("/api/v1/webhooks/events/")
        ids = [e["id"] for e in r.data]
        self.assertIn("progress.completed", ids)

    def test_events_require_admin_auth(self):
        teacher = _make_user("teacher@eventshooks.com", self.tenant, role="TEACHER")
        c = _client_for(teacher, "eventshooks")
        r = c.get("/api/v1/webhooks/events/")
        self.assertEqual(r.status_code, 403)


# ===========================================================================
# 6. Cross-Tenant Isolation
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class WebhookCrossTenantIsolationTestCase(TestCase):
    """
    P0 Security: Verify that webhook endpoints are isolated between tenants.

    An admin of tenant A must not be able to:
    - See webhooks belonging to tenant B
    - Read, update, or delete a webhook belonging to tenant B by guessing its ID
    - Create a webhook that appears in tenant B's list
    """

    def setUp(self):
        # Tenant A with its admin and webhook
        self.tenant_a = _make_tenant("Tenant Alpha", "alpha")
        self.admin_a = _make_user("admin@alpha.com", self.tenant_a)
        self.hook_a = WebhookEndpoint.objects.create(
            tenant=self.tenant_a, name="Alpha Hook",
            url="https://example.com/alpha", events=["course.created"],
            created_by=self.admin_a,
        )

        # Tenant B with its admin and webhook
        self.tenant_b = _make_tenant("Tenant Beta", "beta")
        self.admin_b = _make_user("admin@beta.com", self.tenant_b)
        self.hook_b = WebhookEndpoint.objects.create(
            tenant=self.tenant_b, name="Beta Hook",
            url="https://example.com/beta", events=["user.registered"],
            created_by=self.admin_b,
        )

    def _client_a(self):
        return _client_for(self.admin_a, "alpha")

    def _client_b(self):
        return _client_for(self.admin_b, "beta")

    def test_admin_a_cannot_access_tenant_b_via_cross_origin(self):
        """Admin A using Tenant B's subdomain must be denied (wrong tenant)."""
        c = APIClient()
        c.force_authenticate(user=self.admin_a)
        c.defaults["HTTP_HOST"] = "beta.lms.com"  # Using B's subdomain with A's creds
        r = c.get(_BASE)
        self.assertEqual(r.status_code, 403)

    def test_admin_a_list_only_sees_own_webhooks(self):
        """Admin A's webhook list must not include tenant B's webhooks."""
        r = self._client_a().get(_BASE)
        self.assertEqual(r.status_code, 200)
        names = [w["name"] for w in r.data]
        self.assertIn("Alpha Hook", names)
        self.assertNotIn("Beta Hook", names)

    def test_admin_b_list_only_sees_own_webhooks(self):
        """Admin B's webhook list must not include tenant A's webhooks."""
        r = self._client_b().get(_BASE)
        self.assertEqual(r.status_code, 200)
        names = [w["name"] for w in r.data]
        self.assertIn("Beta Hook", names)
        self.assertNotIn("Alpha Hook", names)

    def test_admin_a_cannot_get_tenant_b_webhook_by_id(self):
        """Admin A must get 404 when accessing tenant B's webhook by UUID."""
        r = self._client_a().get(f"/api/v1/webhooks/{self.hook_b.id}/")
        self.assertEqual(r.status_code, 404)

    def test_admin_a_cannot_update_tenant_b_webhook(self):
        """Admin A must not be able to PUT/rename tenant B's webhook."""
        r = self._client_a().put(
            f"/api/v1/webhooks/{self.hook_b.id}/",
            {"name": "Hijacked"},
            format="json",
        )
        self.assertEqual(r.status_code, 404)
        # Webhook B name must be unchanged
        self.hook_b.refresh_from_db()
        self.assertEqual(self.hook_b.name, "Beta Hook")

    def test_admin_a_cannot_delete_tenant_b_webhook(self):
        """Admin A must not be able to DELETE tenant B's webhook."""
        r = self._client_a().delete(f"/api/v1/webhooks/{self.hook_b.id}/")
        self.assertEqual(r.status_code, 404)
        # Webhook B must still exist
        self.assertTrue(WebhookEndpoint.objects.filter(id=self.hook_b.id).exists())

    def test_admin_a_cannot_regenerate_secret_of_tenant_b_webhook(self):
        """Admin A must not regenerate secret for tenant B's webhook."""
        old_secret = self.hook_b.secret
        r = self._client_a().post(f"/api/v1/webhooks/{self.hook_b.id}/secret/")
        self.assertEqual(r.status_code, 404)
        # Secret must not have changed
        self.hook_b.refresh_from_db()
        self.assertEqual(self.hook_b.secret, old_secret)
