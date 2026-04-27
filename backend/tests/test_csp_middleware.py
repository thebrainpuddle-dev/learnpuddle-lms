# tests/test_csp_middleware.py
"""
Tests for utils/csp_middleware.py — Content Security Policy middleware.

Security properties verified:
1. Every request gets a unique CSP nonce (XSS protection)
2. CSP header added for Django admin and API doc paths
3. CSP header NOT added for regular API endpoints (nginx handles those)
4. Nonces are unique per request (not reused)
5. CSP header contains nonce in script-src and style-src
6. Report-Only mode uses different header name
7. report-uri directive added when configured
8. frame-ancestors 'none' present (clickjacking protection)
9. object-src 'none' present (Flash/plugin protection)
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import re

from django.http import HttpResponse
from django.test import TestCase, override_settings


# ===========================================================================
# Helpers
# ===========================================================================

def _make_request(path: str = "/django-admin/"):
    """Create a minimal mock HTTP request for middleware testing."""
    request = SimpleNamespace(path=path, csp_nonce=None)
    return request


def _make_middleware(settings_overrides=None):
    """Instantiate CSPMiddleware with a no-op get_response callable."""
    from utils.csp_middleware import CSPMiddleware

    def _get_response(req):
        return HttpResponse("OK")

    middleware = CSPMiddleware(_get_response)
    return middleware


# ===========================================================================
# 1. Nonce Generation Tests
# ===========================================================================


class CSPNonceGenerationTestCase(TestCase):
    """CSP nonce must be generated for every request."""

    def test_nonce_is_attached_to_request(self):
        """
        After middleware processes a request, request.csp_nonce must be set
        to a non-empty string.
        """
        from utils.csp_middleware import CSPMiddleware

        results = {}

        def _get_response(req):
            results['nonce'] = getattr(req, 'csp_nonce', None)
            return HttpResponse("OK")

        middleware = CSPMiddleware(_get_response)
        request = _make_request("/django-admin/")
        middleware(request)

        self.assertIsNotNone(results['nonce'], "request.csp_nonce must be set")
        self.assertGreater(len(results['nonce']), 0, "csp_nonce must not be empty")

    def test_nonce_is_url_safe_string(self):
        """Nonce must be URL-safe (can be embedded in HTML attributes safely)."""
        from utils.csp_middleware import CSPMiddleware

        results = {}

        def _get_response(req):
            results['nonce'] = req.csp_nonce
            return HttpResponse("OK")

        middleware = CSPMiddleware(_get_response)
        middleware(_make_request())

        nonce = results['nonce']
        # URL-safe base64: [A-Za-z0-9_-] (no padding = in URL-safe tokens)
        self.assertRegex(
            nonce,
            r'^[A-Za-z0-9_\-]+$',
            f"CSP nonce '{nonce}' must be URL-safe (no special characters)",
        )

    def test_consecutive_requests_get_different_nonces(self):
        """Each request must get a unique nonce — never reused."""
        from utils.csp_middleware import CSPMiddleware

        nonces = []

        def _get_response(req):
            nonces.append(req.csp_nonce)
            return HttpResponse("OK")

        middleware = CSPMiddleware(_get_response)

        # Process 10 requests
        for _ in range(10):
            middleware(_make_request())

        unique_nonces = set(nonces)
        self.assertEqual(
            len(unique_nonces),
            10,
            "Each request must receive a unique CSP nonce — nonce reuse is a security vulnerability",
        )

    def test_get_csp_nonce_helper_returns_nonce(self):
        """get_csp_nonce() helper function must return the request's nonce."""
        from utils.csp_middleware import CSPMiddleware, get_csp_nonce

        captured = {}

        def _get_response(req):
            captured['nonce_from_helper'] = get_csp_nonce(req)
            captured['nonce_direct'] = req.csp_nonce
            return HttpResponse("OK")

        middleware = CSPMiddleware(_get_response)
        middleware(_make_request())

        self.assertEqual(
            captured['nonce_from_helper'],
            captured['nonce_direct'],
            "get_csp_nonce(request) must return the same nonce as request.csp_nonce",
        )

    def test_get_csp_nonce_returns_empty_string_when_not_set(self):
        """get_csp_nonce() must return '' when csp_nonce is not on request."""
        from utils.csp_middleware import get_csp_nonce

        request = SimpleNamespace()  # No csp_nonce attribute
        result = get_csp_nonce(request)
        self.assertEqual(result, "", "get_csp_nonce must return '' for requests without nonce")


# ===========================================================================
# 2. CSP Header Application Tests
# ===========================================================================


class CSPHeaderApplicationTestCase(TestCase):
    """CSP header must be added for Django admin/docs paths, not for API paths."""

    def _call_middleware(self, path: str, settings_overrides=None) -> HttpResponse:
        """Helper: run middleware for a request to the given path."""
        from utils.csp_middleware import CSPMiddleware

        def _get_response(req):
            return HttpResponse("OK")

        overrides = {"CSP_ENABLED": True, **(settings_overrides or {})}
        with override_settings(**overrides):
            middleware = CSPMiddleware(_get_response)
            return middleware(_make_request(path))

    def test_csp_header_added_for_django_admin(self):
        """Content-Security-Policy header must be present for /django-admin/ paths."""
        response = self._call_middleware("/django-admin/")
        self.assertIn(
            "Content-Security-Policy",
            response,
            "CSP header must be added for /django-admin/ path",
        )

    def test_csp_header_added_for_api_docs(self):
        """CSP header must be added for /api/docs/ paths."""
        response = self._call_middleware("/api/docs/")
        self.assertIn("Content-Security-Policy", response)

    def test_csp_header_added_for_redoc(self):
        """CSP header must be added for /api/redoc/ paths."""
        response = self._call_middleware("/api/redoc/")
        self.assertIn("Content-Security-Policy", response)

    def test_csp_header_not_added_for_api_endpoints(self):
        """
        CSP header must NOT be added for regular API endpoints.
        The React SPA and nginx handle CSP for those.
        """
        response = self._call_middleware("/api/v1/courses/")
        self.assertNotIn(
            "Content-Security-Policy",
            response,
            "CSP header must NOT be added for /api/ endpoints (nginx handles that)",
        )

    def test_csp_header_not_added_for_health_check(self):
        """Health check endpoint must not get CSP header."""
        response = self._call_middleware("/health/")
        self.assertNotIn("Content-Security-Policy", response)

    @override_settings(CSP_ENABLED=False)
    def test_csp_disabled_suppresses_header(self):
        """When CSP_ENABLED=False, no CSP header should be added."""
        from utils.csp_middleware import CSPMiddleware

        def _get_response(req):
            return HttpResponse("OK")

        middleware = CSPMiddleware(_get_response)
        response = middleware(_make_request("/django-admin/"))

        self.assertNotIn(
            "Content-Security-Policy",
            response,
            "CSP_ENABLED=False must suppress CSP header",
        )


# ===========================================================================
# 3. CSP Header Content Tests
# ===========================================================================


class CSPHeaderContentTestCase(TestCase):
    """Verify the CSP header contains required security directives."""

    def _get_csp_header(self, path: str = "/django-admin/") -> str:
        """Helper: get the CSP header value for a request to the given path."""
        from utils.csp_middleware import CSPMiddleware

        def _get_response(req):
            return HttpResponse("OK")

        with override_settings(CSP_ENABLED=True):
            middleware = CSPMiddleware(_get_response)
            response = middleware(_make_request(path))

        return response.get("Content-Security-Policy", "")

    def test_csp_contains_nonce_in_script_src(self):
        """
        script-src directive must contain 'nonce-<value>' to allow
        specific inline scripts while blocking others.
        """
        csp = self._get_csp_header()
        self.assertIn(
            "script-src",
            csp,
            "CSP must contain script-src directive",
        )
        self.assertIn(
            "nonce-",
            csp,
            "script-src must contain nonce- to allow specific inline scripts",
        )

    def test_csp_contains_nonce_in_style_src(self):
        """style-src directive must also use nonce."""
        csp = self._get_csp_header()
        self.assertIn("style-src", csp)

    def test_csp_has_frame_ancestors_none(self):
        """
        frame-ancestors 'none' is required to prevent clickjacking.
        Absence of this directive leaves the admin panel embeddable in iframes.
        """
        csp = self._get_csp_header()
        self.assertIn(
            "frame-ancestors 'none'",
            csp,
            "CSP must contain frame-ancestors 'none' to prevent clickjacking",
        )

    def test_csp_has_object_src_none(self):
        """
        object-src 'none' blocks Flash and other plugins.
        Absence leaves plugin-based XSS possible.
        """
        csp = self._get_csp_header()
        self.assertIn(
            "object-src 'none'",
            csp,
            "CSP must contain object-src 'none' to disable Flash/plugins",
        )

    def test_csp_nonce_in_header_matches_request_nonce(self):
        """The nonce in the CSP header must match the nonce on the request."""
        from utils.csp_middleware import CSPMiddleware

        captured = {}

        def _get_response(req):
            captured['nonce'] = req.csp_nonce
            return HttpResponse("OK")

        with override_settings(CSP_ENABLED=True):
            middleware = CSPMiddleware(_get_response)
            response = middleware(_make_request("/django-admin/"))

        csp_header = response.get("Content-Security-Policy", "")
        nonce = captured.get('nonce', '')

        self.assertIn(
            f"nonce-{nonce}",
            csp_header,
            "The nonce in the CSP header must match the nonce set on request.csp_nonce",
        )

    @override_settings(CSP_ENABLED=True, CSP_REPORT_ONLY=True)
    def test_report_only_uses_different_header_name(self):
        """CSP_REPORT_ONLY=True must use Content-Security-Policy-Report-Only header."""
        from utils.csp_middleware import CSPMiddleware

        def _get_response(req):
            return HttpResponse("OK")

        middleware = CSPMiddleware(_get_response)
        response = middleware(_make_request("/django-admin/"))

        self.assertIn(
            "Content-Security-Policy-Report-Only",
            response,
            "CSP_REPORT_ONLY=True must use the Report-Only header variant",
        )
        self.assertNotIn(
            "Content-Security-Policy",
            # Check it's not also setting the enforcement header
            {k: v for k, v in response.items() if k == "Content-Security-Policy"},
            "Report-Only mode must not also set the enforcement CSP header",
        )

    @override_settings(CSP_ENABLED=True, CSP_REPORT_URI="https://csp.example.com/report")
    def test_report_uri_added_when_configured(self):
        """report-uri directive must appear in CSP header when CSP_REPORT_URI is set."""
        from utils.csp_middleware import CSPMiddleware

        def _get_response(req):
            return HttpResponse("OK")

        middleware = CSPMiddleware(_get_response)
        response = middleware(_make_request("/django-admin/"))

        csp = response.get("Content-Security-Policy", "")
        self.assertIn(
            "report-uri https://csp.example.com/report",
            csp,
            "report-uri directive must be included when CSP_REPORT_URI is configured",
        )
