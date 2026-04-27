# apps/courses/tests_completion_rate.py
"""
Tests for CourseListSerializer.get_completion_rate.

Covers the 4 scenarios requested in the backend-engineer's shared-log entry
from 2026-04-22 (Fix 2 — real completion_rate in CourseListSerializer):

1. Real percentage: 1 of 2 assigned teachers completed → 50.0
2. Zero when no teachers assigned → 0.0
3. 100% when all assigned teachers completed → 100.0
4. Content-level TeacherProgress rows (content != None) must not count
   as course completions.
"""

import uuid

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.courses.models import Course, Module, Content
from apps.progress.models import TeacherProgress
from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant(name="Test School", subdomain="cr-test"):
    uid = uuid.uuid4().hex[:6]
    return Tenant.objects.create(
        name=f"{name}-{uid}",
        slug=f"{subdomain}-{uid}",
        subdomain=f"{subdomain}{uid}",
        email=f"admin@{subdomain}{uid}.com",
        is_active=True,
    )


def _make_user(email, tenant, role="SCHOOL_ADMIN"):
    return User.objects.create_user(
        email=email,
        password="TestPass!123",
        first_name="Test",
        last_name="User",
        tenant=tenant,
        role=role,
        is_active=True,
    )


def _make_course(tenant, admin):
    uid = uuid.uuid4().hex[:6]
    return Course.objects.create(
        tenant=tenant,
        title=f"Test Course {uid}",
        slug=f"test-course-{uid}",
        description="Test",
        created_by=admin,
        is_published=True,
        is_active=True,
    )


def _make_module(course):
    return Module.objects.create(
        course=course,
        title="Test Module",
        order=1,
        is_active=True,
    )


def _make_content(module):
    return Content.objects.create(
        module=module,
        title="Test Content",
        content_type="TEXT",
        order=1,
        text_content="<p>Hello</p>",
        is_active=True,
    )


def _complete_course(tenant, teacher, course):
    """Create a course-level (content=None, status=COMPLETED) TeacherProgress row."""
    return TeacherProgress.all_objects.create(
        tenant=tenant,
        teacher=teacher,
        course=course,
        content=None,  # course-level row — the key flag for completion_rate
        status="COMPLETED",
        progress_percentage=100,
    )


def _inprogress_content(tenant, teacher, course, content):
    """Create a content-level (content != None) TeacherProgress row (NOT a completion)."""
    return TeacherProgress.all_objects.create(
        tenant=tenant,
        teacher=teacher,
        course=course,
        content=content,
        status="IN_PROGRESS",
        progress_percentage=50,
    )


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class CompletionRateTestCase(TestCase):
    """
    Verify that GET /api/v1/courses/ returns the correct completion_rate for
    each course, using the _completed_teacher_count annotation added by
    the course_list view.
    """

    def setUp(self):
        self.tenant = _make_tenant()
        self.admin = _make_user(f"admin@{self.tenant.subdomain}.com", self.tenant, role="SCHOOL_ADMIN")
        self.host = f"{self.tenant.subdomain}.lms.com"

        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def _get_course_data(self, course_id):
        """Hit GET /api/v1/courses/ and return the entry for the given course."""
        response = self.client.get("/api/v1/courses/", HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200, response.data)
        results = response.data.get("results", response.data)
        for item in results:
            if str(item["id"]) == str(course_id):
                return item
        self.fail(f"Course {course_id} not found in response: {results}")

    # -----------------------------------------------------------------------
    # Test 1: 1 of 2 teachers completed → 50.0
    # -----------------------------------------------------------------------

    def test_completion_rate_returns_real_value(self):
        """
        When 1 of 2 assigned teachers has a course-level COMPLETED progress row,
        completion_rate must equal 50.0.
        """
        teacher1 = _make_user(f"t1@{self.tenant.subdomain}.com", self.tenant, role="TEACHER")
        teacher2 = _make_user(f"t2@{self.tenant.subdomain}.com", self.tenant, role="TEACHER")

        course = _make_course(self.tenant, self.admin)
        course.assigned_teachers.add(teacher1, teacher2)

        # Only teacher1 has completed the course (course-level row)
        _complete_course(self.tenant, teacher1, course)

        data = self._get_course_data(course.id)
        self.assertEqual(
            data["completion_rate"],
            50.0,
            f"Expected 50.0, got {data['completion_rate']}",
        )

    # -----------------------------------------------------------------------
    # Test 2: No assigned teachers → 0.0
    # -----------------------------------------------------------------------

    def test_completion_rate_zero_when_no_teachers(self):
        """
        A course with no assigned teachers and assigned_to_all=False must
        return completion_rate == 0.0.
        """
        course = _make_course(self.tenant, self.admin)
        # No teachers assigned at all

        data = self._get_course_data(course.id)
        self.assertEqual(
            data["completion_rate"],
            0.0,
            f"Expected 0.0 for course with no teachers, got {data['completion_rate']}",
        )

    # -----------------------------------------------------------------------
    # Test 3: All assigned teachers completed → 100.0
    # -----------------------------------------------------------------------

    def test_completion_rate_100_when_all_complete(self):
        """
        When all assigned teachers have course-level COMPLETED progress rows,
        completion_rate must equal 100.0.
        """
        teacher1 = _make_user(f"all1@{self.tenant.subdomain}.com", self.tenant, role="TEACHER")
        teacher2 = _make_user(f"all2@{self.tenant.subdomain}.com", self.tenant, role="TEACHER")

        course = _make_course(self.tenant, self.admin)
        course.assigned_teachers.add(teacher1, teacher2)

        _complete_course(self.tenant, teacher1, course)
        _complete_course(self.tenant, teacher2, course)

        data = self._get_course_data(course.id)
        self.assertEqual(
            data["completion_rate"],
            100.0,
            f"Expected 100.0 when all teachers completed, got {data['completion_rate']}",
        )

    # -----------------------------------------------------------------------
    # Test 4: Content-level rows must NOT count as completions
    # -----------------------------------------------------------------------

    def test_completion_rate_ignores_content_level_rows(self):
        """
        TeacherProgress rows with content != None (in-progress content items)
        must NOT be counted as course completions.

        Even if a teacher has content-level IN_PROGRESS rows, the course-level
        completion_rate must remain 0.0 until they have a content=None COMPLETED row.
        """
        teacher = _make_user(f"clevel@{self.tenant.subdomain}.com", self.tenant, role="TEACHER")

        course = _make_course(self.tenant, self.admin)
        course.assigned_teachers.add(teacher)

        module = _make_module(course)
        content = _make_content(module)

        # Content-level progress row: should NOT count as a course completion
        _inprogress_content(self.tenant, teacher, course, content)

        data = self._get_course_data(course.id)
        self.assertEqual(
            data["completion_rate"],
            0.0,
            "Content-level TeacherProgress rows must not count as course completions "
            f"(got {data['completion_rate']})",
        )

    # -----------------------------------------------------------------------
    # Bonus: assigned_to_all course with no completions → 0.0
    # -----------------------------------------------------------------------

    def test_completion_rate_zero_for_assigned_to_all_with_no_completions(self):
        """
        A course with assigned_to_all=True and no completed teachers must
        return completion_rate == 0.0 (not crash or error).
        """
        course = _make_course(self.tenant, self.admin)
        course.assigned_to_all = True
        course.save()

        # Create some active teachers in the tenant (will be counted by
        # get_assigned_teacher_count for assigned_to_all courses)
        _make_user(f"at1@{self.tenant.subdomain}.com", self.tenant, role="TEACHER")
        _make_user(f"at2@{self.tenant.subdomain}.com", self.tenant, role="TEACHER")

        # No completions at all
        data = self._get_course_data(course.id)
        self.assertEqual(
            data["completion_rate"],
            0.0,
            f"assigned_to_all course with no completions should be 0.0, got {data['completion_rate']}",
        )

    # -----------------------------------------------------------------------
    # Bonus: partial completion rounding
    # -----------------------------------------------------------------------

    def test_completion_rate_rounds_to_one_decimal(self):
        """
        completion_rate is rounded to 1 decimal place.
        With 1 of 3 teachers completed: 33.333... → 33.3
        """
        t1 = _make_user(f"r1@{self.tenant.subdomain}.com", self.tenant, role="TEACHER")
        t2 = _make_user(f"r2@{self.tenant.subdomain}.com", self.tenant, role="TEACHER")
        t3 = _make_user(f"r3@{self.tenant.subdomain}.com", self.tenant, role="TEACHER")

        course = _make_course(self.tenant, self.admin)
        course.assigned_teachers.add(t1, t2, t3)

        _complete_course(self.tenant, t1, course)

        data = self._get_course_data(course.id)
        # 1/3 = 33.333... rounded to 1dp = 33.3
        self.assertEqual(
            data["completion_rate"],
            33.3,
            f"1/3 teachers completed should be 33.3, got {data['completion_rate']}",
        )
