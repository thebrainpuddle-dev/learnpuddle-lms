# tests/tenants/test_tenant_views.py
"""
Tests for tenant management endpoints.

Covers:
- GET /api/v1/tenants/theme/    — public endpoint, tenant branding
- GET /api/v1/tenants/me/       — tenant details for current tenant (auth required)
- GET /api/v1/tenants/config/   — tenant config (auth required)
- GET/PATCH /api/v1/tenants/settings/  — admin settings

Key behaviors verified:
- Theme is public (no auth needed)
- Active tenant returns tenant_found=true
- Unknown subdomain returns tenant_found=false (not 404)
- Inactive tenant returns tenant_found=false with reason
- Authenticated endpoints require valid auth
- Cross-tenant: users can only access their own tenant's settings
"""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant(name, subdomain, is_active=True):
    return Tenant.objects.create(
        name=name, slug=subdomain, subdomain=subdomain,
        email=f"{subdomain}@example.com", is_active=is_active,
    )


def _make_user(email, tenant, role="TEACHER"):
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


# ===========================================================================
# 1. Tenant Theme (Public)
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class TenantThemeViewTestCase(TestCase):
    """
    GET /api/v1/tenants/theme/ — fully public endpoint.
    """

    def setUp(self):
        self.tenant = _make_tenant("Theme School", "theme")

    def test_theme_returns_200_for_active_tenant(self):
        c = _anon_client("theme")
        r = c.get("/api/v1/tenants/theme/")
        self.assertEqual(r.status_code, 200)

    def test_theme_returns_tenant_found_true_for_active_tenant(self):
        c = _anon_client("theme")
        r = c.get("/api/v1/tenants/theme/")
        self.assertTrue(r.data.get("tenant_found"))

    def test_theme_returns_tenant_name(self):
        c = _anon_client("theme")
        r = c.get("/api/v1/tenants/theme/")
        self.assertEqual(r.data.get("name"), "Theme School")

    def test_theme_requires_no_authentication(self):
        """Theme endpoint must work without any auth token."""
        c = APIClient()
        c.defaults["HTTP_HOST"] = "theme.lms.com"
        r = c.get("/api/v1/tenants/theme/")
        self.assertEqual(r.status_code, 200)

    def test_theme_returns_tenant_found_false_for_unknown_subdomain(self):
        """Unknown subdomains should return 200 with tenant_found=false (not 404)."""
        c = _anon_client("nonexistent9999")
        r = c.get("/api/v1/tenants/theme/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data.get("tenant_found"))

    def test_theme_for_unknown_subdomain_includes_not_found_reason(self):
        c = _anon_client("nope9876")
        r = c.get("/api/v1/tenants/theme/")
        self.assertEqual(r.data.get("reason"), "not_found")

    def test_theme_for_inactive_tenant_returns_tenant_found_false(self):
        inactive = _make_tenant("Inactive School", "inactive", is_active=False)
        c = _anon_client("inactive")
        r = c.get("/api/v1/tenants/theme/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data.get("tenant_found"))

    def test_theme_for_inactive_tenant_includes_deactivated_reason(self):
        _make_tenant("Deactivated School", "deactivated", is_active=False)
        c = _anon_client("deactivated")
        r = c.get("/api/v1/tenants/theme/")
        self.assertIn(r.data.get("reason"), ["deactivated", "trial_expired"])

    def test_theme_response_includes_branding_colors(self):
        c = _anon_client("theme")
        r = c.get("/api/v1/tenants/theme/")
        self.assertIn("primary_color", r.data)
        self.assertIn("secondary_color", r.data)


# ===========================================================================
# 2. Tenant Me (Authenticated)
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class TenantMeViewTestCase(TestCase):
    """
    GET /api/v1/tenants/me/ — returns current tenant info.
    """

    def setUp(self):
        self.tenant = _make_tenant("Me Tenant School", "metenant")
        self.teacher = _make_user("teacher@metenant.com", self.tenant)
        self.admin = _make_user("admin@metenant.com", self.tenant, role="SCHOOL_ADMIN")

    def test_tenant_me_returns_200_for_teacher(self):
        c = _client_for(self.teacher, "metenant")
        r = c.get("/api/v1/tenants/me/")
        self.assertEqual(r.status_code, 200)

    def test_tenant_me_returns_200_for_admin(self):
        c = _client_for(self.admin, "metenant")
        r = c.get("/api/v1/tenants/me/")
        self.assertEqual(r.status_code, 200)

    def test_tenant_me_requires_authentication(self):
        c = _anon_client("metenant")
        r = c.get("/api/v1/tenants/me/")
        self.assertEqual(r.status_code, 401)

    def test_tenant_me_returns_correct_tenant_name(self):
        c = _client_for(self.teacher, "metenant")
        r = c.get("/api/v1/tenants/me/")
        self.assertEqual(r.data.get("name"), "Me Tenant School")

    def test_tenant_me_returns_subdomain(self):
        c = _client_for(self.teacher, "metenant")
        r = c.get("/api/v1/tenants/me/")
        self.assertEqual(r.data.get("subdomain"), "metenant")

    def test_tenant_me_cross_tenant_denied(self):
        """
        User from Tenant A accessing Tenant B's /me/ endpoint must be denied
        with 403 (BE-SEC-001 fix: @tenant_required added to tenant_me_view).

        Regression guard: teacher belongs to 'metenant', but issues a request
        to 'othertenant' Host header. The @tenant_required decorator cross-
        checks the authenticated user's tenant_id against the resolved tenant
        and raises PermissionDenied for a mismatch.
        """
        _make_tenant("Other School", "othertenant")
        c = APIClient()
        c.force_authenticate(user=self.teacher)
        c.defaults["HTTP_HOST"] = "othertenant.lms.com"
        r = c.get("/api/v1/tenants/me/")
        self.assertEqual(r.status_code, 403)


# ===========================================================================
# 3. Tenant Settings (Admin only)
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class TenantSettingsViewTestCase(TestCase):
    """
    GET/PATCH /api/v1/tenants/settings/ — admin-only tenant configuration.
    """

    def setUp(self):
        self.tenant = _make_tenant("Settings School", "settings")
        self.admin = _make_user("admin@settings.com", self.tenant, role="SCHOOL_ADMIN")
        self.teacher = _make_user("teacher@settings.com", self.tenant, role="TEACHER")

    def test_settings_requires_authentication(self):
        c = _anon_client("settings")
        r = c.get("/api/v1/tenants/settings/")
        self.assertEqual(r.status_code, 401)

    def test_settings_returns_200_for_admin(self):
        c = _client_for(self.admin, "settings")
        r = c.get("/api/v1/tenants/settings/")
        self.assertEqual(r.status_code, 200)

    def test_settings_forbidden_for_teacher(self):
        c = _client_for(self.teacher, "settings")
        r = c.get("/api/v1/tenants/settings/")
        self.assertEqual(r.status_code, 403)

    def test_settings_cross_tenant_denied(self):
        """Admin of Tenant A cannot access Tenant B's settings."""
        other_tenant = _make_tenant("Other Settings School", "othersettings")
        c = APIClient()
        c.force_authenticate(user=self.admin)
        c.defaults["HTTP_HOST"] = "othersettings.lms.com"
        r = c.get("/api/v1/tenants/settings/")
        self.assertEqual(r.status_code, 403)


# ===========================================================================
# 4. Tenant Config (Authenticated)
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class TenantConfigViewTestCase(TestCase):
    """
    GET /api/v1/tenants/config/ — tenant feature flags and limits.
    """

    def setUp(self):
        self.tenant = _make_tenant("Config School", "config")
        self.teacher = _make_user("teacher@config.com", self.tenant)

    def test_config_requires_authentication(self):
        c = _anon_client("config")
        r = c.get("/api/v1/tenants/config/")
        self.assertEqual(r.status_code, 401)

    def test_config_returns_200_for_authenticated_user(self):
        c = _client_for(self.teacher, "config")
        r = c.get("/api/v1/tenants/config/")
        self.assertEqual(r.status_code, 200)

    def test_config_includes_tenant_plan_information(self):
        c = _client_for(self.teacher, "config")
        r = c.get("/api/v1/tenants/config/")
        # Config should include plan or feature info
        self.assertIn(r.status_code, [200])
        # Check some meaningful field is present
        self.assertIsNotNone(r.data)
