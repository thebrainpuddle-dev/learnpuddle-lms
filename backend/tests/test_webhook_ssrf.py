# tests/test_webhook_ssrf.py
"""
P0 Security Fix — Webhook SSRF Protection Tests.

Covers Server-Side Request Forgery (SSRF) prevention for webhook endpoints.
Without this protection, an attacker could configure a webhook URL pointing
to internal infrastructure (Redis, database, metadata server) and cause
the server to make HTTP requests to those internal endpoints.

Test matrix:
- Valid external HTTPS URLs → accepted (None returned)
- HTTP URLs → rejected ("URL must use HTTPS")
- Localhost / loopback hostnames → rejected
- Private IP ranges → rejected
- Docker service names → rejected
- Internal domain suffixes (.local, .internal) → rejected
- Cloud metadata server → rejected
- API-level: POST /webhooks/ with bad URLs returns 400
"""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.webhooks.views import _validate_webhook_url


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant(name, subdomain):
    return Tenant.objects.create(
        name=name, slug=subdomain, subdomain=subdomain,
        email=f"{subdomain}@example.com", is_active=True,
    )


def _make_admin(email, tenant):
    return User.objects.create_user(
        email=email, password="Pass!123",
        first_name="Admin", last_name="User",
        tenant=tenant, role="SCHOOL_ADMIN", is_active=True,
    )


# ===========================================================================
# 1. Unit Tests — _validate_webhook_url pure function
# ===========================================================================

class WebhookSSRFUrlValidationTestCase(TestCase):
    """
    Direct unit tests of the SSRF-protection validator.
    No DB or request context needed — purely tests the logic function.
    """

    # --- Valid URLs (should return None) ---

    def test_valid_https_external_url_is_accepted(self):
        self.assertIsNone(_validate_webhook_url("https://example.com/webhook"))

    def test_valid_https_url_with_path_is_accepted(self):
        self.assertIsNone(_validate_webhook_url("https://hooks.zapier.com/hooks/catch/abc123/"))

    def test_valid_https_url_with_port_is_accepted(self):
        self.assertIsNone(_validate_webhook_url("https://example.com:8443/webhook"))

    def test_valid_https_url_with_query_params_is_accepted(self):
        self.assertIsNone(_validate_webhook_url("https://api.example.com/hook?key=abc"))

    # --- HTTP / Non-HTTPS URLs ---

    def test_http_url_is_rejected(self):
        error = _validate_webhook_url("http://example.com/webhook")
        self.assertIsNotNone(error)
        self.assertIn("HTTPS", error)

    def test_ftp_url_is_rejected(self):
        error = _validate_webhook_url("ftp://example.com/files")
        self.assertIsNotNone(error)

    # --- Localhost / Loopback Hostnames ---

    def test_localhost_hostname_is_rejected(self):
        error = _validate_webhook_url("https://localhost/webhook")
        self.assertIsNotNone(error, "localhost must be blocked (SSRF)")

    def test_127_0_0_1_is_rejected(self):
        error = _validate_webhook_url("https://127.0.0.1/webhook")
        self.assertIsNotNone(error, "127.0.0.1 must be blocked (SSRF)")

    def test_0_0_0_0_is_rejected(self):
        error = _validate_webhook_url("https://0.0.0.0/webhook")
        self.assertIsNotNone(error, "0.0.0.0 must be blocked (SSRF)")

    def test_ipv6_loopback_is_rejected(self):
        error = _validate_webhook_url("https://[::1]/webhook")
        self.assertIsNotNone(error, "IPv6 loopback ::1 must be blocked (SSRF)")

    # --- Private IP Ranges ---

    def test_private_192_168_range_is_rejected(self):
        error = _validate_webhook_url("https://192.168.1.100/webhook")
        self.assertIsNotNone(error, "RFC1918 192.168.x.x must be blocked")

    def test_private_10_x_x_x_range_is_rejected(self):
        error = _validate_webhook_url("https://10.0.0.1/webhook")
        self.assertIsNotNone(error, "RFC1918 10.x.x.x must be blocked")

    def test_private_172_16_range_is_rejected(self):
        error = _validate_webhook_url("https://172.16.0.1/webhook")
        self.assertIsNotNone(error, "RFC1918 172.16-31.x.x must be blocked")

    def test_link_local_169_254_is_rejected(self):
        """AWS/GCP metadata service lives at 169.254.169.254."""
        error = _validate_webhook_url("https://169.254.169.254/latest/meta-data/")
        self.assertIsNotNone(error, "Link-local 169.254.x.x must be blocked (cloud metadata SSRF)")

    # --- Docker Internal Service Names ---

    def test_docker_web_service_is_rejected(self):
        error = _validate_webhook_url("https://web/endpoint")
        self.assertIsNotNone(error, "Docker service 'web' must be blocked")

    def test_docker_redis_service_is_rejected(self):
        error = _validate_webhook_url("https://redis/endpoint")
        self.assertIsNotNone(error, "Docker service 'redis' must be blocked")

    def test_docker_db_service_is_rejected(self):
        error = _validate_webhook_url("https://db/endpoint")
        self.assertIsNotNone(error, "Docker service 'db' must be blocked")

    def test_docker_worker_service_is_rejected(self):
        error = _validate_webhook_url("https://worker/endpoint")
        self.assertIsNotNone(error, "Docker service 'worker' must be blocked")

    def test_docker_flower_service_is_rejected(self):
        error = _validate_webhook_url("https://flower/endpoint")
        self.assertIsNotNone(error, "Docker service 'flower' must be blocked")

    def test_docker_nginx_service_is_rejected(self):
        error = _validate_webhook_url("https://nginx/endpoint")
        self.assertIsNotNone(error, "Docker service 'nginx' must be blocked")

    # --- Internal Domain Suffixes ---

    def test_dot_local_suffix_is_rejected(self):
        error = _validate_webhook_url("https://myservice.local/webhook")
        self.assertIsNotNone(error, ".local TLD must be blocked (mDNS internal)")

    def test_dot_internal_suffix_is_rejected(self):
        error = _validate_webhook_url("https://myservice.internal/webhook")
        self.assertIsNotNone(error, ".internal TLD must be blocked")

    def test_dot_localhost_suffix_is_rejected(self):
        error = _validate_webhook_url("https://anything.localhost/webhook")
        self.assertIsNotNone(error, "*.localhost must be blocked")

    # --- Cloud Metadata Server ---

    def test_google_metadata_internal_is_rejected(self):
        error = _validate_webhook_url("https://metadata.google.internal/computeMetadata/v1/")
        self.assertIsNotNone(error, "GCP metadata server must be blocked")

    # --- Edge Cases ---

    def test_empty_string_is_rejected(self):
        error = _validate_webhook_url("")
        self.assertIsNotNone(error)

    def test_url_without_hostname_is_rejected(self):
        error = _validate_webhook_url("https:///path")
        self.assertIsNotNone(error)


# ===========================================================================
# 2. API Integration Tests — SSRF protection via POST /api/v1/webhooks/
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class WebhookApiSSRFTestCase(TestCase):
    """
    Integration tests verifying that the SSRF protection is enforced
    when creating or updating webhooks via the API.
    """

    def setUp(self):
        self.tenant = _make_tenant("SSRF School", "ssrftest")
        self.admin = _make_admin("admin@ssrftest.com", self.tenant)
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.client.defaults["HTTP_HOST"] = "ssrftest.lms.com"

    def _create_webhook(self, url, events=None):
        return self.client.post(
            "/api/v1/webhooks/",
            {
                "name": "Test Webhook",
                "url": url,
                "events": events or ["course.created"],
            },
            format="json",
        )

    def test_create_webhook_with_http_url_returns_400(self):
        r = self._create_webhook("http://example.com/hook")
        self.assertEqual(r.status_code, 400)
        self.assertIn("HTTPS", r.data.get("error", ""))

    def test_create_webhook_with_localhost_returns_400(self):
        r = self._create_webhook("https://localhost/api/steal")
        self.assertEqual(r.status_code, 400)

    def test_create_webhook_with_127_0_0_1_returns_400(self):
        r = self._create_webhook("https://127.0.0.1:8000/api/steal")
        self.assertEqual(r.status_code, 400)

    def test_create_webhook_with_private_ip_returns_400(self):
        r = self._create_webhook("https://192.168.0.1/steal")
        self.assertEqual(r.status_code, 400)

    def test_create_webhook_with_docker_db_returns_400(self):
        r = self._create_webhook("https://db:5432/steal")
        self.assertEqual(r.status_code, 400)

    def test_create_webhook_with_dot_internal_returns_400(self):
        r = self._create_webhook("https://internal.service.internal/hook")
        self.assertEqual(r.status_code, 400)

    def test_create_webhook_with_valid_url_returns_201(self):
        r = self._create_webhook("https://hooks.example.com/lms-webhook")
        self.assertEqual(r.status_code, 201)
        self.assertIn("id", r.data)
        self.assertIn("secret", r.data)

    def test_update_webhook_url_with_ssrf_returns_400(self):
        """SSRF protection must also apply on webhook UPDATE (PUT)."""
        # First create a valid webhook
        create_r = self._create_webhook("https://hooks.example.com/initial")
        self.assertEqual(create_r.status_code, 201)
        webhook_id = create_r.data["id"]

        # Try to update the URL to a SSRF target
        update_r = self.client.put(
            f"/api/v1/webhooks/{webhook_id}/",
            {"url": "https://redis/steal"},
            format="json",
        )
        self.assertEqual(update_r.status_code, 400)

    def test_update_webhook_url_with_private_ip_returns_400(self):
        """SSRF protection on PUT must block private IPs."""
        create_r = self._create_webhook("https://hooks.example.com/initial2")
        self.assertEqual(create_r.status_code, 201)
        webhook_id = create_r.data["id"]

        update_r = self.client.put(
            f"/api/v1/webhooks/{webhook_id}/",
            {"url": "https://10.0.0.5/steal"},
            format="json",
        )
        self.assertEqual(update_r.status_code, 400)
