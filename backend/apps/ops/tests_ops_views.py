"""tests_ops_views.py — Comprehensive tests for apps/ops/views.py

Covers:
- Authentication / authorisation walls (anonymous → 401, SCHOOL_ADMIN → 403,
  SUPER_ADMIN → 2xx)
- Response structure for key super-admin ops endpoints
- Incident lifecycle: list, acknowledge, resolve, idempotent re-resolve
- Error listing with filter parameters
- Tenant listing (overview, tenants, timeline)
- Replay cases catalog
- Actions catalog
- Weekly report CSV

All endpoints live under:
  /api/v1/super-admin/ops/<path>    — handled by apps.ops.urls (SUPER_ADMIN only)
  /api/v1/ops/<path>                — handled by apps.ops.public_urls (public ingest)
"""

from __future__ import annotations

import uuid

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.ops.models import OpsIncident, OpsRouteError
from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_tenant(subdomain: str) -> Tenant:
    return Tenant.objects.create(
        name=subdomain.replace("-", " ").title(),
        slug=subdomain,
        subdomain=subdomain,
        email=f"admin@{subdomain}.com",
        is_active=True,
    )


def _make_super_admin() -> User:
    uid = uuid.uuid4().hex[:6]
    return User.objects.create_user(
        email=f"super-{uid}@learnpuddle.com",
        password="SuperP@ss123!",
        first_name="Super",
        last_name="Admin",
        role="SUPER_ADMIN",
        is_active=True,
    )


def _make_school_admin(tenant: Tenant) -> User:
    uid = uuid.uuid4().hex[:6]
    return User.objects.create_user(
        email=f"admin-{uid}@{tenant.subdomain}.com",
        password="AdminP@ss123!",
        first_name="School",
        last_name="Admin",
        role="SCHOOL_ADMIN",
        tenant=tenant,
        is_active=True,
    )


def _make_incident(
    tenant: Tenant,
    severity: str = "P2",
    status: str = "OPEN",
    dedupe_key: str | None = None,
) -> OpsIncident:
    uid = uuid.uuid4().hex[:8]
    return OpsIncident.objects.create(
        severity=severity,
        scope="TENANT",
        tenant=tenant,
        rule_id="test_rule",
        dedupe_key=dedupe_key or f"test:{uid}",
        title="Test incident",
        description="Test description",
        status=status,
    )


def _make_route_error(tenant: Tenant, status_code: int = 500) -> OpsRouteError:
    uid = uuid.uuid4().hex[:8]
    return OpsRouteError.objects.create(
        tenant=tenant,
        portal="TENANT_ADMIN",
        tab_key="courses",
        endpoint="/api/courses/",
        method="GET",
        status_code=status_code,
        fingerprint=f"{tenant.id}:courses:{status_code}:{uid}",
        total_count=1,
        count_1h=1,
        count_24h=1,
    )


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------

SUPER_ADMIN_PREFIX = "/api/v1/super-admin/ops"


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="learnpuddle.com")
class OpsBaseTestCase(TestCase):
    def setUp(self):
        self.tenant = _make_tenant("ops-test-school")
        self.super_admin = _make_super_admin()
        self.school_admin = _make_school_admin(self.tenant)

        self.sa_client = APIClient()
        self.sa_client.force_authenticate(user=self.super_admin)

        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.school_admin)

        self.anon_client = APIClient()


# ---------------------------------------------------------------------------
# 1. Authentication / authorisation walls
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="learnpuddle.com")
class TestOpsAuthWalls(OpsBaseTestCase):
    """
    Every super-admin ops endpoint must:
    - Reject anonymous requests (401)
    - Reject SCHOOL_ADMIN requests (403)
    - Permit SUPER_ADMIN requests (200/201/2xx)
    """

    PROTECTED_ENDPOINTS = [
        ("GET", f"{SUPER_ADMIN_PREFIX}/overview/"),
        ("GET", f"{SUPER_ADMIN_PREFIX}/tenants/"),
        ("GET", f"{SUPER_ADMIN_PREFIX}/incidents/"),
        ("GET", f"{SUPER_ADMIN_PREFIX}/errors/"),
        ("GET", f"{SUPER_ADMIN_PREFIX}/replay-cases/"),
        ("GET", f"{SUPER_ADMIN_PREFIX}/actions/catalog/"),
    ]

    def test_anonymous_requests_return_401(self):
        for method, url in self.PROTECTED_ENDPOINTS:
            with self.subTest(method=method, url=url):
                resp = getattr(self.anon_client, method.lower())(url)
                self.assertEqual(
                    resp.status_code, 401,
                    f"Expected 401 for anonymous {method} {url}, got {resp.status_code}",
                )

    def test_school_admin_requests_return_403(self):
        for method, url in self.PROTECTED_ENDPOINTS:
            with self.subTest(method=method, url=url):
                resp = getattr(self.admin_client, method.lower())(url)
                self.assertEqual(
                    resp.status_code, 403,
                    f"Expected 403 for SCHOOL_ADMIN {method} {url}, got {resp.status_code}",
                )

    def test_super_admin_can_access_overview(self):
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/overview/")
        self.assertEqual(resp.status_code, 200)

    def test_super_admin_can_access_tenants(self):
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/tenants/")
        self.assertEqual(resp.status_code, 200)

    def test_super_admin_can_access_incidents(self):
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/incidents/")
        self.assertEqual(resp.status_code, 200)

    def test_super_admin_can_access_errors(self):
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/errors/")
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# 2. ops_overview — response shape
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="learnpuddle.com")
class TestOpsOverview(OpsBaseTestCase):
    """ops_overview returns platform-wide health summary."""

    def test_overview_response_contains_totals(self):
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/overview/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # Overview must include totals with health buckets
        self.assertIn("totals", data, "Expected 'totals' key in overview response")
        totals = data["totals"]
        for key in ("tenants", "healthy", "degraded", "down", "maintenance"):
            self.assertIn(key, totals, f"Expected '{key}' in overview totals")

    def test_overview_returns_open_incidents(self):
        incident = _make_incident(self.tenant, status="OPEN")
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/overview/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        incident_ids = [i["id"] for i in data.get("open_incidents", [])]
        self.assertIn(str(incident.id), incident_ids)


# ---------------------------------------------------------------------------
# 3. ops_tenants — listing and search
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="learnpuddle.com")
class TestOpsTenants(OpsBaseTestCase):
    """ops_tenants returns paginated tenant list with health snapshots."""

    def test_tenants_returns_200_with_results(self):
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/tenants/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("results", data)

    def test_tenants_includes_fixture_tenant(self):
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/tenants/")
        self.assertEqual(resp.status_code, 200)
        result_subdomains = [t["subdomain"] for t in resp.json()["results"]]
        self.assertIn(self.tenant.subdomain, result_subdomains)

    def test_tenants_search_filters_by_name(self):
        other = _make_tenant("completely-different-school")
        resp = self.sa_client.get(
            f"{SUPER_ADMIN_PREFIX}/tenants/?search={self.tenant.name[:5]}"
        )
        self.assertEqual(resp.status_code, 200)
        result_subdomains = [t["subdomain"] for t in resp.json()["results"]]
        self.assertIn(self.tenant.subdomain, result_subdomains)
        self.assertNotIn(other.subdomain, result_subdomains)

    def test_tenants_result_row_has_required_keys(self):
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/tenants/")
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertTrue(len(results) > 0, "Expected at least one tenant in results")
        row = results[0]
        for key in ("tenant_id", "name", "subdomain", "status", "failures_week"):
            self.assertIn(key, row, f"Expected key '{key}' in tenant row")


# ---------------------------------------------------------------------------
# 4. ops_incidents — listing and filters
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="learnpuddle.com")
class TestOpsIncidentsList(OpsBaseTestCase):
    """ops_incidents returns incident list with optional filters."""

    def setUp(self):
        super().setUp()
        self.open_p2 = _make_incident(self.tenant, severity="P2", status="OPEN")
        self.acked_p1 = _make_incident(self.tenant, severity="P1", status="ACKED")
        self.resolved = _make_incident(self.tenant, severity="P2", status="RESOLVED")

    def test_list_returns_200_with_results_key(self):
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/incidents/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("results", resp.json())

    def test_list_includes_open_incident(self):
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/incidents/")
        ids = [i["id"] for i in resp.json()["results"]]
        self.assertIn(str(self.open_p2.id), ids)

    def test_status_filter_open(self):
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/incidents/?status=OPEN")
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        statuses = {i["status"] for i in results}
        self.assertSetEqual(statuses, {"OPEN"}, "Status filter should only return OPEN incidents")

    def test_status_filter_resolved(self):
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/incidents/?status=RESOLVED")
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        statuses = {i["status"] for i in results}
        self.assertSetEqual(statuses, {"RESOLVED"})

    def test_severity_filter_p1(self):
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/incidents/?severity=P1")
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        severities = {i["severity"] for i in results}
        self.assertSetEqual(severities, {"P1"})

    def test_incident_row_has_required_keys(self):
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/incidents/")
        results = resp.json()["results"]
        self.assertTrue(len(results) > 0)
        row = results[0]
        for key in ("id", "severity", "status", "title", "started_at", "last_seen_at"):
            self.assertIn(key, row, f"Expected key '{key}' in incident row")


# ---------------------------------------------------------------------------
# 5. ops_incident_acknowledge / ops_incident_resolve — lifecycle
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="learnpuddle.com")
class TestOpsIncidentLifecycle(OpsBaseTestCase):
    """Incident acknowledge / resolve transitions."""

    def test_acknowledge_open_incident(self):
        incident = _make_incident(self.tenant, status="OPEN")
        resp = self.sa_client.post(
            f"{SUPER_ADMIN_PREFIX}/incidents/{incident.id}/acknowledge/",
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        incident.refresh_from_db()
        self.assertEqual(incident.status, "ACKED")
        self.assertIsNotNone(incident.acknowledged_at)
        self.assertEqual(incident.owner, self.super_admin)

    def test_acknowledge_resolved_incident_returns_400(self):
        incident = _make_incident(self.tenant, status="RESOLVED")
        resp = self.sa_client.post(
            f"{SUPER_ADMIN_PREFIX}/incidents/{incident.id}/acknowledge/",
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())

    def test_resolve_open_incident(self):
        incident = _make_incident(self.tenant, status="OPEN")
        resp = self.sa_client.post(
            f"{SUPER_ADMIN_PREFIX}/incidents/{incident.id}/resolve/",
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        incident.refresh_from_db()
        self.assertEqual(incident.status, "RESOLVED")
        self.assertIsNotNone(incident.resolved_at)
        self.assertIsNotNone(incident.mttr_seconds)

    def test_resolve_already_resolved_is_idempotent(self):
        """Resolving an already-resolved incident returns 200 (no error)."""
        incident = _make_incident(self.tenant, status="RESOLVED")
        resp = self.sa_client.post(
            f"{SUPER_ADMIN_PREFIX}/incidents/{incident.id}/resolve/",
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

    def test_resolve_acked_incident(self):
        incident = _make_incident(self.tenant, status="ACKED")
        resp = self.sa_client.post(
            f"{SUPER_ADMIN_PREFIX}/incidents/{incident.id}/resolve/",
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        incident.refresh_from_db()
        self.assertEqual(incident.status, "RESOLVED")

    def test_acknowledge_nonexistent_incident_returns_404(self):
        fake_id = uuid.uuid4()
        resp = self.sa_client.post(
            f"{SUPER_ADMIN_PREFIX}/incidents/{fake_id}/acknowledge/",
            format="json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_resolve_nonexistent_incident_returns_404(self):
        fake_id = uuid.uuid4()
        resp = self.sa_client.post(
            f"{SUPER_ADMIN_PREFIX}/incidents/{fake_id}/resolve/",
            format="json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_school_admin_cannot_acknowledge_incident(self):
        incident = _make_incident(self.tenant, status="OPEN")
        resp = self.admin_client.post(
            f"{SUPER_ADMIN_PREFIX}/incidents/{incident.id}/acknowledge/",
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_school_admin_cannot_resolve_incident(self):
        incident = _make_incident(self.tenant, status="OPEN")
        resp = self.admin_client.post(
            f"{SUPER_ADMIN_PREFIX}/incidents/{incident.id}/resolve/",
            format="json",
        )
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# 6. ops_errors — listing with filters
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="learnpuddle.com")
class TestOpsErrors(OpsBaseTestCase):
    """ops_errors returns route-error list with optional filters."""

    def setUp(self):
        super().setUp()
        self.error_500 = _make_route_error(self.tenant, status_code=500)
        self.error_429 = _make_route_error(self.tenant, status_code=429)

    def test_errors_returns_200_with_results_key(self):
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/errors/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("results", resp.json())

    def test_errors_includes_500_by_default(self):
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/errors/")
        result_ids = [r["id"] for r in resp.json()["results"]]
        self.assertIn(str(self.error_500.id), result_ids)

    def test_errors_default_excludes_non_500_429(self):
        """By default, only 429 and 500 status codes are returned."""
        error_403 = _make_route_error(self.tenant, status_code=403)
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/errors/")
        result_ids = [r["id"] for r in resp.json()["results"]]
        self.assertNotIn(str(error_403.id), result_ids)

    def test_errors_custom_status_code_filter(self):
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/errors/?status_codes=429")
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        status_codes = {r["status_code"] for r in results}
        self.assertNotIn(500, status_codes)
        self.assertIn(429, status_codes)

    def test_errors_filter_by_tenant_id(self):
        other_tenant = _make_tenant("ops-other-tenant")
        other_error = _make_route_error(other_tenant, status_code=500)
        resp = self.sa_client.get(
            f"{SUPER_ADMIN_PREFIX}/errors/?tenant_id={self.tenant.id}"
        )
        self.assertEqual(resp.status_code, 200)
        result_ids = [r["id"] for r in resp.json()["results"]]
        self.assertIn(str(self.error_500.id), result_ids)
        self.assertNotIn(str(other_error.id), result_ids)

    def test_error_detail_returns_200(self):
        resp = self.sa_client.get(
            f"{SUPER_ADMIN_PREFIX}/errors/{self.error_500.id}/"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("error_group", data)
        self.assertIn("recent_replay_steps", data)

    def test_error_detail_nonexistent_returns_404(self):
        resp = self.sa_client.get(
            f"{SUPER_ADMIN_PREFIX}/errors/{uuid.uuid4()}/"
        )
        self.assertEqual(resp.status_code, 404)

    def test_school_admin_cannot_access_errors(self):
        resp = self.admin_client.get(f"{SUPER_ADMIN_PREFIX}/errors/")
        self.assertEqual(resp.status_code, 403)

    def test_errors_result_row_has_required_keys(self):
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/errors/")
        results = resp.json()["results"]
        self.assertTrue(len(results) > 0)
        row = results[0]
        for key in ("id", "status_code", "endpoint", "method", "total_count"):
            self.assertIn(key, row, f"Expected key '{key}' in error row")


# ---------------------------------------------------------------------------
# 7. ops_replay_cases — catalog
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="learnpuddle.com")
class TestOpsReplayCases(OpsBaseTestCase):
    """ops_replay_cases returns catalog of available replay cases."""

    def test_replay_cases_returns_200(self):
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/replay-cases/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("results", resp.json())

    def test_replay_cases_portal_filter(self):
        resp = self.sa_client.get(
            f"{SUPER_ADMIN_PREFIX}/replay-cases/?portal=TENANT_ADMIN"
        )
        self.assertEqual(resp.status_code, 200)

    def test_school_admin_cannot_access_replay_cases(self):
        resp = self.admin_client.get(f"{SUPER_ADMIN_PREFIX}/replay-cases/")
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# 8. ops_actions_catalog
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="learnpuddle.com")
class TestOpsActionsCatalog(OpsBaseTestCase):
    """ops_actions_catalog returns available guarded action definitions."""

    def test_actions_catalog_returns_200(self):
        resp = self.sa_client.get(f"{SUPER_ADMIN_PREFIX}/actions/catalog/")
        self.assertEqual(resp.status_code, 200)

    def test_school_admin_cannot_access_catalog(self):
        resp = self.admin_client.get(f"{SUPER_ADMIN_PREFIX}/actions/catalog/")
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# 9. ops_tenant_timeline
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="learnpuddle.com")
class TestOpsTenantTimeline(OpsBaseTestCase):
    """ops_tenant_timeline returns per-tenant ops events / status series."""

    def test_timeline_returns_200_for_existing_tenant(self):
        resp = self.sa_client.get(
            f"{SUPER_ADMIN_PREFIX}/tenants/{self.tenant.id}/timeline/"
        )
        self.assertEqual(resp.status_code, 200)

    def test_timeline_returns_404_for_nonexistent_tenant(self):
        resp = self.sa_client.get(
            f"{SUPER_ADMIN_PREFIX}/tenants/{uuid.uuid4()}/timeline/"
        )
        self.assertEqual(resp.status_code, 404)

    def test_school_admin_cannot_access_timeline(self):
        resp = self.admin_client.get(
            f"{SUPER_ADMIN_PREFIX}/tenants/{self.tenant.id}/timeline/"
        )
        self.assertEqual(resp.status_code, 403)
