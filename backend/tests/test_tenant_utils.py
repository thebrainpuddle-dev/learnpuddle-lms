# tests/test_tenant_utils.py
"""
Tests for utils/tenant_utils.py — Tenant resolution from HTTP requests.

Covers (extending existing partial coverage in apps/tenants/tests.py):
1. Subdomain resolution under PLATFORM_DOMAIN (school.learnpuddle.com)
2. localhost resolves to demo tenant (dev mode)
3. 127.0.0.1 resolves to demo tenant (dev mode)
4. .localhost subdomain resolution (e.g., demo.localhost:8000)
5. X-Tenant-Subdomain header override in dev mode
6. Platform root (learnpuddle.com) returns None (no tenant)
7. www root (www.learnpuddle.com) returns None (no tenant)
8. Custom domain resolution (verified custom domains)
9. Inactive tenant raises PermissionDenied
10. Non-existent subdomain raises PermissionDenied
11. Unknown host raises PermissionDenied
12. Multi-level subdomain (a.b.learnpuddle.com) rejected
13. Empty subdomain rejected
14. get_current_tenant() (wrapper) delegates to middleware
"""

import pytest
from django.test import TestCase, override_settings
from django.core.exceptions import PermissionDenied
from types import SimpleNamespace


# ===========================================================================
# Helpers
# ===========================================================================

def _make_request(host: str, subdomain_header: str = "") -> SimpleNamespace:
    """Create a minimal mock request with configurable Host header."""
    meta = {}
    if subdomain_header:
        meta["HTTP_X_TENANT_SUBDOMAIN"] = subdomain_header

    request = SimpleNamespace(
        META=meta,
        _host=host,
    )

    # Attach get_host() method
    def _get_host():
        return host

    request.get_host = _get_host
    return request


@pytest.fixture
def demo_tenant(db):
    """A 'demo' subdomain tenant for localhost dev-mode tests."""
    from apps.tenants.models import Tenant
    return Tenant.objects.create(
        name="Demo School",
        slug="demo-school-utils",
        subdomain="demo",
        email="admin@demo.example.com",
        is_active=True,
    )


@pytest.fixture
def school_tenant(db):
    """A regular subdomain tenant."""
    from apps.tenants.models import Tenant
    return Tenant.objects.create(
        name="Springfield School",
        slug="springfield-school",
        subdomain="springfield",
        email="admin@springfield.example.com",
        is_active=True,
    )


@pytest.fixture
def custom_domain_tenant(db):
    """A tenant with a verified custom domain."""
    from apps.tenants.models import Tenant
    return Tenant.objects.create(
        name="Custom Domain School",
        slug="custom-domain-school",
        subdomain="customschool",
        email="admin@customschool.example.com",
        is_active=True,
        custom_domain="learn.customschool.org",
        custom_domain_verified=True,
    )


# ===========================================================================
# 1. Platform Subdomain Resolution Tests
# ===========================================================================


@pytest.mark.django_db
@override_settings(PLATFORM_DOMAIN="lms.com")
class PlatformSubdomainTestCase(TestCase):
    """Tenant resolution from subdomain under PLATFORM_DOMAIN."""

    def setUp(self):
        from apps.tenants.models import Tenant
        self.tenant = Tenant.objects.create(
            name="Springfield School",
            slug="springfield-school-utils",
            subdomain="springfield",
            email="admin@springfield.example.com",
            is_active=True,
        )

    def test_resolves_subdomain_under_platform_domain(self):
        """school.lms.com must resolve to the 'school' subdomain tenant."""
        from utils.tenant_utils import get_tenant_from_request

        request = _make_request("springfield.lms.com")
        tenant = get_tenant_from_request(request)

        self.assertEqual(
            tenant.subdomain,
            "springfield",
            "springfield.lms.com must resolve to the 'springfield' tenant",
        )

    def test_platform_root_returns_none(self):
        """lms.com (platform root) must return None (no specific tenant)."""
        from utils.tenant_utils import get_tenant_from_request

        request = _make_request("lms.com")
        result = get_tenant_from_request(request)

        self.assertIsNone(
            result,
            "Platform root domain must return None (not a tenant host)",
        )

    def test_www_root_returns_none(self):
        """www.lms.com must return None (no specific tenant)."""
        from utils.tenant_utils import get_tenant_from_request

        request = _make_request("www.lms.com")
        result = get_tenant_from_request(request)

        self.assertIsNone(result, "www. prefix of platform root must return None")

    def test_nonexistent_subdomain_raises_permission_denied(self):
        """Unknown subdomain must raise PermissionDenied."""
        from utils.tenant_utils import get_tenant_from_request

        request = _make_request("ghost.lms.com")

        with self.assertRaises(PermissionDenied):
            get_tenant_from_request(request)

    def test_inactive_tenant_raises_permission_denied(self):
        """Inactive tenant must raise PermissionDenied (not return the tenant)."""
        from utils.tenant_utils import get_tenant_from_request
        from apps.tenants.models import Tenant

        inactive = Tenant.objects.create(
            name="Inactive School",
            slug="inactive-school-utils",
            subdomain="inactive",
            email="admin@inactive.example.com",
            is_active=False,
        )

        request = _make_request("inactive.lms.com")

        with self.assertRaises(PermissionDenied):
            get_tenant_from_request(request)

    def test_multi_level_subdomain_rejected(self):
        """a.b.lms.com (multi-level) must raise PermissionDenied."""
        from utils.tenant_utils import get_tenant_from_request

        request = _make_request("a.b.lms.com")

        with self.assertRaises(PermissionDenied):
            get_tenant_from_request(request)

    def test_www_subdomain_explicitly_rejected(self):
        """www.lms.com is the platform root — must return None."""
        from utils.tenant_utils import get_tenant_from_request

        request = _make_request("www.lms.com")
        result = get_tenant_from_request(request)
        self.assertIsNone(result)


# ===========================================================================
# 2. Localhost / Development Mode Tests
# ===========================================================================


@pytest.mark.django_db
@override_settings(PLATFORM_DOMAIN="lms.com")
class LocalhostResolutionTestCase(TestCase):
    """Dev-mode: localhost/127.0.0.1 resolve to demo tenant."""

    def setUp(self):
        from apps.tenants.models import Tenant
        self.demo_tenant = Tenant.objects.create(
            name="Demo School",
            slug="demo-school-localhost",
            subdomain="demo",
            email="admin@demo.example.com",
            is_active=True,
        )

    def test_localhost_resolves_to_demo_tenant(self):
        """localhost must resolve to the 'demo' subdomain tenant."""
        from utils.tenant_utils import get_tenant_from_request

        request = _make_request("localhost")
        tenant = get_tenant_from_request(request)

        self.assertEqual(
            tenant.subdomain,
            "demo",
            "localhost must fall back to the 'demo' tenant in dev mode",
        )

    def test_127_0_0_1_resolves_to_demo_tenant(self):
        """127.0.0.1 must resolve to the 'demo' subdomain tenant."""
        from utils.tenant_utils import get_tenant_from_request

        request = _make_request("127.0.0.1")
        tenant = get_tenant_from_request(request)

        self.assertEqual(
            tenant.subdomain,
            "demo",
            "127.0.0.1 must fall back to the 'demo' tenant",
        )

    def test_subdomain_dot_localhost_resolves_subdomain(self):
        """demo.localhost must resolve to the 'demo' tenant."""
        from utils.tenant_utils import get_tenant_from_request

        request = _make_request("demo.localhost")
        tenant = get_tenant_from_request(request)

        self.assertEqual(tenant.subdomain, "demo")

    def test_x_tenant_subdomain_header_overrides_localhost(self):
        """X-Tenant-Subdomain header must override the default 'demo' fallback."""
        from utils.tenant_utils import get_tenant_from_request
        from apps.tenants.models import Tenant

        # Create a second tenant
        other = Tenant.objects.create(
            name="Other School",
            slug="other-school-localhost",
            subdomain="other",
            email="admin@other.example.com",
            is_active=True,
        )

        request = _make_request("localhost", subdomain_header="other")
        tenant = get_tenant_from_request(request)

        self.assertEqual(
            tenant.subdomain,
            "other",
            "X-Tenant-Subdomain header must override the demo fallback",
        )

    def test_localhost_with_inactive_demo_raises(self):
        """If demo tenant is inactive, localhost must raise PermissionDenied."""
        from utils.tenant_utils import get_tenant_from_request

        self.demo_tenant.is_active = False
        self.demo_tenant.save()

        request = _make_request("localhost")

        with self.assertRaises(PermissionDenied):
            get_tenant_from_request(request)


# ===========================================================================
# 3. Custom Domain Tests
# ===========================================================================


@pytest.mark.django_db
@override_settings(PLATFORM_DOMAIN="lms.com")
class CustomDomainResolutionTestCase(TestCase):
    """Custom domain resolution (verified custom domains)."""

    def setUp(self):
        from apps.tenants.models import Tenant
        self.tenant = Tenant.objects.create(
            name="Custom Domain School",
            slug="custom-domain-school-utils",
            subdomain="customschool",
            email="admin@customschool.example.com",
            is_active=True,
            custom_domain="learn.customschool.org",
            custom_domain_verified=True,
        )

    def test_verified_custom_domain_resolves_to_tenant(self):
        """learn.customschool.org must resolve to the tenant via custom_domain match."""
        from utils.tenant_utils import get_tenant_from_request

        request = _make_request("learn.customschool.org")
        tenant = get_tenant_from_request(request)

        self.assertEqual(
            tenant.subdomain,
            "customschool",
            "Verified custom domain must resolve to the correct tenant",
        )

    def test_unverified_custom_domain_does_not_resolve(self):
        """An unverified custom domain must not resolve (security: prevent domain hijack)."""
        from utils.tenant_utils import get_tenant_from_request
        from apps.tenants.models import Tenant

        unverified = Tenant.objects.create(
            name="Unverified School",
            slug="unverified-school",
            subdomain="unverifiedschool",
            email="admin@unverified.example.com",
            is_active=True,
            custom_domain="unverified.example.org",
            custom_domain_verified=False,  # Not verified
        )

        request = _make_request("unverified.example.org")

        with self.assertRaises(PermissionDenied):
            get_tenant_from_request(request)


# ===========================================================================
# 4. Unknown / Invalid Host Tests
# ===========================================================================


@pytest.mark.django_db
@override_settings(PLATFORM_DOMAIN="lms.com")
class UnknownHostTestCase(TestCase):
    """Unknown hosts must raise PermissionDenied (not return None or crash)."""

    def test_completely_unknown_host_raises(self):
        """A host not matching any pattern must raise PermissionDenied."""
        from utils.tenant_utils import get_tenant_from_request

        request = _make_request("completely-unknown-host.xyz")

        with self.assertRaises(PermissionDenied):
            get_tenant_from_request(request)

    def test_ip_address_host_raises(self):
        """
        Arbitrary external IP hosts (not localhost/127.0.0.1) must be rejected.
        This prevents host injection attacks.
        """
        from utils.tenant_utils import get_tenant_from_request

        request = _make_request("192.168.0.1")

        with self.assertRaises(PermissionDenied):
            get_tenant_from_request(request)


# ===========================================================================
# 5. get_current_tenant() Wrapper Tests
# ===========================================================================


class GetCurrentTenantWrapperTestCase(TestCase):
    """utils/tenant_utils.get_current_tenant() must delegate to middleware."""

    def test_get_current_tenant_returns_none_when_not_set(self):
        """get_current_tenant() must return None when context is empty."""
        from utils.tenant_middleware import clear_current_tenant
        from utils.tenant_utils import get_current_tenant

        clear_current_tenant()
        self.assertIsNone(
            get_current_tenant(),
            "get_current_tenant() must return None when tenant context is empty",
        )

    def test_get_current_tenant_returns_set_tenant(self):
        """After set_current_tenant(), get_current_tenant() must return the same tenant."""
        from utils.tenant_middleware import set_current_tenant, clear_current_tenant
        from utils.tenant_utils import get_current_tenant
        from types import SimpleNamespace

        mock_tenant = SimpleNamespace(subdomain="wrapper-test")
        set_current_tenant(mock_tenant)

        try:
            result = get_current_tenant()
            self.assertIs(
                result,
                mock_tenant,
                "get_current_tenant() must return the tenant set by set_current_tenant()",
            )
        finally:
            clear_current_tenant()
