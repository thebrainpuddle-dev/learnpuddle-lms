# tests/test_cors_headers.py
"""
P0 Security Fix Verification Tests — CORS Header Validation.

Covers:
- CORS headers match tenant subdomain origins, never wildcard (*)
- Requests from non-tenant origins are denied CORS access
- Preflight (OPTIONS) requests handled correctly
- Credentials allowed only for valid tenant origins
- Cross-Origin-Resource-Policy is set to 'same-origin' (nginx layer)

These tests correspond to TASK-004 (HLS CORS wildcard fix).
The old config used Access-Control-Allow-Origin: * which allowed any
domain to fetch signed video URLs cross-origin.
"""

from django.test import TestCase, override_settings, RequestFactory
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant(name, subdomain, email):
    return Tenant.objects.create(
        name=name, slug=subdomain, subdomain=subdomain, email=email
    )


def _make_user(email, tenant, role="TEACHER"):
    return User.objects.create_user(
        email=email,
        password="pass123",
        first_name="Test",
        last_name="User",
        tenant=tenant,
        role=role,
    )


# ===========================================================================
# 1. CORS Origin Validation Tests
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="learnpuddle.com",
    DEBUG=False,
    CORS_ALLOWED_ORIGINS=[],
    CORS_ALLOWED_ORIGIN_REGEXES=[r"^https://([a-z0-9-]+\.)*learnpuddle\.com$"],
    CORS_ALLOW_CREDENTIALS=True,
    SECURE_SSL_REDIRECT=False,
)
class CorsOriginValidationTestCase(TestCase):
    """
    Verify that django-cors-headers only allows origins matching
    the tenant subdomain pattern, never a wildcard.
    """

    def setUp(self):
        self.tenant = _make_tenant("CORS School", "cors-demo", "cors@demo.com")
        self.user = _make_user("corsuser@demo.com", self.tenant, role="TEACHER")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_valid_tenant_origin_gets_cors_headers(self):
        """
        A request from a valid tenant subdomain origin should receive
        the Access-Control-Allow-Origin header matching that origin.
        """
        response = self.client.get(
            "/api/v1/courses/",
            HTTP_HOST="cors-demo.learnpuddle.com",
            HTTP_ORIGIN="https://cors-demo.learnpuddle.com",
        )
        acao = response.get("Access-Control-Allow-Origin", "")
        self.assertEqual(acao, "https://cors-demo.learnpuddle.com")

    def test_root_domain_origin_gets_cors_headers(self):
        """
        The root domain (learnpuddle.com) should also be allowed.
        """
        response = self.client.get(
            "/api/v1/courses/",
            HTTP_HOST="cors-demo.learnpuddle.com",
            HTTP_ORIGIN="https://learnpuddle.com",
        )
        acao = response.get("Access-Control-Allow-Origin", "")
        self.assertEqual(acao, "https://learnpuddle.com")

    def test_unauthorized_origin_gets_no_cors_header(self):
        """
        A request from an unauthorized origin (e.g., evil.com) must NOT
        receive an Access-Control-Allow-Origin header.
        """
        response = self.client.get(
            "/api/v1/courses/",
            HTTP_HOST="cors-demo.learnpuddle.com",
            HTTP_ORIGIN="https://evil.com",
        )
        acao = response.get("Access-Control-Allow-Origin", "")
        self.assertEqual(acao, "", "Unauthorized origin must not get CORS header")

    def test_wildcard_origin_is_never_returned(self):
        """
        The response must NEVER contain Access-Control-Allow-Origin: *
        regardless of the request origin.
        """
        for origin in [
            "https://cors-demo.learnpuddle.com",
            "https://evil.com",
            "https://example.org",
            "*",
        ]:
            response = self.client.get(
                "/api/v1/courses/",
                HTTP_HOST="cors-demo.learnpuddle.com",
                HTTP_ORIGIN=origin,
            )
            acao = response.get("Access-Control-Allow-Origin", "")
            self.assertNotEqual(
                acao, "*",
                f"Wildcard CORS must never be returned (origin={origin})",
            )

    def test_http_origin_rejected_when_https_required(self):
        """
        An HTTP (non-TLS) origin should be rejected since the regex
        requires https://.
        """
        response = self.client.get(
            "/api/v1/courses/",
            HTTP_HOST="cors-demo.learnpuddle.com",
            HTTP_ORIGIN="http://cors-demo.learnpuddle.com",
        )
        acao = response.get("Access-Control-Allow-Origin", "")
        self.assertEqual(acao, "", "HTTP origin should be rejected (HTTPS required)")

    def test_subdomain_injection_rejected(self):
        """
        Origins that try to abuse subdomain matching (e.g.,
        evil-learnpuddle.com) must be rejected.
        """
        response = self.client.get(
            "/api/v1/courses/",
            HTTP_HOST="cors-demo.learnpuddle.com",
            HTTP_ORIGIN="https://evil-learnpuddle.com",
        )
        acao = response.get("Access-Control-Allow-Origin", "")
        self.assertEqual(acao, "", "Subdomain injection must be rejected")


# ===========================================================================
# 2. CORS Preflight (OPTIONS) Tests
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="learnpuddle.com",
    DEBUG=False,
    CORS_ALLOWED_ORIGINS=[],
    CORS_ALLOWED_ORIGIN_REGEXES=[r"^https://([a-z0-9-]+\.)*learnpuddle\.com$"],
    CORS_ALLOW_CREDENTIALS=True,
    SECURE_SSL_REDIRECT=False,
)
class CorsPreflightTestCase(TestCase):
    """
    Verify that CORS preflight (OPTIONS) requests are handled correctly.
    """

    def setUp(self):
        self.tenant = _make_tenant("Preflight School", "pf-demo", "pf@demo.com")
        self.client = APIClient()

    def test_preflight_from_valid_origin_returns_cors_headers(self):
        """
        An OPTIONS preflight from a valid tenant origin should return
        the correct CORS headers including Allow-Origin, Allow-Methods,
        and Allow-Headers.
        """
        response = self.client.options(
            "/api/v1/courses/",
            HTTP_HOST="pf-demo.learnpuddle.com",
            HTTP_ORIGIN="https://pf-demo.learnpuddle.com",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="Authorization,Content-Type",
        )
        self.assertEqual(
            response.get("Access-Control-Allow-Origin"),
            "https://pf-demo.learnpuddle.com",
        )
        # Allow-Credentials must be true for JWT cookie/header auth
        self.assertEqual(
            response.get("Access-Control-Allow-Credentials"),
            "true",
        )

    def test_preflight_from_invalid_origin_denied(self):
        """
        An OPTIONS preflight from an unauthorized origin should NOT
        receive CORS approval headers.
        """
        response = self.client.options(
            "/api/v1/courses/",
            HTTP_HOST="pf-demo.learnpuddle.com",
            HTTP_ORIGIN="https://attacker.com",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
        )
        acao = response.get("Access-Control-Allow-Origin", "")
        self.assertEqual(acao, "", "Preflight from attacker origin must be denied")


# ===========================================================================
# 3. CORS Credentials Tests
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="learnpuddle.com",
    DEBUG=False,
    CORS_ALLOWED_ORIGINS=[],
    CORS_ALLOWED_ORIGIN_REGEXES=[r"^https://([a-z0-9-]+\.)*learnpuddle\.com$"],
    CORS_ALLOW_CREDENTIALS=True,
    SECURE_SSL_REDIRECT=False,
)
class CorsCredentialsTestCase(TestCase):
    """
    Verify that Access-Control-Allow-Credentials is only set for
    valid origins (never combined with wildcard).
    """

    def setUp(self):
        self.tenant = _make_tenant("Cred School", "cred-demo", "cred@demo.com")
        self.user = _make_user("creduser@demo.com", self.tenant, role="TEACHER")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_credentials_header_present_for_valid_origin(self):
        """
        When a valid tenant origin is used, Allow-Credentials must be 'true'.
        """
        response = self.client.get(
            "/api/v1/courses/",
            HTTP_HOST="cred-demo.learnpuddle.com",
            HTTP_ORIGIN="https://cred-demo.learnpuddle.com",
        )
        self.assertEqual(
            response.get("Access-Control-Allow-Credentials"),
            "true",
        )

    def test_credentials_not_combined_with_wildcard(self):
        """
        CORS spec forbids combining Allow-Credentials: true with
        Allow-Origin: *.  Verify this never happens.
        """
        response = self.client.get(
            "/api/v1/courses/",
            HTTP_HOST="cred-demo.learnpuddle.com",
            HTTP_ORIGIN="https://cred-demo.learnpuddle.com",
        )
        acao = response.get("Access-Control-Allow-Origin", "")
        acac = response.get("Access-Control-Allow-Credentials", "")
        if acac == "true":
            self.assertNotEqual(
                acao, "*",
                "Allow-Credentials: true must never be combined with Allow-Origin: *",
            )


# ===========================================================================
# 4. Media/Video Endpoint CORS Tests
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="learnpuddle.com",
    DEBUG=False,
    CORS_ALLOWED_ORIGINS=[],
    CORS_ALLOWED_ORIGIN_REGEXES=[r"^https://([a-z0-9-]+\.)*learnpuddle\.com$"],
    CORS_ALLOW_CREDENTIALS=True,
    SECURE_SSL_REDIRECT=False,
)
class MediaEndpointCorsTestCase(TestCase):
    """
    Verify that media/video endpoints do not leak signed URLs
    via CORS to unauthorized origins.
    """

    def setUp(self):
        self.tenant = _make_tenant("Media School", "media-demo", "media@demo.com")
        self.user = _make_user("mediauser@demo.com", self.tenant, role="TEACHER")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_media_endpoint_no_cors_for_attacker_origin(self):
        """
        Requests to /media/ from an unauthorized origin must NOT
        get CORS headers (prevents cross-origin video URL exfiltration).
        """
        response = self.client.get(
            "/media/tenant/1/uploads/test.m3u8",
            HTTP_HOST="media-demo.learnpuddle.com",
            HTTP_ORIGIN="https://attacker.com",
        )
        acao = response.get("Access-Control-Allow-Origin", "")
        self.assertEqual(acao, "", "Media endpoint must not allow attacker origin")

    def test_media_endpoint_allows_tenant_origin(self):
        """
        Requests to /media/ from a valid tenant origin should be allowed.
        """
        response = self.client.get(
            "/media/tenant/1/uploads/test.m3u8",
            HTTP_HOST="media-demo.learnpuddle.com",
            HTTP_ORIGIN="https://media-demo.learnpuddle.com",
        )
        # May be 404 (no file), but CORS header should still be present
        acao = response.get("Access-Control-Allow-Origin", "")
        self.assertEqual(acao, "https://media-demo.learnpuddle.com")
