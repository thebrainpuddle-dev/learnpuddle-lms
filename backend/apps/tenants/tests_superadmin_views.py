# apps/tenants/tests_superadmin_views.py
"""
Tests for tenants/superadmin_views.py:
  - platform_stats: GET /api/v1/super-admin/stats/
  - tenant_list_create: GET/POST /api/v1/super-admin/tenants/
  - tenant_detail: GET/PATCH /api/v1/super-admin/tenants/<id>/
  - tenant_usage: GET /api/v1/super-admin/tenants/<id>/usage/

Access: SUPER_ADMIN only.
"""
import uuid
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status

from apps.tenants.models import Tenant
from apps.users.models import User


HOST = "test.lms.com"


def _tenant(name, slug, sub, email, active=True):
    return Tenant.objects.create(name=name, slug=slug, subdomain=sub, email=email, is_active=active)


def _user(email, tenant, role="SUPER_ADMIN"):
    return User.objects.create_user(
        email=email, password="Pass!1234",
        first_name="S", last_name="A",
        tenant=tenant, role=role, is_active=True,
    )


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class PlatformStatsTestCase(TestCase):
    """Tests for GET /api/v1/super-admin/stats/"""

    def setUp(self):
        self.tenant = _tenant("Super School", "ss-stats", "test", "sa@test.com")
        self.super_admin = _user("sa@test.com", self.tenant, role="SUPER_ADMIN")
        self.school_admin = _user("admin@test.com", self.tenant, role="SCHOOL_ADMIN")
        self.client = APIClient()
        self.client.force_authenticate(user=self.super_admin)

    def test_unauthenticated_returns_401(self):
        response = APIClient().get("/api/v1/super-admin/stats/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_school_admin_cannot_access_stats(self):
        client = APIClient()
        client.force_authenticate(user=self.school_admin)
        response = client.get("/api/v1/super-admin/stats/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_super_admin_can_access_stats(self):
        response = self.client.get("/api/v1/super-admin/stats/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_stats_has_total_tenants(self):
        response = self.client.get("/api/v1/super-admin/stats/", HTTP_HOST=HOST)
        self.assertIn("total_tenants", response.data)

    def test_stats_has_total_users(self):
        response = self.client.get("/api/v1/super-admin/stats/", HTTP_HOST=HOST)
        self.assertIn("total_users", response.data)

    def test_stats_has_plan_distribution(self):
        response = self.client.get("/api/v1/super-admin/stats/", HTTP_HOST=HOST)
        self.assertIn("plan_distribution", response.data)

    def test_stats_has_recent_onboards(self):
        response = self.client.get("/api/v1/super-admin/stats/", HTTP_HOST=HOST)
        self.assertIn("recent_onboards", response.data)


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class TenantListCreateTestCase(TestCase):
    """Tests for GET/POST /api/v1/super-admin/tenants/"""

    def setUp(self):
        self.tenant = _tenant("Platform School", "ss-tenants", "test", "saplt@test.com")
        self.super_admin = _user("saplt@test.com", self.tenant, role="SUPER_ADMIN")
        self.school_admin = _user("admin@plttest.com", self.tenant, role="SCHOOL_ADMIN")
        self.client = APIClient()
        self.client.force_authenticate(user=self.super_admin)

    def test_unauthenticated_returns_401(self):
        response = APIClient().get("/api/v1/super-admin/tenants/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_school_admin_cannot_list_tenants(self):
        client = APIClient()
        client.force_authenticate(user=self.school_admin)
        response = client.get("/api/v1/super-admin/tenants/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_super_admin_can_list_tenants(self):
        response = self.client.get("/api/v1/super-admin/tenants/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_tenants_filter_by_active(self):
        inactive_tenant = _tenant("Inactive", "ss-inactive", "inactive", "inact@test.com", active=False)
        response = self.client.get("/api/v1/super-admin/tenants/?is_active=false", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        for r in results:
            self.assertFalse(r["is_active"])

    def test_list_tenants_search_by_name(self):
        _tenant("Unique XYZ Tenant", "ss-unique-xyz", "uniquexyz", "xyz@test.com")
        response = self.client.get("/api/v1/super-admin/tenants/?search=Unique+XYZ", HTTP_HOST=HOST)
        results = response.data.get("results", response.data)
        self.assertTrue(any("Unique XYZ" in r["name"] for r in results))

    def test_super_admin_can_onboard_tenant(self):
        response = self.client.post(
            "/api/v1/super-admin/tenants/",
            {
                "school_name": "New School",
                "admin_email": "newschool@example.com",
                "admin_first_name": "New",
                "admin_last_name": "Admin",
                "admin_password": "StrongPass!123",
            },
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("tenant", response.data)

    def test_onboard_tenant_missing_fields_returns_400(self):
        response = self.client.post(
            "/api/v1/super-admin/tenants/",
            {"school_name": "Incomplete"},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class TenantDetailSuperadminTestCase(TestCase):
    """Tests for GET/PATCH /api/v1/super-admin/tenants/<id>/"""

    def setUp(self):
        self.tenant = _tenant("SA Detail School", "ss-det", "test", "sadet@test.com")
        self.super_admin = _user("sadet@test.com", self.tenant, role="SUPER_ADMIN")
        self.other_tenant = _tenant("Other Tenant", "ss-other", "other", "other@test.com")
        self.client = APIClient()
        self.client.force_authenticate(user=self.super_admin)

    def test_super_admin_can_get_tenant_detail(self):
        response = self.client.get(f"/api/v1/super-admin/tenants/{self.other_tenant.id}/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_nonexistent_tenant_returns_404(self):
        response = self.client.get(f"/api/v1/super-admin/tenants/{uuid.uuid4()}/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_super_admin_can_patch_tenant(self):
        response = self.client.patch(
            f"/api/v1/super-admin/tenants/{self.other_tenant.id}/",
            {"is_active": False},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class TenantUsageTestCase(TestCase):
    """Tests for GET /api/v1/super-admin/tenants/<id>/usage/"""

    def setUp(self):
        self.tenant = _tenant("Usage School", "ss-usage", "test", "sausage@test.com")
        self.super_admin = _user("sausage@test.com", self.tenant, role="SUPER_ADMIN")
        self.target_tenant = _tenant("Target School", "ss-target", "target", "target@test.com")
        self.client = APIClient()
        self.client.force_authenticate(user=self.super_admin)

    def test_super_admin_can_get_tenant_usage(self):
        response = self.client.get(
            f"/api/v1/super-admin/tenants/{self.target_tenant.id}/usage/", HTTP_HOST=HOST
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_usage_for_nonexistent_tenant_returns_404(self):
        response = self.client.get(
            f"/api/v1/super-admin/tenants/{uuid.uuid4()}/usage/", HTTP_HOST=HOST
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_school_admin_cannot_access_usage(self):
        school_admin = _user("admin@ssusage.com", self.tenant, role="SCHOOL_ADMIN")
        client = APIClient()
        client.force_authenticate(user=school_admin)
        response = client.get(
            f"/api/v1/super-admin/tenants/{self.target_tenant.id}/usage/", HTTP_HOST=HOST
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
