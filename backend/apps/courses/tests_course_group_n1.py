# apps/courses/tests_course_group_n1.py
"""
TDD tests for the N+1 query fix in CourseListSerializer.get_assigned_teacher_count
when courses use group-based assignments.

Root cause: the view used `prefetch_related('assigned_groups')` which fetched the
TeacherGroup objects but NOT their members. For each course with groups, the
serializer fell through to:
    User.objects.filter(teacher_groups__in=...).distinct().count()
— one extra query PER COURSE. With N group-assigned courses on a page that's N
extra queries (N+1 pattern).

Fix: use a Prefetch object to also prefetch `TeacherGroup.members` filtered to
active TEACHER-role users. The serializer then unions individual_ids with
prefetched group member IDs in Python — zero extra per-course DB queries.

Test suite (RED before fix, GREEN after fix):
  1. assigned_teacher_count is correct for a course with a single group
  2. teachers in both a group and individually assigned are counted only once
  3. inactive teachers in groups are NOT counted
  4. non-TEACHER role users in groups are NOT counted
  5. GET /api/v1/courses/ query count does NOT grow with more group-assigned courses (N+1 guard)
"""

import uuid

import pytest
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.courses.models import Course, Module, TeacherGroup
from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers (shared with tests_completion_rate pattern)
# ---------------------------------------------------------------------------

def _make_tenant(name="Group School", subdomain="grp-test"):
    uid = uuid.uuid4().hex[:6]
    return Tenant.objects.create(
        name=f"{name}-{uid}",
        slug=f"{subdomain}-{uid}",
        subdomain=f"{subdomain}{uid}",
        email=f"admin@{subdomain}{uid}.com",
        is_active=True,
    )


def _make_user(email, tenant, role="TEACHER", is_active=True):
    return User.objects.create_user(
        email=email,
        password="TestPass!123",
        first_name="Test",
        last_name="User",
        tenant=tenant,
        role=role,
        is_active=is_active,
    )


def _make_course(tenant, admin):
    uid = uuid.uuid4().hex[:6]
    return Course.objects.create(
        tenant=tenant,
        title=f"Group Course {uid}",
        slug=f"group-course-{uid}",
        description="Test group assignment",
        created_by=admin,
        is_published=True,
        is_active=True,
    )


def _make_group(tenant, name=None):
    name = name or f"Group-{uuid.uuid4().hex[:6]}"
    return TeacherGroup.objects.create(
        tenant=tenant,
        name=name,
        group_type="CUSTOM",
    )


# ---------------------------------------------------------------------------
# Correctness tests (verify assigned_teacher_count is right for groups)
# ---------------------------------------------------------------------------

@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class AssignedTeacherCountGroupsTestCase(TestCase):
    """
    Verify CourseListSerializer returns correct assigned_teacher_count for
    courses that use TeacherGroup-based assignment.
    """

    def setUp(self):
        self.tenant = _make_tenant()
        self.admin = _make_user(
            f"admin@{self.tenant.subdomain}.com", self.tenant, role="SCHOOL_ADMIN"
        )
        self.host = f"{self.tenant.subdomain}.lms.com"
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def _get_course_data(self, course_id):
        response = self.client.get("/api/v1/courses/", HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200, response.data)
        results = response.data.get("results", response.data)
        for item in results:
            if str(item["id"]) == str(course_id):
                return item
        self.fail(f"Course {course_id} not found in response: {results}")

    # ------------------------------------------------------------------
    # Test 1: basic group count
    # ------------------------------------------------------------------

    def test_assigned_teacher_count_counts_group_members(self):
        """
        A course assigned to a group with 2 active teachers must return
        assigned_teacher_count == 2.
        """
        group = _make_group(self.tenant, "Math Teachers")
        t1 = _make_user(f"t1@{self.tenant.subdomain}.com", self.tenant)
        t2 = _make_user(f"t2@{self.tenant.subdomain}.com", self.tenant)
        # Add teachers to the group via the reverse M2M (User.teacher_groups)
        t1.teacher_groups.add(group)
        t2.teacher_groups.add(group)

        course = _make_course(self.tenant, self.admin)
        course.assigned_groups.add(group)

        data = self._get_course_data(course.id)
        self.assertEqual(
            data["assigned_teacher_count"],
            2,
            f"Expected 2 teachers from group, got {data['assigned_teacher_count']}",
        )

    # ------------------------------------------------------------------
    # Test 2: deduplication — same teacher in group AND individually assigned
    # ------------------------------------------------------------------

    def test_assigned_teacher_count_deduplicates_group_and_individual(self):
        """
        A teacher who is both in an assigned group AND individually assigned
        must be counted only ONCE.
        """
        group = _make_group(self.tenant, "Science Group")
        shared_teacher = _make_user(
            f"shared@{self.tenant.subdomain}.com", self.tenant
        )
        shared_teacher.teacher_groups.add(group)

        course = _make_course(self.tenant, self.admin)
        course.assigned_groups.add(group)
        course.assigned_teachers.add(shared_teacher)  # also individually assigned

        data = self._get_course_data(course.id)
        self.assertEqual(
            data["assigned_teacher_count"],
            1,
            "Teacher in group AND individually assigned must be counted once, "
            f"got {data['assigned_teacher_count']}",
        )

    # ------------------------------------------------------------------
    # Test 3: inactive teachers in groups are NOT counted
    # ------------------------------------------------------------------

    def test_assigned_teacher_count_excludes_inactive_group_members(self):
        """
        Inactive teachers in an assigned group must NOT be included in
        assigned_teacher_count.
        """
        group = _make_group(self.tenant, "Inactive Group")
        active_teacher = _make_user(
            f"active@{self.tenant.subdomain}.com", self.tenant, is_active=True
        )
        inactive_teacher = _make_user(
            f"inactive@{self.tenant.subdomain}.com", self.tenant, is_active=False
        )
        active_teacher.teacher_groups.add(group)
        inactive_teacher.teacher_groups.add(group)

        course = _make_course(self.tenant, self.admin)
        course.assigned_groups.add(group)

        data = self._get_course_data(course.id)
        self.assertEqual(
            data["assigned_teacher_count"],
            1,
            f"Inactive group members must not be counted, got {data['assigned_teacher_count']}",
        )

    # ------------------------------------------------------------------
    # Test 4: non-TEACHER role users in groups are NOT counted
    # ------------------------------------------------------------------

    def test_assigned_teacher_count_excludes_non_teacher_role_group_members(self):
        """
        Users with roles other than TEACHER who are in an assigned group
        must NOT be included in assigned_teacher_count.
        """
        group = _make_group(self.tenant, "Mixed Role Group")
        teacher = _make_user(
            f"teacher@{self.tenant.subdomain}.com", self.tenant, role="TEACHER"
        )
        hod = _make_user(
            f"hod@{self.tenant.subdomain}.com", self.tenant, role="HOD"
        )
        teacher.teacher_groups.add(group)
        hod.teacher_groups.add(group)

        course = _make_course(self.tenant, self.admin)
        course.assigned_groups.add(group)

        data = self._get_course_data(course.id)
        self.assertEqual(
            data["assigned_teacher_count"],
            1,
            f"Non-TEACHER role users must not be counted, got {data['assigned_teacher_count']}",
        )

    # ------------------------------------------------------------------
    # Test 5: individual-only (no groups) fast path
    # ------------------------------------------------------------------

    def test_assigned_teacher_count_individual_only_no_groups(self):
        """
        A course with ONLY individually-assigned teachers and NO groups must
        return the exact count of those teachers via the fast-path at
        serializers.py:L185 (`if not groups: return len(individual_ids)`).

        This pins the fast-path so future changes that add group logic cannot
        silently alter the individual-only count.
        """
        t1 = _make_user(f"ind1@{self.tenant.subdomain}.com", self.tenant)
        t2 = _make_user(f"ind2@{self.tenant.subdomain}.com", self.tenant)
        t3 = _make_user(f"ind3@{self.tenant.subdomain}.com", self.tenant)

        course = _make_course(self.tenant, self.admin)
        course.assigned_teachers.add(t1, t2, t3)
        # deliberately NO assigned_groups

        data = self._get_course_data(course.id)
        self.assertEqual(
            data["assigned_teacher_count"],
            3,
            f"Individual-only course must count exactly 3 teachers, got {data['assigned_teacher_count']}",
        )

    # ------------------------------------------------------------------
    # Test 6: multiple groups, combined unique count
    # ------------------------------------------------------------------

    def test_assigned_teacher_count_combines_multiple_groups(self):
        """
        A course assigned to 2 groups with a total of 3 unique active teachers
        must return assigned_teacher_count == 3 (no double-counting across groups).
        """
        group_a = _make_group(self.tenant, "Group A")
        group_b = _make_group(self.tenant, "Group B")
        t1 = _make_user(f"m1@{self.tenant.subdomain}.com", self.tenant)
        t2 = _make_user(f"m2@{self.tenant.subdomain}.com", self.tenant)
        t3 = _make_user(f"m3@{self.tenant.subdomain}.com", self.tenant)
        # t1 in both groups (should not be double-counted)
        t1.teacher_groups.add(group_a, group_b)
        t2.teacher_groups.add(group_a)
        t3.teacher_groups.add(group_b)

        course = _make_course(self.tenant, self.admin)
        course.assigned_groups.add(group_a, group_b)

        data = self._get_course_data(course.id)
        self.assertEqual(
            data["assigned_teacher_count"],
            3,
            f"3 unique teachers across 2 groups, got {data['assigned_teacher_count']}",
        )


# ---------------------------------------------------------------------------
# N+1 query guard — this test FAILS before the prefetch fix
# ---------------------------------------------------------------------------

@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class CourseListGroupN1TestCase(TestCase):
    """
    Verify that GET /api/v1/courses/ does not issue a per-course DB query
    for courses with group assignments (N+1 guard).

    This test documents the performance contract: going from 1 group-assigned
    course to 3 must NOT add any extra queries.
    """

    def setUp(self):
        self.tenant = _make_tenant("N1 School", "n1-test")
        self.admin = _make_user(
            f"admin@{self.tenant.subdomain}.com", self.tenant, role="SCHOOL_ADMIN"
        )
        self.host = f"{self.tenant.subdomain}.lms.com"
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_query_count_does_not_grow_with_group_assigned_courses(self):
        """
        When courses are assigned via groups, the view must use a Prefetch that
        fetches group members in bulk so the serializer never issues a per-course
        COUNT query.

        Creates 1 group-assigned course, measures queries, then creates 2 more
        (3 total). The query count must be identical — no N+1 growth.
        """
        group = _make_group(self.tenant, "N1 Test Group")
        teacher = _make_user(
            f"n1t@{self.tenant.subdomain}.com", self.tenant
        )
        teacher.teacher_groups.add(group)

        # --- Baseline: 1 group-assigned course ---
        c1 = _make_course(self.tenant, self.admin)
        c1.assigned_groups.add(group)

        with CaptureQueriesContext(connection) as ctx_one:
            resp = self.client.get("/api/v1/courses/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        queries_with_one = len(ctx_one.captured_queries)

        # --- 3 group-assigned courses ---
        c2 = _make_course(self.tenant, self.admin)
        c2.assigned_groups.add(group)
        c3 = _make_course(self.tenant, self.admin)
        c3.assigned_groups.add(group)

        with CaptureQueriesContext(connection) as ctx_three:
            resp = self.client.get("/api/v1/courses/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        queries_with_three = len(ctx_three.captured_queries)

        # Strict assertEqual is intentional: the query count must be IDENTICAL,
        # not merely "not too much bigger".  If this assertion fires it means
        # *something* in the read path now scales with N — not necessarily
        # group-related code (future contributors: add a new per-result query?
        # look here first).
        self.assertEqual(
            queries_with_three,
            queries_with_one,
            f"N+1 detected: {queries_with_one} queries for 1 group course but "
            f"{queries_with_three} queries for 3 group courses. "
            f"Expected the same count — the view must prefetch group members.",
        )
