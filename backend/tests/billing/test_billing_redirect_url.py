"""
Unit tests for ``apps.billing.views._is_tenant_redirect_url_allowed``.

Security context:  The ``create_checkout`` and ``create_portal`` billing
views accept ``success_url``, ``cancel_url``, and ``return_url`` parameters
that are forwarded to Stripe.  An attacker with school-admin access could
supply an arbitrary URL, obtain a signed Stripe redirect, and phish other
admins (open-redirect via Stripe).

``_is_tenant_redirect_url_allowed`` is the single guard preventing this.
These tests pin the exact allow/deny boundary so a future refactor cannot
silently weaken the check.

Test taxonomy:
  - Tenant-owned HTTPS URLs → ALLOW
  - Verified custom-domain URLs → ALLOW
  - Foreign / adversarial URLs → DENY
  - Localhost variants (DEBUG=True only) → ALLOW / DENY
  - Edge-case inputs (None, empty string, bad type) → DENY
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.billing.views import _is_tenant_redirect_url_allowed


# ---------------------------------------------------------------------------
# Fixture: minimal tenant-like namespace
# ---------------------------------------------------------------------------


def _tenant(
    subdomain: str = "demo",
    custom_domain: str = "",
    custom_domain_verified: bool = False,
) -> SimpleNamespace:
    """Return a minimal tenant-like object (no DB required)."""
    return SimpleNamespace(
        subdomain=subdomain,
        custom_domain=custom_domain,
        custom_domain_verified=custom_domain_verified,
    )


PLATFORM_DOMAIN = "learnpuddle.com"
TENANT = _tenant(subdomain="demo")


# ===========================================================================
# Production mode (DEBUG=False)
# ===========================================================================


class TestRedirectUrlProductionMode:
    """Redirect URL validation in production (DEBUG=False, HTTPS required)."""

    @pytest.fixture(autouse=True)
    def _production_settings(self, settings):
        settings.DEBUG = False
        settings.PLATFORM_DOMAIN = PLATFORM_DOMAIN

    # --- ALLOW ---

    def test_exact_tenant_subdomain_https(self):
        """https://demo.learnpuddle.com/ → allowed."""
        assert _is_tenant_redirect_url_allowed(
            "https://demo.learnpuddle.com/", TENANT
        ) is True

    def test_tenant_subdomain_with_path(self):
        """Path component is irrelevant — host matching only."""
        assert _is_tenant_redirect_url_allowed(
            "https://demo.learnpuddle.com/admin/billing?plan=pro", TENANT
        ) is True

    def test_tenant_subdomain_root_no_trailing_slash(self):
        assert _is_tenant_redirect_url_allowed(
            "https://demo.learnpuddle.com", TENANT
        ) is True

    def test_verified_custom_domain_allowed(self):
        """A verified custom domain for the same tenant is allowed."""
        tenant = _tenant(
            subdomain="demo",
            custom_domain="school.example.org",
            custom_domain_verified=True,
        )
        assert _is_tenant_redirect_url_allowed(
            "https://school.example.org/billing", tenant
        ) is True

    # --- DENY — wrong tenant ---

    def test_different_tenant_subdomain_denied(self):
        """Another tenant's subdomain must not be accepted."""
        assert _is_tenant_redirect_url_allowed(
            "https://attacker.learnpuddle.com/phish", TENANT
        ) is False

    def test_platform_domain_root_denied(self):
        """The bare platform domain (no subdomain) is not an allowed host."""
        assert _is_tenant_redirect_url_allowed(
            "https://learnpuddle.com/redirect", TENANT
        ) is False

    def test_unverified_custom_domain_denied(self):
        """Custom domain that has NOT been verified must be rejected."""
        tenant = _tenant(
            subdomain="demo",
            custom_domain="evil.example.com",
            custom_domain_verified=False,
        )
        assert _is_tenant_redirect_url_allowed(
            "https://evil.example.com/steal", tenant
        ) is False

    def test_empty_custom_domain_not_matched(self):
        """Empty custom_domain string must never be accepted as a valid host."""
        tenant = _tenant(subdomain="demo", custom_domain="", custom_domain_verified=True)
        assert _is_tenant_redirect_url_allowed(
            "https://demo.learnpuddle.com/ok", tenant
        ) is True  # Still accepted via subdomain
        assert _is_tenant_redirect_url_allowed(
            "https:///path", tenant
        ) is False

    # --- DENY — wrong scheme ---

    def test_http_denied_in_production(self):
        """HTTP (non-TLS) must be rejected in production mode."""
        assert _is_tenant_redirect_url_allowed(
            "http://demo.learnpuddle.com/", TENANT
        ) is False

    def test_ftp_denied(self):
        assert _is_tenant_redirect_url_allowed(
            "ftp://demo.learnpuddle.com/file", TENANT
        ) is False

    def test_data_uri_denied(self):
        assert _is_tenant_redirect_url_allowed(
            "data:text/html,<script>alert(1)</script>", TENANT
        ) is False

    # --- DENY — localhost in production ---

    def test_localhost_denied_in_production(self):
        """localhost must NOT be allowed when DEBUG=False."""
        assert _is_tenant_redirect_url_allowed(
            "https://localhost/admin", TENANT
        ) is False

    def test_127_0_0_1_denied_in_production(self):
        assert _is_tenant_redirect_url_allowed(
            "https://127.0.0.1/admin", TENANT
        ) is False

    # --- DENY — open redirect attempts ---

    def test_subdomain_bypass_attempt_denied(self):
        """Attacker prepends the valid host as a subdomain of their domain."""
        assert _is_tenant_redirect_url_allowed(
            "https://demo.learnpuddle.com.evil.com/phish", TENANT
        ) is False

    def test_path_confusion_attempt_denied(self):
        """demo.learnpuddle.com appears in the path, not the host."""
        assert _is_tenant_redirect_url_allowed(
            "https://evil.com/demo.learnpuddle.com/redirect", TENANT
        ) is False

    def test_url_with_credentials_denied(self):
        """URLs with userinfo (user:pass@host) targeting the right host are
        accepted by Python's urlparse — ensure the check still uses hostname
        (host without port/credentials) correctly."""
        # Python urlparse sets .hostname = 'demo.learnpuddle.com' for this
        assert _is_tenant_redirect_url_allowed(
            "https://user:pass@demo.learnpuddle.com/", TENANT
        ) is True  # hostname resolves correctly — not a bypass

    def test_port_variation_same_host(self):
        """Port number should not affect the host comparison."""
        assert _is_tenant_redirect_url_allowed(
            "https://demo.learnpuddle.com:443/billing", TENANT
        ) is True

    # --- DENY — edge-case inputs ---

    def test_none_url_denied(self):
        assert _is_tenant_redirect_url_allowed(None, TENANT) is False  # type: ignore[arg-type]

    def test_empty_string_url_denied(self):
        assert _is_tenant_redirect_url_allowed("", TENANT) is False

    def test_non_string_int_denied(self):
        assert _is_tenant_redirect_url_allowed(42, TENANT) is False  # type: ignore[arg-type]

    def test_non_string_list_denied(self):
        assert _is_tenant_redirect_url_allowed([], TENANT) is False  # type: ignore[arg-type]

    def test_whitespace_only_url_denied(self):
        assert _is_tenant_redirect_url_allowed("   ", TENANT) is False

    def test_relative_url_denied(self):
        """Relative URLs have no host and must be rejected."""
        assert _is_tenant_redirect_url_allowed("/admin/billing", TENANT) is False

    def test_url_with_no_scheme_denied(self):
        assert _is_tenant_redirect_url_allowed("demo.learnpuddle.com/billing", TENANT) is False

    def test_empty_host_url_denied(self):
        assert _is_tenant_redirect_url_allowed("https:///path", TENANT) is False


# ===========================================================================
# Debug mode (DEBUG=True)
# ===========================================================================


class TestRedirectUrlDebugMode:
    """In DEBUG mode localhost variants must be additionally accepted."""

    @pytest.fixture(autouse=True)
    def _debug_settings(self, settings):
        settings.DEBUG = True
        settings.PLATFORM_DOMAIN = PLATFORM_DOMAIN

    def test_https_tenant_subdomain_still_allowed_in_debug(self):
        assert _is_tenant_redirect_url_allowed(
            "https://demo.learnpuddle.com/", TENANT
        ) is True

    def test_http_tenant_subdomain_allowed_in_debug(self):
        """HTTP is permitted in DEBUG mode (local dev convenience)."""
        assert _is_tenant_redirect_url_allowed(
            "http://demo.learnpuddle.com/", TENANT
        ) is True

    def test_localhost_allowed_in_debug(self):
        assert _is_tenant_redirect_url_allowed(
            "http://localhost/admin/billing", TENANT
        ) is True

    def test_127_0_0_1_allowed_in_debug(self):
        assert _is_tenant_redirect_url_allowed(
            "http://127.0.0.1/admin", TENANT
        ) is True

    def test_tenant_subdomain_localhost_allowed_in_debug(self):
        """demo.localhost is a common local-dev pattern."""
        assert _is_tenant_redirect_url_allowed(
            "http://demo.localhost:3000/admin", TENANT
        ) is True

    def test_foreign_domain_still_denied_in_debug(self):
        """DEBUG mode must NOT open the door to arbitrary foreign domains."""
        assert _is_tenant_redirect_url_allowed(
            "http://evil.com/steal", TENANT
        ) is False

    def test_attacker_subdomain_denied_in_debug(self):
        assert _is_tenant_redirect_url_allowed(
            "http://attacker.learnpuddle.com/phish", TENANT
        ) is False

    def test_http_denied_for_foreign_domain_in_debug(self):
        assert _is_tenant_redirect_url_allowed(
            "https://notmydomain.com/redirect", TENANT
        ) is False


# ===========================================================================
# Multi-tenant: different tenants should not share allowed URLs
# ===========================================================================


class TestRedirectUrlCrossTenantIsolation:
    """Two separate tenant objects must not share allowed redirect URL sets."""

    @pytest.fixture(autouse=True)
    def _production_settings(self, settings):
        settings.DEBUG = False
        settings.PLATFORM_DOMAIN = PLATFORM_DOMAIN

    def test_tenant_a_url_rejected_for_tenant_b(self):
        tenant_a = _tenant(subdomain="alpha")
        tenant_b = _tenant(subdomain="beta")
        url = "https://alpha.learnpuddle.com/billing"
        assert _is_tenant_redirect_url_allowed(url, tenant_a) is True
        assert _is_tenant_redirect_url_allowed(url, tenant_b) is False

    def test_tenant_b_url_rejected_for_tenant_a(self):
        tenant_a = _tenant(subdomain="alpha")
        tenant_b = _tenant(subdomain="beta")
        url = "https://beta.learnpuddle.com/billing"
        assert _is_tenant_redirect_url_allowed(url, tenant_b) is True
        assert _is_tenant_redirect_url_allowed(url, tenant_a) is False

    def test_custom_domain_not_accepted_by_different_tenant(self):
        """Tenant A's verified custom domain must not be accepted by Tenant B."""
        tenant_a = _tenant(
            subdomain="alpha",
            custom_domain="school-a.example.org",
            custom_domain_verified=True,
        )
        tenant_b = _tenant(subdomain="beta")
        url = "https://school-a.example.org/billing"
        assert _is_tenant_redirect_url_allowed(url, tenant_a) is True
        assert _is_tenant_redirect_url_allowed(url, tenant_b) is False
