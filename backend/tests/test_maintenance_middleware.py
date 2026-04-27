# tests/test_maintenance_middleware.py
"""
Tests for utils/maintenance_middleware.py — MaintenanceModeWriteBlockMiddleware.

Covers:
1. GET/HEAD/OPTIONS requests always pass through (safe methods)
2. Write requests (POST/PUT/PATCH/DELETE) blocked when maintenance_mode_enabled=True
3. SUPER_ADMIN write requests always pass through
4. Auth endpoints are always exempt
5. Health check always exempt
6. Django admin always exempt
7. Super-admin API endpoints always exempt
8. maintenance_ends_at timestamp included in 503 response
9. Non-maintenance tenant write requests pass through normally
10. Tenant without maintenance mode passes through normally
"""

from types import SimpleNamespace
from django.http import HttpResponse
from django.test import TestCase


# ===========================================================================
# Helpers
# ===========================================================================

def _make_tenant(maintenance: bool = False, ends_at=None):
    """Minimal mock tenant for middleware tests."""
    tenant = SimpleNamespace(
        maintenance_mode_enabled=maintenance,
        maintenance_mode_ends_at=ends_at,
    )
    return tenant


def _make_user(role: str = "SCHOOL_ADMIN", is_authenticated: bool = True):
    """Minimal mock user."""
    return SimpleNamespace(
        role=role,
        is_authenticated=is_authenticated,
    )


def _make_middleware():
    """Instantiate MaintenanceModeWriteBlockMiddleware with a passing get_response."""
    from utils.maintenance_middleware import MaintenanceModeWriteBlockMiddleware

    def _get_response(req):
        return HttpResponse("OK", status=200)

    return MaintenanceModeWriteBlockMiddleware(_get_response)


def _make_request(
    method: str = "POST",
    path: str = "/api/v1/courses/",
    user=None,
    tenant=None,
):
    """Create a minimal mock request."""
    return SimpleNamespace(
        method=method,
        path=path,
        user=user or _make_user(),
        tenant=tenant,
    )


# ===========================================================================
# 1. Safe Method Tests (GET/HEAD/OPTIONS)
# ===========================================================================


class SafeMethodTestCase(TestCase):
    """Safe HTTP methods must always pass through, regardless of maintenance mode."""

    def setUp(self):
        self.middleware = _make_middleware()

    def test_get_passes_through_in_maintenance_mode(self):
        """GET must pass through even when tenant is in maintenance mode."""
        tenant = _make_tenant(maintenance=True)
        request = _make_request(method="GET", tenant=tenant)

        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    def test_head_passes_through_in_maintenance_mode(self):
        """HEAD must pass through in maintenance mode."""
        tenant = _make_tenant(maintenance=True)
        request = _make_request(method="HEAD", tenant=tenant)

        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    def test_options_passes_through_in_maintenance_mode(self):
        """OPTIONS (CORS preflight) must always pass through."""
        tenant = _make_tenant(maintenance=True)
        request = _make_request(method="OPTIONS", tenant=tenant)

        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)


# ===========================================================================
# 2. Write Blocking Tests
# ===========================================================================


class WriteBlockingTestCase(TestCase):
    """Write methods (POST/PUT/PATCH/DELETE) must be blocked during maintenance."""

    def setUp(self):
        self.middleware = _make_middleware()
        self.tenant = _make_tenant(maintenance=True)
        self.user = _make_user(role="SCHOOL_ADMIN")

    def test_post_blocked_in_maintenance_mode(self):
        """POST must be blocked when tenant has maintenance_mode_enabled=True."""
        request = _make_request(method="POST", tenant=self.tenant, user=self.user)

        response = self.middleware(request)
        self.assertEqual(
            response.status_code,
            503,
            "POST must return 503 when tenant is in maintenance mode",
        )

    def test_put_blocked_in_maintenance_mode(self):
        """PUT must be blocked during maintenance mode."""
        request = _make_request(method="PUT", tenant=self.tenant, user=self.user)

        response = self.middleware(request)
        self.assertEqual(response.status_code, 503)

    def test_patch_blocked_in_maintenance_mode(self):
        """PATCH must be blocked during maintenance mode."""
        request = _make_request(method="PATCH", tenant=self.tenant, user=self.user)

        response = self.middleware(request)
        self.assertEqual(response.status_code, 503)

    def test_delete_blocked_in_maintenance_mode(self):
        """DELETE must be blocked during maintenance mode."""
        request = _make_request(method="DELETE", tenant=self.tenant, user=self.user)

        response = self.middleware(request)
        self.assertEqual(response.status_code, 503)

    def test_503_response_has_maintenance_mode_flag(self):
        """503 JSON response must include maintenance_mode=True."""
        import json

        request = _make_request(method="POST", tenant=self.tenant, user=self.user)
        response = self.middleware(request)

        data = json.loads(response.content)
        self.assertTrue(
            data.get("maintenance_mode"),
            "503 response must include maintenance_mode=True",
        )

    def test_503_response_has_maintenance_ends_at_when_set(self):
        """If maintenance_mode_ends_at is set, it must appear in the 503 response."""
        import json
        from datetime import datetime, timezone

        ends_at = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        tenant = _make_tenant(maintenance=True, ends_at=ends_at)
        request = _make_request(method="POST", tenant=tenant, user=self.user)

        response = self.middleware(request)
        data = json.loads(response.content)

        self.assertIn(
            "maintenance_ends_at",
            data,
            "503 response must include maintenance_ends_at timestamp",
        )
        self.assertIsNotNone(data["maintenance_ends_at"])

    def test_503_response_has_null_maintenance_ends_at_when_not_set(self):
        """If maintenance_mode_ends_at is None, response must have null for that field."""
        import json

        tenant = _make_tenant(maintenance=True, ends_at=None)
        request = _make_request(method="POST", tenant=tenant, user=self.user)

        response = self.middleware(request)
        data = json.loads(response.content)

        self.assertIsNone(
            data.get("maintenance_ends_at"),
            "maintenance_ends_at must be null when not scheduled",
        )


# ===========================================================================
# 3. Non-Maintenance Mode Tests
# ===========================================================================


class NonMaintenanceModeTestCase(TestCase):
    """Write requests must pass through when tenant is NOT in maintenance mode."""

    def setUp(self):
        self.middleware = _make_middleware()

    def test_post_passes_through_when_no_maintenance(self):
        """POST must succeed when tenant is NOT in maintenance mode."""
        tenant = _make_tenant(maintenance=False)
        request = _make_request(method="POST", tenant=tenant, user=_make_user())

        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    def test_post_passes_through_when_no_tenant(self):
        """POST must pass through when request has no tenant (public endpoints)."""
        request = _make_request(method="POST", tenant=None, user=_make_user())

        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)


# ===========================================================================
# 4. SUPER_ADMIN Bypass Tests
# ===========================================================================


class SuperAdminBypassTestCase(TestCase):
    """SUPER_ADMIN must bypass maintenance mode block for write operations."""

    def setUp(self):
        self.middleware = _make_middleware()
        self.tenant = _make_tenant(maintenance=True)

    def test_super_admin_can_post_in_maintenance_mode(self):
        """SUPER_ADMIN POST must not be blocked even in maintenance mode."""
        user = _make_user(role="SUPER_ADMIN")
        request = _make_request(method="POST", tenant=self.tenant, user=user)

        response = self.middleware(request)
        self.assertEqual(
            response.status_code,
            200,
            "SUPER_ADMIN must bypass maintenance mode write block",
        )

    def test_super_admin_can_delete_in_maintenance_mode(self):
        """SUPER_ADMIN DELETE must not be blocked."""
        user = _make_user(role="SUPER_ADMIN")
        request = _make_request(method="DELETE", tenant=self.tenant, user=user)

        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    def test_school_admin_blocked_in_maintenance_mode(self):
        """SCHOOL_ADMIN is NOT exempt — must be blocked in maintenance mode."""
        user = _make_user(role="SCHOOL_ADMIN")
        request = _make_request(method="POST", tenant=self.tenant, user=user)

        response = self.middleware(request)
        self.assertEqual(response.status_code, 503)

    def test_teacher_blocked_in_maintenance_mode(self):
        """TEACHER role must be blocked in maintenance mode."""
        user = _make_user(role="TEACHER")
        request = _make_request(method="POST", tenant=self.tenant, user=user)

        response = self.middleware(request)
        self.assertEqual(response.status_code, 503)


# ===========================================================================
# 5. Exempt Path Tests
# ===========================================================================


class ExemptPathTestCase(TestCase):
    """Certain paths must always pass through regardless of maintenance mode."""

    def setUp(self):
        self.middleware = _make_middleware()
        self.tenant = _make_tenant(maintenance=True)
        self.user = _make_user(role="SCHOOL_ADMIN")

    def _post_to(self, path: str) -> int:
        request = _make_request(method="POST", path=path, tenant=self.tenant, user=self.user)
        return self.middleware(request).status_code

    def test_health_check_exempt(self):
        """/health/ is always exempt."""
        self.assertEqual(self._post_to("/health/"), 200)

    def test_auth_endpoints_exempt(self):
        """/api/users/auth/ endpoints must always pass through (login, refresh)."""
        self.assertEqual(self._post_to("/api/users/auth/login/"), 200)
        self.assertEqual(self._post_to("/api/v1/users/auth/refresh/"), 200)

    def test_django_admin_exempt(self):
        """/django-admin/ is always exempt (for platform maintenance)."""
        self.assertEqual(self._post_to("/django-admin/login/"), 200)

    def test_super_admin_api_exempt(self):
        """/api/super-admin/ is always exempt (for emergency ops)."""
        self.assertEqual(self._post_to("/api/super-admin/tenants/"), 200)
        self.assertEqual(self._post_to("/api/v1/super-admin/tenants/"), 200)

    def test_regular_api_not_exempt(self):
        """/api/v1/courses/ is NOT exempt and must be blocked."""
        self.assertEqual(self._post_to("/api/v1/courses/"), 503)
