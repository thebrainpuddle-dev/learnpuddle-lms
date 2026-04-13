# tests/test_tenant_manager.py
"""
Unit tests for TenantManager, TenantQuerySet, and TenantAwareModel.

Covers:
- TenantQuerySet.filter_by_tenant auto-filtering
- TenantManager.get_queryset returns tenant-scoped results
- TenantManager.all_tenants bypasses filtering
- TenantAwareModel.save auto-sets tenant from context
- Behaviour when no tenant is set in context (management-command scenario)
- Switching tenant context between operations
"""

from django.test import TestCase

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.courses.models import Course
from utils.tenant_middleware import (
    get_current_tenant,
    set_current_tenant,
    clear_current_tenant,
)


def _make_tenant(name, subdomain, email):
    return Tenant.objects.create(
        name=name, slug=subdomain, subdomain=subdomain, email=email
    )


def _make_admin(email, tenant):
    return User.objects.create_user(
        email=email,
        password="pass123",
        first_name="Admin",
        last_name="Test",
        tenant=tenant,
        role="SCHOOL_ADMIN",
    )


class TenantQuerySetFilterByTenantTestCase(TestCase):
    """Tests for TenantQuerySet.filter_by_tenant()."""

    def setUp(self):
        self.tenant_a = _make_tenant("School A", "tqa", "tqa@test.com")
        self.tenant_b = _make_tenant("School B", "tqb", "tqb@test.com")
        self.admin_a = _make_admin("admin@tqa.com", self.tenant_a)
        self.admin_b = _make_admin("admin@tqb.com", self.tenant_b)

        self.course_a = Course.objects.create(
            tenant=self.tenant_a,
            title="Course A",
            slug="course-a-tq",
            description="A",
            created_by=self.admin_a,
            is_published=True,
            is_active=True,
        )
        self.course_b = Course.objects.create(
            tenant=self.tenant_b,
            title="Course B",
            slug="course-b-tq",
            description="B",
            created_by=self.admin_b,
            is_published=True,
            is_active=True,
        )

    def tearDown(self):
        clear_current_tenant()

    def test_filter_by_tenant_returns_only_current_tenant_records(self):
        """When tenant A is set, only tenant A courses are returned."""
        set_current_tenant(self.tenant_a)
        courses = list(Course.objects.all())
        course_ids = [c.id for c in courses]
        self.assertIn(self.course_a.id, course_ids)
        self.assertNotIn(self.course_b.id, course_ids)

    def test_filter_by_tenant_excludes_other_tenant(self):
        """When tenant B is set, tenant A's courses are excluded."""
        set_current_tenant(self.tenant_b)
        courses = list(Course.objects.all())
        course_ids = [c.id for c in courses]
        self.assertIn(self.course_b.id, course_ids)
        self.assertNotIn(self.course_a.id, course_ids)

    def test_no_tenant_context_returns_all_records(self):
        """Without tenant context, all records are returned (management scenario)."""
        clear_current_tenant()
        courses = list(Course.objects.all())
        course_ids = [c.id for c in courses]
        self.assertIn(self.course_a.id, course_ids)
        self.assertIn(self.course_b.id, course_ids)

    def test_switching_tenant_context_changes_results(self):
        """Switching tenant context yields different query results."""
        set_current_tenant(self.tenant_a)
        count_a = Course.objects.count()

        set_current_tenant(self.tenant_b)
        count_b = Course.objects.count()

        # Each tenant has exactly 1 course
        self.assertEqual(count_a, 1)
        self.assertEqual(count_b, 1)


class TenantManagerAllTenantsTestCase(TestCase):
    """Tests for TenantManager.all_tenants() bypass method."""

    def setUp(self):
        self.tenant_a = _make_tenant("School X", "tmx", "tmx@test.com")
        self.tenant_b = _make_tenant("School Y", "tmy", "tmy@test.com")
        self.admin_a = _make_admin("admin@tmx.com", self.tenant_a)
        self.admin_b = _make_admin("admin@tmy.com", self.tenant_b)

        Course.objects.create(
            tenant=self.tenant_a,
            title="X Course",
            slug="x-course-tm",
            description="X",
            created_by=self.admin_a,
            is_published=True,
            is_active=True,
        )
        Course.objects.create(
            tenant=self.tenant_b,
            title="Y Course",
            slug="y-course-tm",
            description="Y",
            created_by=self.admin_b,
            is_published=True,
            is_active=True,
        )

    def tearDown(self):
        clear_current_tenant()

    def test_all_tenants_returns_all_records_when_tenant_set(self):
        """all_tenants() must bypass filtering even when a tenant is active."""
        set_current_tenant(self.tenant_a)
        all_courses = Course.objects.all_tenants().all()
        self.assertGreaterEqual(all_courses.count(), 2)

    def test_all_tenants_returns_all_records_when_no_tenant_set(self):
        """all_tenants() works when no tenant context is set."""
        clear_current_tenant()
        all_courses = Course.objects.all_tenants().all()
        self.assertGreaterEqual(all_courses.count(), 2)

    def test_all_tenants_chainable_with_filter(self):
        """all_tenants() can be chained with Django filter() methods."""
        set_current_tenant(self.tenant_a)
        result = Course.objects.all_tenants().filter(title="Y Course")
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().title, "Y Course")


class TenantAwareModelSaveTestCase(TestCase):
    """Tests for TenantAwareModel.save() auto-tenant-setting behavior."""

    def setUp(self):
        self.tenant = _make_tenant("Auto School", "autosave", "auto@test.com")
        self.admin = _make_admin("admin@autosave.com", self.tenant)

    def tearDown(self):
        clear_current_tenant()

    def test_save_auto_sets_tenant_from_context(self):
        """When no tenant is set on the model, save auto-assigns from context."""
        set_current_tenant(self.tenant)

        course = Course(
            title="Auto Tenant Course",
            slug="auto-tenant-course",
            description="Tenant should be auto-set from context",
            created_by=self.admin,
            is_published=True,
            is_active=True,
        )
        course.save()

        course.refresh_from_db()
        self.assertEqual(course.tenant_id, self.tenant.id)

    def test_save_preserves_explicitly_set_tenant(self):
        """When tenant is explicitly set on the model, save does not override it."""
        other_tenant = _make_tenant("Other Auto", "autoother", "autoother@test.com")
        other_admin = _make_admin("admin@autoother.com", other_tenant)
        set_current_tenant(self.tenant)

        course = Course(
            tenant=other_tenant,
            title="Explicit Tenant",
            slug="explicit-tenant-save",
            description="Explicitly set",
            created_by=other_admin,
            is_published=True,
            is_active=True,
        )
        course.save()

        course.refresh_from_db()
        self.assertEqual(course.tenant_id, other_tenant.id)


class TenantManagerConcurrencySimulationTestCase(TestCase):
    """
    Simulates the pattern where two request contexts operate on
    different tenants sequentially (the WSGI pattern).
    """

    def setUp(self):
        self.tenant_a = _make_tenant("Concur A", "conca", "conca@test.com")
        self.tenant_b = _make_tenant("Concur B", "concb", "concb@test.com")
        self.admin_a = _make_admin("admin@conca.com", self.tenant_a)
        self.admin_b = _make_admin("admin@concb.com", self.tenant_b)

        Course.objects.create(
            tenant=self.tenant_a, title="Concur Course A",
            slug="concur-a", description="A", created_by=self.admin_a,
            is_published=True, is_active=True,
        )
        Course.objects.create(
            tenant=self.tenant_b, title="Concur Course B",
            slug="concur-b", description="B", created_by=self.admin_b,
            is_published=True, is_active=True,
        )

    def tearDown(self):
        clear_current_tenant()

    def test_sequential_context_switches_produce_correct_results(self):
        """
        Simulating two back-to-back requests to different tenants:
        each should see only its own data.
        """
        # Request 1: Tenant A
        clear_current_tenant()
        set_current_tenant(self.tenant_a)
        a_courses = list(Course.objects.values_list("title", flat=True))
        clear_current_tenant()

        # Request 2: Tenant B
        set_current_tenant(self.tenant_b)
        b_courses = list(Course.objects.values_list("title", flat=True))
        clear_current_tenant()

        self.assertIn("Concur Course A", a_courses)
        self.assertNotIn("Concur Course B", a_courses)

        self.assertIn("Concur Course B", b_courses)
        self.assertNotIn("Concur Course A", b_courses)

    def test_clear_between_requests_prevents_bleed(self):
        """
        After clearing tenant, subsequent queries should return all
        records (no stale tenant filter).
        """
        set_current_tenant(self.tenant_a)
        a_count = Course.objects.count()

        clear_current_tenant()
        all_count = Course.objects.count()

        self.assertEqual(a_count, 1)
        self.assertGreaterEqual(all_count, 2)
