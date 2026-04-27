# apps/tenants/tests_views_extended.py
"""
Tests for tenant-facing public and admin views:
  - tenant_theme_view (GET /api/v1/tenants/theme/)
  - tenant_me_view (GET /api/v1/tenants/me/)
  - tenant_config_view (GET /api/v1/tenants/config/)
  - tenant_stats_view (GET /api/v1/tenants/stats/)
  - tenant_analytics_view (GET /api/v1/tenants/analytics/)
  - tenant_settings_view (GET/PATCH /api/v1/tenants/settings/)
"""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status

from apps.tenants.models import Tenant
from apps.users.models import User


HOST = "test.lms.com"


def _tenant(name, slug, sub, email, active=True):
    return Tenant.objects.create(name=name, slug=slug, subdomain=sub, email=email, is_active=active)


def _user(email, tenant, role="TEACHER"):
    return User.objects.create_user(
        email=email, password="Pass!1234",
        first_name="T", last_name="U",
        tenant=tenant, role=role, is_active=True,
    )


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class TenantThemeViewTestCase(TestCase):
    """Tests for GET /api/v1/tenants/theme/ (public, no auth)"""

    def setUp(self):
        self.tenant = _tenant("Theme School", "ts-theme", "test", "theme@test.com")
        self.client = APIClient()

    def test_active_tenant_returns_tenant_found_true(self):
        response = self.client.get("/api/v1/tenants/theme/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["tenant_found"])

    def test_inactive_tenant_returns_tenant_found_false(self):
        inactive = _tenant("Inactive", "ts-inactive", "inactive", "inactive@test.com", active=False)
        response = self.client.get("/api/v1/tenants/theme/", HTTP_HOST="inactive.lms.com")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["tenant_found"])

    def test_unknown_subdomain_returns_not_found(self):
        response = self.client.get("/api/v1/tenants/theme/", HTTP_HOST="unknown.lms.com")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["tenant_found"])
        self.assertEqual(response.data["reason"], "not_found")

    def test_localhost_returns_platform_root_theme(self):
        response = self.client.get("/api/v1/tenants/theme/", HTTP_HOST="localhost")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["tenant_found"])
        self.assertEqual(response.data.get("name"), "LearnPuddle")

    def test_theme_has_primary_color(self):
        response = self.client.get("/api/v1/tenants/theme/", HTTP_HOST=HOST)
        self.assertIn("primary_color", response.data)


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class TenantMeViewTestCase(TestCase):
    """Tests for GET /api/v1/tenants/me/"""

    def setUp(self):
        self.tenant = _tenant("Me School", "ts-me", "test", "me@test.com")
        self.teacher = _user("teacher@me.com", self.tenant)
        self.client = APIClient()
        self.client.force_authenticate(user=self.teacher)

    def test_unauthenticated_returns_401(self):
        response = APIClient().get("/api/v1/tenants/me/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_returns_200(self):
        response = self.client.get("/api/v1/tenants/me/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_me_returns_tenant_name(self):
        response = self.client.get("/api/v1/tenants/me/", HTTP_HOST=HOST)
        self.assertEqual(response.data["name"], "Me School")


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class TenantConfigViewTestCase(TestCase):
    """Tests for GET /api/v1/tenants/config/"""

    def setUp(self):
        self.tenant = _tenant("Config School", "ts-config", "test", "config@test.com")
        self.teacher = _user("teacher@config.com", self.tenant, role="TEACHER")
        self.admin = _user("admin@config.com", self.tenant, role="SCHOOL_ADMIN")

    def test_unauthenticated_returns_401(self):
        response = APIClient().get("/api/v1/tenants/config/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_teacher_can_access_config(self):
        client = APIClient()
        client.force_authenticate(user=self.teacher)
        response = client.get("/api/v1/tenants/config/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("features", response.data)

    def test_admin_config_includes_limits(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        response = client.get("/api/v1/tenants/config/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("limits", response.data)

    def test_teacher_config_excludes_limits(self):
        client = APIClient()
        client.force_authenticate(user=self.teacher)
        response = client.get("/api/v1/tenants/config/", HTTP_HOST=HOST)
        self.assertNotIn("limits", response.data)

    def test_config_has_plan_field(self):
        client = APIClient()
        client.force_authenticate(user=self.teacher)
        response = client.get("/api/v1/tenants/config/", HTTP_HOST=HOST)
        self.assertIn("plan", response.data)


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class TenantStatsViewTestCase(TestCase):
    """Tests for GET /api/v1/tenants/stats/"""

    def setUp(self):
        self.tenant = _tenant("Stats School", "ts-stats", "test", "stats@test.com")
        self.admin = _user("admin@stats.com", self.tenant, role="SCHOOL_ADMIN")
        self.teacher = _user("teacher@stats.com", self.tenant, role="TEACHER")

    def test_unauthenticated_returns_401(self):
        response = APIClient().get("/api/v1/tenants/stats/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_can_access_stats(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        response = client.get("/api/v1/tenants/stats/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_teacher_cannot_access_stats(self):
        client = APIClient()
        client.force_authenticate(user=self.teacher)
        response = client.get("/api/v1/tenants/stats/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class TenantAnalyticsViewTestCase(TestCase):
    """Tests for GET /api/v1/tenants/analytics/"""

    def setUp(self):
        self.tenant = _tenant("Analytics School", "ts-analytics", "test", "analytics@test.com")
        self.admin = _user("admin@analytics.com", self.tenant, role="SCHOOL_ADMIN")
        self.teacher = _user("teacher@analytics.com", self.tenant, role="TEACHER")

    def test_unauthenticated_returns_401(self):
        response = APIClient().get("/api/v1/tenants/analytics/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_can_access_analytics(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        response = client.get("/api/v1/tenants/analytics/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_teacher_cannot_access_analytics(self):
        client = APIClient()
        client.force_authenticate(user=self.teacher)
        response = client.get("/api/v1/tenants/analytics/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_analytics_with_months_param(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        response = client.get("/api/v1/tenants/analytics/?months=12", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_analytics_invalid_months_defaults_gracefully(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        response = client.get("/api/v1/tenants/analytics/?months=bad", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class TenantSettingsViewTestCase(TestCase):
    """Tests for GET/PATCH /api/v1/tenants/settings/"""

    def setUp(self):
        self.tenant = _tenant("Settings School", "ts-settings", "test", "settings@test.com")
        self.admin = _user("admin@settings.com", self.tenant, role="SCHOOL_ADMIN")
        self.teacher = _user("teacher@settings.com", self.tenant, role="TEACHER")

    def test_unauthenticated_get_returns_401(self):
        response = APIClient().get("/api/v1/tenants/settings/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_can_get_settings(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        response = client.get("/api/v1/tenants/settings/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_teacher_cannot_access_settings(self):
        client = APIClient()
        client.force_authenticate(user=self.teacher)
        response = client.get("/api/v1/tenants/settings/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_patch_settings_name(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        response = client.patch(
            "/api/v1/tenants/settings/",
            {"name": "Updated School Name"},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.name, "Updated School Name")

    def test_admin_can_patch_primary_color(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        response = client.patch(
            "/api/v1/tenants/settings/",
            {"primary_color": "#ff5500"},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
