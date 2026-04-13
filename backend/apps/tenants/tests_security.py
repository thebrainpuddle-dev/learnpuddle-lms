# apps/tenants/tests_security.py
"""
P0 Security Fix Verification Tests — Tenant Isolation & Middleware.

Covers:
- contextvars tenant isolation: each request context is fully isolated
- Middleware clears tenant BEFORE each request (stale state cannot bleed)
- Middleware clears tenant AFTER each request
- Cross-tenant access is blocked at the middleware level (403)
- SUPER_ADMIN bypass works across tenants
- Users cannot reach another tenant's API even with a valid JWT

These tests correspond to the P0 security fix that replaced
`threading.local()` with `contextvars.ContextVar` for tenant storage.
The old threading.local approach leaked tenant context across coroutines
sharing the same OS thread in ASGI/Channels deployments.
"""

import contextvars
from django.http import JsonResponse
from django.test import TestCase, RequestFactory, override_settings
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User
from utils.tenant_middleware import (
    TenantMiddleware,
    get_current_tenant,
    set_current_tenant,
    clear_current_tenant,
    _current_tenant,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_view(request):
    """Minimal view that returns the current tenant id (or 'none')."""
    t = get_current_tenant()
    return JsonResponse({"tenant": str(t.id) if t else "none"})


def _make_tenant(name, subdomain, email):
    return Tenant.objects.create(
        name=name, slug=subdomain, subdomain=subdomain, email=email
    )


def _make_user(email, tenant, role="TEACHER", first="Test", last="User"):
    return User.objects.create_user(
        email=email,
        password="pass123",
        first_name=first,
        last_name=last,
        tenant=tenant,
        role=role,
    )


# ===========================================================================
# 1. contextvars Isolation Tests
# ===========================================================================

class ContextvarsIsolationTestCase(TestCase):
    """
    Verify that contextvars.ContextVar correctly scopes tenant per-context.

    The key security property: if Context A sets tenant=X, that must NOT
    be visible from a freshly-created Context B (or the default context).
    This mirrors the ASGI request model where each request runs in an
    independent asyncio context.
    """

    def setUp(self):
        self.tenant_a = _make_tenant("School A", "sec-a", "a@sec.com")
        self.tenant_b = _make_tenant("School B", "sec-b", "b@sec.com")

    def tearDown(self):
        clear_current_tenant()

    # ------------------------------------------------------------------ #
    # Basic get/set/clear                                                  #
    # ------------------------------------------------------------------ #

    def test_set_current_tenant_is_visible_in_same_context(self):
        set_current_tenant(self.tenant_a)
        self.assertEqual(get_current_tenant(), self.tenant_a)

    def test_clear_current_tenant_returns_none(self):
        set_current_tenant(self.tenant_a)
        clear_current_tenant()
        self.assertIsNone(get_current_tenant())

    def test_default_context_has_no_tenant(self):
        """Without any set, the contextvar default is None."""
        clear_current_tenant()
        self.assertIsNone(get_current_tenant())

    def test_overwrite_tenant_is_visible(self):
        set_current_tenant(self.tenant_a)
        set_current_tenant(self.tenant_b)
        self.assertEqual(get_current_tenant(), self.tenant_b)

    # ------------------------------------------------------------------ #
    # copy_context() isolation — the ASGI safety property                 #
    # ------------------------------------------------------------------ #

    def test_child_context_copy_sees_parent_value_at_fork_time(self):
        """
        When a context is copied (copy_context()), the child starts with
        the parent's current value.  This is the expected behaviour for
        asyncio tasks spawned from a request handler.
        """
        set_current_tenant(self.tenant_a)
        child_ctx = contextvars.copy_context()

        result = {}

        def read_tenant():
            result["tenant"] = get_current_tenant()

        child_ctx.run(read_tenant)
        # Child sees the forked value
        self.assertEqual(result["tenant"], self.tenant_a)

    def test_child_context_mutation_does_not_affect_parent(self):
        """
        Mutations inside a copied context MUST NOT bleed back to the
        parent context.  This is the ASGI-safety guarantee: a response
        handler for Tenant A cannot contaminate the next request.
        """
        set_current_tenant(self.tenant_a)
        child_ctx = contextvars.copy_context()

        def mutate_tenant():
            _current_tenant.set(self.tenant_b)

        child_ctx.run(mutate_tenant)

        # Parent context is unaffected
        self.assertEqual(get_current_tenant(), self.tenant_a)

    def test_two_independent_contexts_are_isolated(self):
        """
        Two independently-created contexts (simulating two concurrent ASGI
        requests) each have their own tenant value with no cross-bleed.
        """
        clear_current_tenant()

        ctx_a = contextvars.copy_context()
        ctx_b = contextvars.copy_context()

        results = {}

        def run_a():
            _current_tenant.set(self.tenant_a)
            results["a_during"] = get_current_tenant()

        def run_b():
            _current_tenant.set(self.tenant_b)
            results["b_during"] = get_current_tenant()

        ctx_a.run(run_a)
        ctx_b.run(run_b)

        self.assertEqual(results["a_during"], self.tenant_a)
        self.assertEqual(results["b_during"], self.tenant_b)

        # Parent context still has None (unaffected by children)
        self.assertIsNone(get_current_tenant())

    def test_context_value_after_request_is_cleared(self):
        """
        After a request finishes, the tenant stored in the contextvar
        must be None, so the next request starts clean.
        """
        set_current_tenant(self.tenant_a)
        # Simulate middleware post-request cleanup
        clear_current_tenant()
        self.assertIsNone(get_current_tenant())


# ===========================================================================
# 2. TenantMiddleware Lifecycle Tests
# ===========================================================================

@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class TenantMiddlewareLifecycleTestCase(TestCase):
    """
    Verify that TenantMiddleware correctly clears tenant state at the
    start and end of every request, preventing stale-context bleed.
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.tenant = _make_tenant("MW School", "mwtest", "mw@test.com")
        self.tenant_a = _make_tenant("MW School A", "mwa", "mwa@test.com")
        self.tenant_b = _make_tenant("MW School B", "mwb", "mwb@test.com")

    def tearDown(self):
        clear_current_tenant()

    def test_middleware_clears_stale_tenant_before_new_request(self):
        """
        Even if a previous request left tenant in the contextvar,
        the middleware must clear it before processing the next request.
        """
        # Simulate stale state from a previous request (shouldn't happen in
        # production with correct middleware, but this is the regression test)
        set_current_tenant(self.tenant_a)

        middleware = TenantMiddleware(_simple_view)
        request = self.factory.get("/api/test/", HTTP_HOST="mwb.lms.com")
        request.user = type("User", (), {"is_authenticated": False})()

        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        # After the request the stale tenant_a should no longer be active
        self.assertIsNone(get_current_tenant())

    def test_middleware_clears_tenant_after_response(self):
        """
        After the middleware processes a request, the tenant context
        variable must be None (even when request succeeds).
        """
        middleware = TenantMiddleware(_simple_view)
        request = self.factory.get("/api/test/", HTTP_HOST="mwtest.lms.com")
        request.user = type("User", (), {"is_authenticated": False})()

        middleware(request)

        self.assertIsNone(get_current_tenant())

    def test_middleware_clears_tenant_after_exception(self):
        """
        If the view raises an exception, the middleware must still clear
        the tenant context to avoid contaminating the next request.
        """
        def _raising_view(request):
            raise RuntimeError("Unexpected error in view")

        middleware = TenantMiddleware(_raising_view)
        request = self.factory.get("/api/test/", HTTP_HOST="mwtest.lms.com")
        request.user = type("User", (), {"is_authenticated": False})()

        # The middleware catches unknown exceptions and returns 500
        response = middleware(request)

        self.assertEqual(response.status_code, 500)
        # Crucially: tenant is still cleared
        self.assertIsNone(get_current_tenant())

    def test_health_endpoint_skips_tenant_resolution(self):
        """
        /health/* endpoints must skip tenant resolution entirely (no
        database queries, no middleware side effects).
        """
        middleware = TenantMiddleware(_simple_view)
        request = self.factory.get("/health/", HTTP_HOST="anything.lms.com")
        request.user = type("User", (), {"is_authenticated": False})()

        response = middleware(request)

        self.assertEqual(response.status_code, 200)

    def test_sequential_requests_to_different_tenants_resolve_independently(self):
        """
        Two sequential requests to different tenants must each resolve
        their own tenant independently (no cross-bleed).
        """
        resolved = []

        def _capture_tenant_view(request):
            resolved.append(get_current_tenant())
            return JsonResponse({"ok": True})

        middleware = TenantMiddleware(_capture_tenant_view)

        req_a = self.factory.get("/api/test/", HTTP_HOST="mwa.lms.com")
        req_a.user = type("User", (), {"is_authenticated": False})()

        req_b = self.factory.get("/api/test/", HTTP_HOST="mwb.lms.com")
        req_b.user = type("User", (), {"is_authenticated": False})()

        middleware(req_a)
        middleware(req_b)

        self.assertEqual(len(resolved), 2)
        self.assertIsNotNone(resolved[0])
        self.assertIsNotNone(resolved[1])
        # Each request resolved its own tenant
        self.assertEqual(resolved[0].subdomain, "mwa")
        self.assertEqual(resolved[1].subdomain, "mwb")
        # The two are distinct tenant objects
        self.assertNotEqual(resolved[0].id, resolved[1].id)


# ===========================================================================
# 3. Cross-Tenant API Access Tests
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["a.lms.com", "b.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class CrossTenantAccessTestCase(TestCase):
    """
    Verify that a user belonging to Tenant A cannot access Tenant B's API,
    even with a fully valid JWT.  The TenantMiddleware must enforce this.
    """

    def setUp(self):
        self.tenant_a = _make_tenant("Access School A", "a", "access-a@lms.com")
        self.tenant_b = _make_tenant("Access School B", "b", "access-b@lms.com")

        self.user_a = _make_user("user@a.com", self.tenant_a, role="SCHOOL_ADMIN")
        self.user_b = _make_user("user@b.com", self.tenant_b, role="SCHOOL_ADMIN")

    def test_tenant_a_user_gets_403_on_tenant_b_host(self):
        """A user from Tenant A is forbidden on Tenant B's subdomain."""
        client = APIClient()
        client.force_authenticate(user=self.user_a)
        response = client.get("/api/v1/courses/", HTTP_HOST="b.lms.com")
        self.assertEqual(response.status_code, 403)

    def test_tenant_b_user_gets_403_on_tenant_a_host(self):
        """A user from Tenant B is forbidden on Tenant A's subdomain."""
        client = APIClient()
        client.force_authenticate(user=self.user_b)
        response = client.get("/api/v1/courses/", HTTP_HOST="a.lms.com")
        self.assertEqual(response.status_code, 403)

    def test_tenant_a_user_can_access_own_tenant_host(self):
        """Sanity check: a user can still access their own tenant's API."""
        client = APIClient()
        client.force_authenticate(user=self.user_a)
        response = client.get("/api/v1/courses/", HTTP_HOST="a.lms.com")
        # 200 (list) or 403/401 from role check are all OK; 403 from tenant
        # mismatch would mean the middleware is broken.
        self.assertNotEqual(response.status_code, 403)

    def test_super_admin_can_access_any_tenant_host(self):
        """SUPER_ADMIN is exempt from the tenant-membership check."""
        super_admin = _make_user(
            "superadmin@platform.com", self.tenant_a, role="SUPER_ADMIN", first="Super", last="Admin"
        )
        client = APIClient()
        client.force_authenticate(user=super_admin)
        # Accessing Tenant B's host as SUPER_ADMIN should NOT return 403
        response = client.get("/api/v1/courses/", HTTP_HOST="b.lms.com")
        self.assertNotEqual(response.status_code, 403)

    def test_unauthenticated_request_is_not_blocked_by_tenant_check(self):
        """
        Unauthenticated requests should not get a 403 from the *tenant*
        membership check (they may still get 401 from auth layer).
        """
        client = APIClient()
        response = client.get("/api/v1/courses/", HTTP_HOST="a.lms.com")
        # Should be 401 (auth), NOT 403 (tenant mismatch)
        self.assertEqual(response.status_code, 401)


# ===========================================================================
# 4. Password Security Tests
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["pw.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class PasswordSecurityTestCase(TestCase):
    """
    Verify that password operations don't double-hash credentials.

    The P0 bug: some code paths were calling `set_password()` on an
    already-hashed password (or `create_user()` on a pre-hashed string),
    causing bcrypt-on-bcrypt hashing that makes all passwords invalid.
    These tests prove: create → login, change → re-login all work end-to-end.
    """

    HOST = "pw.lms.com"

    def setUp(self):
        self.client = APIClient()
        self.tenant = _make_tenant("PW School", "pw", "pw@pwschool.com")

    def test_newly_created_user_can_login_immediately(self):
        """User created via create_user() must be able to log in."""
        user = _make_user("fresh@pw.com", self.tenant, role="TEACHER")
        response = self.client.post(
            "/api/users/auth/login/",
            {"email": "fresh@pw.com", "password": "pass123"},
            HTTP_HOST=self.HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("tokens", response.data)

    def test_password_change_does_not_double_hash(self):
        """
        Changing a password via the API and then logging in with the new
        password must succeed.  If double-hashing occurred, the login
        would fail with 400/401.
        """
        user = _make_user("chpw@pw.com", self.tenant, role="TEACHER")
        self.client.force_authenticate(user=user)

        change_resp = self.client.post(
            "/api/users/auth/change-password/",
            {
                "old_password": "pass123",
                "new_password": "NewSecure!999",
                "new_password_confirm": "NewSecure!999",
            },
            HTTP_HOST=self.HOST,
        )
        self.assertEqual(change_resp.status_code, 200)

        # Clear auth, then log in with new password
        self.client.credentials()
        login_resp = self.client.post(
            "/api/users/auth/login/",
            {"email": "chpw@pw.com", "password": "NewSecure!999"},
            HTTP_HOST=self.HOST,
        )
        self.assertEqual(login_resp.status_code, 200)
        self.assertIn("tokens", login_resp.data)

    def test_old_password_does_not_work_after_change(self):
        """After a successful password change, the old password must be rejected."""
        user = _make_user("oldpw@pw.com", self.tenant, role="TEACHER")
        self.client.force_authenticate(user=user)

        self.client.post(
            "/api/users/auth/change-password/",
            {
                "old_password": "pass123",
                "new_password": "BrandNew!999",
                "new_password_confirm": "BrandNew!999",
            },
            HTTP_HOST=self.HOST,
        )

        self.client.credentials()
        login_resp = self.client.post(
            "/api/users/auth/login/",
            {"email": "oldpw@pw.com", "password": "pass123"},
            HTTP_HOST=self.HOST,
        )
        self.assertEqual(login_resp.status_code, 400)

    def test_password_reset_allows_login_with_new_password(self):
        """
        The full reset flow (request → confirm) must result in a usable
        new password without any double-hashing.
        """
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes

        user = _make_user("reset@pw.com", self.tenant, role="TEACHER")
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        confirm_resp = self.client.post(
            "/api/users/auth/confirm-password-reset/",
            {"uid": uid, "token": token, "new_password": "AfterReset!123"},
            HTTP_HOST=self.HOST,
        )
        self.assertEqual(confirm_resp.status_code, 200)

        login_resp = self.client.post(
            "/api/users/auth/login/",
            {"email": "reset@pw.com", "password": "AfterReset!123"},
            HTTP_HOST=self.HOST,
        )
        self.assertEqual(login_resp.status_code, 200)
        self.assertIn("tokens", login_resp.data)


# ===========================================================================
# 5. Tenant Manager Isolation Tests
# ===========================================================================

class TenantManagerIsolationTestCase(TestCase):
    """
    Verify that TenantManager auto-filters correctly and data from
    one tenant cannot be retrieved in another tenant's context.
    """

    def setUp(self):
        self.tenant_a = _make_tenant("Mgr School A", "mgra", "mgra@t.com")
        self.tenant_b = _make_tenant("Mgr School B", "mgrb", "mgrb@t.com")

    def tearDown(self):
        clear_current_tenant()

    def test_objects_all_scoped_to_current_tenant(self):
        """
        TenantManager.all() returns only objects belonging to the
        currently-set tenant.
        """
        # Create a user in each tenant
        user_a = _make_user("ua@mgra.com", self.tenant_a)
        user_b = _make_user("ub@mgrb.com", self.tenant_b)

        set_current_tenant(self.tenant_a)
        from apps.users.models import User
        users_in_a = list(User.objects.filter(role="TEACHER").values_list("email", flat=True))

        self.assertIn("ua@mgra.com", users_in_a)
        self.assertNotIn("ub@mgrb.com", users_in_a)

    def test_all_tenants_bypass_returns_everything(self):
        """
        TenantManager.all_tenants() must bypass filtering.
        """
        _make_user("ua2@mgra.com", self.tenant_a)
        _make_user("ub2@mgrb.com", self.tenant_b)

        set_current_tenant(self.tenant_a)
        from apps.users.models import User
        all_users = list(User.objects.all_tenants().filter(role="TEACHER").values_list("email", flat=True))

        self.assertIn("ua2@mgra.com", all_users)
        self.assertIn("ub2@mgrb.com", all_users)

    def test_no_tenant_context_returns_all_records(self):
        """
        When no tenant is set (e.g. management commands), TenantManager
        must return all records rather than raising an error.
        """
        clear_current_tenant()
        _make_user("ua3@mgra.com", self.tenant_a)
        _make_user("ub3@mgrb.com", self.tenant_b)

        from apps.users.models import User
        # filter_by_tenant falls through to unfiltered when tenant is None
        count = User.objects.filter(role="TEACHER").count()
        self.assertGreaterEqual(count, 2)
