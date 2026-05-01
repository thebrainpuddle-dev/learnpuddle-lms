# tests/notifications/test_email_utils.py
"""
Unit tests for apps/notifications/email_utils.py.

All helper functions are pure (no DB), so no django_db fixture is needed.

Tests:
  - get_base_sender_address: parses DEFAULT_FROM_EMAIL, falls back to PLATFORM_DOMAIN
  - build_school_sender_email: uses configured name > tenant name > platform name
  - build_tenant_reply_to: configured reply-to > tenant email > empty
  - build_bucket_headers: correct header keys and values
  - get_base_context: contains platform_name, platform_domain, year
  - build_tenant_url: custom domain (verified), subdomain, platform-only
  - build_login_url: backward-compat wrapper
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings


def _tenant(
    subdomain="testschool",
    email="admin@school.example.com",
    name="Test School",
    custom_domain="",
    custom_domain_verified=False,
    notification_from_name="",
    notification_reply_to="",
    email_bucket_prefix="",
    id="tenant-uuid-123",
):
    """Build a minimal tenant-like object (no DB)."""
    return SimpleNamespace(
        subdomain=subdomain,
        email=email,
        name=name,
        custom_domain=custom_domain,
        custom_domain_verified=custom_domain_verified,
        notification_from_name=notification_from_name,
        notification_reply_to=notification_reply_to,
        email_bucket_prefix=email_bucket_prefix,
        id=id,
    )


# ===========================================================================
# 1. get_base_sender_address
# ===========================================================================

class GetBaseSenderAddressTestCase(SimpleTestCase):
    """Tests for get_base_sender_address()."""

    @override_settings(DEFAULT_FROM_EMAIL="LearnPuddle <noreply@learnpuddle.com>")
    def test_extracts_email_from_display_name_format(self):
        """Should return just the email address, not the display name."""
        from apps.notifications.email_utils import get_base_sender_address
        result = get_base_sender_address()
        self.assertEqual(result, "noreply@learnpuddle.com")

    @override_settings(DEFAULT_FROM_EMAIL="noreply@platform.com")
    def test_returns_plain_email_unchanged(self):
        """When DEFAULT_FROM_EMAIL has no display name, returns it as-is."""
        from apps.notifications.email_utils import get_base_sender_address
        result = get_base_sender_address()
        self.assertEqual(result, "noreply@platform.com")

    @override_settings(DEFAULT_FROM_EMAIL="", PLATFORM_DOMAIN="example.com")
    def test_falls_back_to_platform_domain_when_empty(self):
        """Empty DEFAULT_FROM_EMAIL falls back to noreply@<PLATFORM_DOMAIN>."""
        from apps.notifications.email_utils import get_base_sender_address
        result = get_base_sender_address()
        self.assertEqual(result, "noreply@example.com")


# ===========================================================================
# 2. build_school_sender_email
# ===========================================================================

@override_settings(
    PLATFORM_NAME="LearnPuddle",
    DEFAULT_FROM_EMAIL="noreply@learnpuddle.com",
)
class BuildSchoolSenderEmailTestCase(SimpleTestCase):
    """Tests for build_school_sender_email()."""

    def test_uses_notification_from_name_when_configured(self):
        """Configured notification_from_name takes precedence over tenant.name."""
        from apps.notifications.email_utils import build_school_sender_email
        t = _tenant(name="School Name", notification_from_name="Preferred Name")
        result = build_school_sender_email(t)
        self.assertIn("Preferred Name", result)
        self.assertNotIn("School Name", result)

    def test_falls_back_to_tenant_name_when_from_name_empty(self):
        """Empty notification_from_name → use tenant.name."""
        from apps.notifications.email_utils import build_school_sender_email
        t = _tenant(name="Central High", notification_from_name="")
        result = build_school_sender_email(t)
        self.assertIn("Central High", result)

    def test_includes_platform_name_in_via_format(self):
        """Output must include 'via <PLATFORM_NAME>'."""
        from apps.notifications.email_utils import build_school_sender_email
        t = _tenant()
        result = build_school_sender_email(t)
        self.assertIn("via LearnPuddle", result)

    def test_result_contains_sender_email_address(self):
        """Output must include the base sender email address."""
        from apps.notifications.email_utils import build_school_sender_email
        t = _tenant()
        result = build_school_sender_email(t)
        self.assertIn("noreply@learnpuddle.com", result)

    def test_handles_none_tenant(self):
        """None tenant → uses PLATFORM_NAME as school name."""
        from apps.notifications.email_utils import build_school_sender_email
        result = build_school_sender_email(None)
        self.assertIn("LearnPuddle", result)


# ===========================================================================
# 3. build_tenant_reply_to
# ===========================================================================

class BuildTenantReplyToTestCase(SimpleTestCase):
    """Tests for build_tenant_reply_to()."""

    def test_returns_configured_reply_to_when_set(self):
        """notification_reply_to takes precedence when configured."""
        from apps.notifications.email_utils import build_tenant_reply_to
        t = _tenant(notification_reply_to="custom-reply@school.com")
        result = build_tenant_reply_to(t)
        self.assertEqual(result, ["custom-reply@school.com"])

    def test_falls_back_to_tenant_email_when_reply_to_empty(self):
        """Empty notification_reply_to → use tenant.email."""
        from apps.notifications.email_utils import build_tenant_reply_to
        t = _tenant(notification_reply_to="", email="admin@school.example.com")
        result = build_tenant_reply_to(t)
        self.assertEqual(result, ["admin@school.example.com"])

    def test_returns_empty_list_when_no_tenant(self):
        """None tenant → empty list (no reply-to)."""
        from apps.notifications.email_utils import build_tenant_reply_to
        result = build_tenant_reply_to(None)
        self.assertEqual(result, [])

    def test_returns_empty_list_when_tenant_has_no_email(self):
        """Tenant with empty email AND no configured reply-to → empty list."""
        from apps.notifications.email_utils import build_tenant_reply_to
        t = _tenant(notification_reply_to="", email="")
        result = build_tenant_reply_to(t)
        self.assertEqual(result, [])


# ===========================================================================
# 4. build_bucket_headers
# ===========================================================================

class BuildBucketHeadersTestCase(SimpleTestCase):
    """Tests for build_bucket_headers()."""

    def test_returns_four_headers(self):
        """Result must always contain exactly the 4 expected headers."""
        from apps.notifications.email_utils import build_bucket_headers
        headers = build_bucket_headers(_tenant(), "onboarding", "welcome.html", "admin_welcome")
        for key in ("X-LP-Bucket", "X-LP-Template", "X-LP-Tenant", "X-LP-Event"):
            self.assertIn(key, headers)

    def test_bucket_uses_subdomain_prefix(self):
        """X-LP-Bucket uses the tenant subdomain as prefix."""
        from apps.notifications.email_utils import build_bucket_headers
        t = _tenant(subdomain="myschool")
        headers = build_bucket_headers(t, "trial", "expiry.html", "trial_warn")
        self.assertIn("myschool:trial", headers["X-LP-Bucket"])

    def test_bucket_uses_email_bucket_prefix_when_configured(self):
        """Custom email_bucket_prefix overrides subdomain."""
        from apps.notifications.email_utils import build_bucket_headers
        t = _tenant(subdomain="myschool", email_bucket_prefix="custom-prefix")
        headers = build_bucket_headers(t, "trial", "expiry.html", "trial_warn")
        self.assertIn("custom-prefix:trial", headers["X-LP-Bucket"])

    def test_bucket_falls_back_to_platform_when_no_tenant(self):
        """None tenant → X-LP-Bucket starts with 'platform'."""
        from apps.notifications.email_utils import build_bucket_headers
        headers = build_bucket_headers(None, "onboarding", "welcome.html", "admin_welcome")
        self.assertIn("platform:", headers["X-LP-Bucket"])

    def test_template_header_matches_template_name(self):
        """X-LP-Template must equal the template_name argument."""
        from apps.notifications.email_utils import build_bucket_headers
        headers = build_bucket_headers(_tenant(), "onboarding", "admin_welcome.html", "admin_welcome")
        self.assertEqual(headers["X-LP-Template"], "admin_welcome.html")

    def test_event_header_matches_event_argument(self):
        """X-LP-Event must equal the event argument."""
        from apps.notifications.email_utils import build_bucket_headers
        headers = build_bucket_headers(_tenant(), "onboarding", "welcome.html", "my_event")
        self.assertEqual(headers["X-LP-Event"], "my_event")


# ===========================================================================
# 5. get_base_context
# ===========================================================================

@override_settings(PLATFORM_NAME="TestPlatform", PLATFORM_DOMAIN="test.com")
class GetBaseContextTestCase(SimpleTestCase):
    """Tests for get_base_context()."""

    def test_contains_platform_name(self):
        from apps.notifications.email_utils import get_base_context
        ctx = get_base_context()
        self.assertEqual(ctx["platform_name"], "TestPlatform")

    def test_contains_platform_domain(self):
        from apps.notifications.email_utils import get_base_context
        ctx = get_base_context()
        self.assertEqual(ctx["platform_domain"], "test.com")

    def test_contains_current_year(self):
        from apps.notifications.email_utils import get_base_context
        from datetime import datetime
        ctx = get_base_context()
        self.assertEqual(ctx["year"], datetime.now().year)


# ===========================================================================
# 6. build_tenant_url
# ===========================================================================

@override_settings(PLATFORM_DOMAIN="learnpuddle.com")
class BuildTenantUrlTestCase(SimpleTestCase):
    """Tests for build_tenant_url()."""

    def test_uses_custom_domain_when_verified(self):
        """Verified custom domain takes highest precedence."""
        from apps.notifications.email_utils import build_tenant_url
        t = _tenant(custom_domain="school.example.com", custom_domain_verified=True)
        url = build_tenant_url(t, "/login")
        self.assertEqual(url, "https://school.example.com/login")

    def test_ignores_unverified_custom_domain(self):
        """Unverified custom domain must be ignored in favour of subdomain."""
        from apps.notifications.email_utils import build_tenant_url
        t = _tenant(
            subdomain="myschool",
            custom_domain="school.example.com",
            custom_domain_verified=False,
        )
        url = build_tenant_url(t, "/login")
        self.assertIn("myschool.learnpuddle.com", url)

    def test_uses_subdomain_when_no_custom_domain(self):
        """With no custom domain, uses subdomain.PLATFORM_DOMAIN."""
        from apps.notifications.email_utils import build_tenant_url
        t = _tenant(subdomain="demo")
        url = build_tenant_url(t, "/dashboard")
        self.assertEqual(url, "https://demo.learnpuddle.com/dashboard")

    def test_falls_back_to_platform_domain_with_no_tenant(self):
        """None tenant → uses platform domain only."""
        from apps.notifications.email_utils import build_tenant_url
        url = build_tenant_url(None, "/login")
        self.assertEqual(url, "https://learnpuddle.com/login")

    def test_prepends_slash_to_path_if_missing(self):
        """Path without leading slash must be normalised."""
        from apps.notifications.email_utils import build_tenant_url
        t = _tenant(subdomain="test")
        url = build_tenant_url(t, "login")
        self.assertTrue(url.endswith("/login"), f"Expected trailing /login, got {url!r}")

    def test_default_path_is_login(self):
        """Default path is '/login' when not specified."""
        from apps.notifications.email_utils import build_tenant_url
        url = build_tenant_url(None)
        self.assertTrue(url.endswith("/login"))


# ===========================================================================
# 7. build_login_url (backward-compat wrapper)
# ===========================================================================

@override_settings(PLATFORM_DOMAIN="learnpuddle.com")
class BuildLoginUrlTestCase(SimpleTestCase):
    """Tests for build_login_url() — backward-compat wrapper."""

    def test_builds_subdomain_url(self):
        """Must produce subdomain-based URL for the given subdomain."""
        from apps.notifications.email_utils import build_login_url
        url = build_login_url("myschool")
        self.assertEqual(url, "https://myschool.learnpuddle.com/login")

    def test_accepts_custom_path(self):
        """Custom path argument is honoured."""
        from apps.notifications.email_utils import build_login_url
        url = build_login_url("myschool", path="/forgot-password")
        self.assertTrue(url.endswith("/forgot-password"))

    def test_empty_subdomain_falls_back_to_platform(self):
        """Empty subdomain → platform-level URL."""
        from apps.notifications.email_utils import build_login_url
        url = build_login_url("")
        self.assertEqual(url, "https://learnpuddle.com/login")
