# tests/test_contextvars_isolation.py
"""
Extended tenant isolation tests using contextvars.

These tests verify the P0 security fix (threading.local -> contextvars)
at the ORM level, ensuring that TenantManager auto-filtering correctly
interacts with the contextvars-based tenant storage across:
- Multiple model types
- Nested context runs (simulating ASGI coroutines)
- Edge cases: empty tenants, deleted tenants, inactive tenants
"""

import contextvars
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.courses.models import Course, Module, Content
from utils.tenant_middleware import (
    _current_tenant,
    get_current_tenant,
    set_current_tenant,
    clear_current_tenant,
)


def _make_tenant(name, subdomain, email, is_active=True):
    return Tenant.objects.create(
        name=name, slug=subdomain, subdomain=subdomain,
        email=email, is_active=is_active,
    )


def _make_user(email, tenant, role="TEACHER"):
    return User.objects.create_user(
        email=email, password="pass123",
        first_name="Test", last_name="User",
        tenant=tenant, role=role,
    )


def _make_course(tenant, admin, title, slug):
    return Course.objects.create(
        tenant=tenant, title=title, slug=slug,
        description="Test", created_by=admin,
        is_published=True, is_active=True,
    )


class ContextvarsMultiModelIsolationTestCase(TestCase):
    """
    Verify that contextvars tenant isolation works across multiple
    model types that use TenantManager.
    """

    def setUp(self):
        self.tenant_a = _make_tenant("Multi A", "multa", "multa@test.com")
        self.tenant_b = _make_tenant("Multi B", "multb", "multb@test.com")

        self.admin_a = _make_user("admin@multa.com", self.tenant_a, role="SCHOOL_ADMIN")
        self.admin_b = _make_user("admin@multb.com", self.tenant_b, role="SCHOOL_ADMIN")

        self.teacher_a = _make_user("teacher@multa.com", self.tenant_a)
        self.teacher_b = _make_user("teacher@multb.com", self.tenant_b)

        self.course_a = _make_course(self.tenant_a, self.admin_a, "Course A", "multi-course-a")
        self.course_b = _make_course(self.tenant_b, self.admin_b, "Course B", "multi-course-b")

    def tearDown(self):
        clear_current_tenant()

    def test_user_model_filtered_by_tenant(self):
        """User queries should be scoped by tenant context."""
        set_current_tenant(self.tenant_a)
        emails = list(User.objects.filter(role="TEACHER").values_list("email", flat=True))
        self.assertIn("teacher@multa.com", emails)
        self.assertNotIn("teacher@multb.com", emails)

    def test_course_model_filtered_by_tenant(self):
        """Course queries should be scoped by tenant context."""
        set_current_tenant(self.tenant_b)
        titles = list(Course.objects.values_list("title", flat=True))
        self.assertIn("Course B", titles)
        self.assertNotIn("Course A", titles)

    def test_multiple_models_all_scoped_consistently(self):
        """When tenant is set, ALL tenant-aware models filter consistently."""
        set_current_tenant(self.tenant_a)

        user_count = User.objects.filter(role="TEACHER").count()
        course_count = Course.objects.count()

        self.assertEqual(user_count, 1)
        self.assertEqual(course_count, 1)


class ContextvarsNestedContextTestCase(TestCase):
    """
    Simulate ASGI-style nested contexts to verify no cross-bleed.
    This validates the core security property of the contextvars fix.
    """

    def setUp(self):
        self.tenant_a = _make_tenant("Nested A", "nesta", "nesta@test.com")
        self.tenant_b = _make_tenant("Nested B", "nestb", "nestb@test.com")
        self.admin_a = _make_user("admin@nesta.com", self.tenant_a, role="SCHOOL_ADMIN")
        self.admin_b = _make_user("admin@nestb.com", self.tenant_b, role="SCHOOL_ADMIN")

        _make_course(self.tenant_a, self.admin_a, "Nested A Course", "nested-a")
        _make_course(self.tenant_b, self.admin_b, "Nested B Course", "nested-b")

    def tearDown(self):
        clear_current_tenant()

    def test_nested_context_does_not_affect_parent(self):
        """
        A child context (simulating a coroutine) setting a different
        tenant must NOT affect the parent context's view.
        """
        set_current_tenant(self.tenant_a)

        child_ctx = contextvars.copy_context()
        child_result = {}

        def child_work():
            _current_tenant.set(self.tenant_b)
            child_result["tenant"] = get_current_tenant()
            child_result["courses"] = list(
                Course.objects.values_list("title", flat=True)
            )

        child_ctx.run(child_work)

        # Child saw tenant B
        self.assertEqual(child_result["tenant"], self.tenant_b)

        # Parent still sees tenant A
        self.assertEqual(get_current_tenant(), self.tenant_a)

    def test_parallel_context_runs_fully_isolated(self):
        """
        Two independent context runs (simulating concurrent ASGI requests)
        each see only their own tenant's data.
        """
        clear_current_tenant()

        ctx_a = contextvars.copy_context()
        ctx_b = contextvars.copy_context()

        results = {}

        def work_a():
            _current_tenant.set(self.tenant_a)
            results["a_courses"] = list(
                Course.objects.values_list("title", flat=True)
            )

        def work_b():
            _current_tenant.set(self.tenant_b)
            results["b_courses"] = list(
                Course.objects.values_list("title", flat=True)
            )

        ctx_a.run(work_a)
        ctx_b.run(work_b)

        self.assertIn("Nested A Course", results["a_courses"])
        self.assertNotIn("Nested B Course", results["a_courses"])

        self.assertIn("Nested B Course", results["b_courses"])
        self.assertNotIn("Nested A Course", results["b_courses"])

        # Parent context unaffected
        self.assertIsNone(get_current_tenant())


class ContextvarsEdgeCasesTestCase(TestCase):
    """Edge cases for tenant isolation behavior."""

    def setUp(self):
        self.tenant = _make_tenant("Edge School", "edgecase", "edge@test.com")
        self.admin = _make_user("admin@edge.com", self.tenant, role="SCHOOL_ADMIN")

    def tearDown(self):
        clear_current_tenant()

    def test_setting_tenant_to_none_explicitly(self):
        """Explicitly setting tenant to None via set_current_tenant(None) is valid."""
        set_current_tenant(self.tenant)
        set_current_tenant(None)
        self.assertIsNone(get_current_tenant())

    def test_clear_is_idempotent(self):
        """Calling clear_current_tenant multiple times is safe."""
        clear_current_tenant()
        clear_current_tenant()
        clear_current_tenant()
        self.assertIsNone(get_current_tenant())

    def test_set_and_get_roundtrip(self):
        """Basic set/get roundtrip returns the exact same object."""
        set_current_tenant(self.tenant)
        retrieved = get_current_tenant()
        self.assertIs(retrieved, self.tenant)

    def test_context_var_default_is_none(self):
        """The ContextVar default must be None (no implicit tenant)."""
        clear_current_tenant()
        val = _current_tenant.get()
        self.assertIsNone(val)


@override_settings(
    ALLOWED_HOSTS=["a.lms.com", "b.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class CrossTenantAPIWithContextvarsTestCase(TestCase):
    """
    Integration tests: API-level cross-tenant isolation using the
    contextvars-backed middleware.
    """

    def setUp(self):
        self.tenant_a = _make_tenant("API School A", "a", "api-a@test.com")
        self.tenant_b = _make_tenant("API School B", "b", "api-b@test.com")

        self.admin_a = _make_user("admin@api-a.com", self.tenant_a, role="SCHOOL_ADMIN")
        self.admin_b = _make_user("admin@api-b.com", self.tenant_b, role="SCHOOL_ADMIN")

        _make_course(self.tenant_a, self.admin_a, "API Course A", "api-course-a")
        _make_course(self.tenant_b, self.admin_b, "API Course B", "api-course-b")

    def tearDown(self):
        clear_current_tenant()

    def test_admin_a_sees_only_own_courses_via_api(self):
        """Admin A accessing tenant A's host sees only tenant A courses."""
        client = APIClient()
        client.force_authenticate(user=self.admin_a)
        response = client.get("/api/v1/courses/", HTTP_HOST="a.lms.com")
        self.assertEqual(response.status_code, 200)
        titles = [c["title"] for c in response.data.get("results", response.data)]
        self.assertIn("API Course A", titles)
        self.assertNotIn("API Course B", titles)

    def test_admin_b_cannot_access_admin_a_host(self):
        """Admin B is forbidden on tenant A's host."""
        client = APIClient()
        client.force_authenticate(user=self.admin_b)
        response = client.get("/api/v1/courses/", HTTP_HOST="a.lms.com")
        self.assertEqual(response.status_code, 403)

    def test_sequential_api_requests_do_not_bleed_tenant_state(self):
        """
        Two sequential API requests to different tenants get correctly
        isolated results (regression test for the pre-fix threading.local bug).
        """
        client_a = APIClient()
        client_a.force_authenticate(user=self.admin_a)

        client_b = APIClient()
        client_b.force_authenticate(user=self.admin_b)

        # Request 1: Tenant A
        resp_a = client_a.get("/api/v1/courses/", HTTP_HOST="a.lms.com")
        self.assertEqual(resp_a.status_code, 200)

        # Request 2: Tenant B (must NOT see tenant A's data)
        resp_b = client_b.get("/api/v1/courses/", HTTP_HOST="b.lms.com")
        self.assertEqual(resp_b.status_code, 200)

        titles_a = [c["title"] for c in resp_a.data.get("results", resp_a.data)]
        titles_b = [c["title"] for c in resp_b.data.get("results", resp_b.data)]

        self.assertIn("API Course A", titles_a)
        self.assertNotIn("API Course B", titles_a)

        self.assertIn("API Course B", titles_b)
        self.assertNotIn("API Course A", titles_b)
