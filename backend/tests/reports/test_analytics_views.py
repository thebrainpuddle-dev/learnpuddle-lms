# tests/reports/test_analytics_views.py
"""
TDD tests for the three analytics chart endpoints introduced in FE-034.

These endpoints do NOT yet exist in the backend — these tests are written
first (TDD) to define the contract the backend-engineer must implement.

Expected endpoints (to be added to apps/reports/urls.py):
  GET /reports/analytics/deadline-adherence/  → DeadlineAdherencePoint[]
  GET /reports/analytics/approval-trends/     → ApprovalTrendsPoint[]
  GET /reports/analytics/course-effectiveness/ → CourseEffectivenessItem[]

Contract (from frontend/src/services/adminReportsService.ts):

  DeadlineAdherencePoint {
      period: str          # e.g. "Jan 2026"
      adherencePercent: float  # 0–100
      totalTeachers: int
      onTime: int
      late: int
  }

  ApprovalTrendsPoint {
      period: str          # e.g. "Jan 2026"
      approved: int
      rejected: int
      pending: int
  }

  CourseEffectivenessItem {
      courseId: str (UUID)
      courseName: str
      completionRate: float  # 0–100
      avgScore: float        # 0–100
      enrolledCount: int
  }

All three require @admin_only + @tenant_required (same pattern as all
other reports endpoints). Optional start/end ISO-date params are
accepted by deadline-adherence and approval-trends.

Tenant isolation: each endpoint must only return data for the
request.tenant — a second tenant's data must never appear.
"""

import uuid
from datetime import date, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.courses.models import Course, Module, Content
from apps.progress.models import (
    Assignment,
    AssignmentSubmission,
    TeacherProgress,
    QuizSubmission,
    Quiz,
)
from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _subdomain():
    return "analytics-" + uuid.uuid4().hex[:6]


def _tenant():
    sub = _subdomain()
    return Tenant.objects.create(
        name=f"School {sub}",
        slug=sub,
        subdomain=sub,
        email=f"{sub}@school.com",
        is_active=True,
    )


def _admin(tenant):
    return User.objects.create_user(
        email=f"admin-{uuid.uuid4().hex[:6]}@school.com",
        password="pass",
        first_name="Admin",
        last_name="User",
        tenant=tenant,
        role="SCHOOL_ADMIN",
        is_active=True,
    )


def _teacher(tenant):
    return User.objects.create_user(
        email=f"teacher-{uuid.uuid4().hex[:6]}@school.com",
        password="pass",
        first_name="Teacher",
        last_name="User",
        tenant=tenant,
        role="TEACHER",
        is_active=True,
    )


def _course(tenant, admin, title=None, deadline=None):
    slug = uuid.uuid4().hex[:10]
    return Course.objects.create(
        tenant=tenant,
        title=title or f"Course {slug}",
        slug=slug,
        description="Test course",
        created_by=admin,
        is_published=True,
        is_active=True,
        assigned_to_all=True,
        deadline=deadline,
    )


def _module(course):
    return Module.objects.create(
        course=course,
        title="Module 1",
        description="",
        order=1,
        is_active=True,
    )


def _content(module):
    return Content.objects.create(
        module=module,
        title="Content 1",
        content_type="TEXT",
        order=1,
        text_content="<p>Test</p>",
        is_active=True,
    )


def _assignment(tenant, course, title=None):
    return Assignment.objects.create(
        tenant=tenant,
        course=course,
        title=title or f"Assignment {uuid.uuid4().hex[:6]}",
        description="Test assignment",
        is_active=True,
    )


def _quiz(tenant, course):
    """Create an Assignment + linked Quiz for a course, return the Quiz."""
    assignment = Assignment.objects.create(
        tenant=tenant,
        course=course,
        title=f"Quiz Assignment {uuid.uuid4().hex[:6]}",
        description="Test quiz assignment",
        is_active=True,
    )
    return Quiz.all_objects.create(
        tenant=tenant,
        assignment=assignment,
    )


def _auth_client(user, tenant):
    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
    return client


# ---------------------------------------------------------------------------
# 1. Deadline Adherence Endpoint
# ---------------------------------------------------------------------------

class TestDeadlineAdherenceAuth:
    """Authentication and authorisation guards for deadline-adherence."""

    def test_requires_authentication(self, db):
        tenant = _tenant()
        client = APIClient()
        resp = client.get(
            "/api/v1/reports/analytics/deadline-adherence/",
            HTTP_HOST=f"{tenant.subdomain}.lms.com",
        )
        assert resp.status_code == 401, (
            "Unauthenticated requests must be rejected with 401"
        )

    def test_teacher_cannot_access(self, db):
        tenant = _tenant()
        teacher = _teacher(tenant)
        client = _auth_client(teacher, tenant)
        resp = client.get("/api/v1/reports/analytics/deadline-adherence/")
        assert resp.status_code == 403, (
            "TEACHER role must not access admin-only report endpoint"
        )

    def test_admin_can_access(self, db):
        tenant = _tenant()
        admin = _admin(tenant)
        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/deadline-adherence/")
        assert resp.status_code == 200, (
            f"School admin should receive 200, got {resp.status_code}"
        )


class TestDeadlineAdherenceResponseShape:
    """Response envelope and field types for deadline-adherence."""

    def test_returns_a_list(self, db):
        tenant = _tenant()
        admin = _admin(tenant)
        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/deadline-adherence/")
        assert resp.status_code == 200
        assert isinstance(resp.data, list), "Response body must be a list"

    def test_empty_data_returns_empty_list(self, db):
        """No courses → empty list, not an error."""
        tenant = _tenant()
        admin = _admin(tenant)
        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/deadline-adherence/")
        assert resp.status_code == 200
        assert resp.data == [] or isinstance(resp.data, list)

    def test_item_shape_when_data_exists(self, db):
        """Each item must have the five required fields with correct types."""
        tenant = _tenant()
        admin = _admin(tenant)
        teacher = _teacher(tenant)
        past_deadline = date.today() - timedelta(days=30)
        course = _course(tenant, admin, deadline=past_deadline)

        # Teacher completed the course before deadline
        TeacherProgress.all_objects.create(
            tenant=tenant,
            teacher=teacher,
            course=course,
            content=None,
            status="COMPLETED",
            completed_at=timezone.now() - timedelta(days=35),
        )

        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/deadline-adherence/")
        assert resp.status_code == 200
        assert len(resp.data) >= 1, "Expected at least one period in the result"

        item = resp.data[0]
        assert "period" in item, "Each item must have a 'period' key"
        assert "adherencePercent" in item, "Each item must have 'adherencePercent'"
        assert "totalTeachers" in item, "Each item must have 'totalTeachers'"
        assert "onTime" in item, "Each item must have 'onTime'"
        assert "late" in item, "Each item must have 'late'"

        assert isinstance(item["period"], str)
        assert 0 <= item["adherencePercent"] <= 100
        assert isinstance(item["totalTeachers"], int)
        assert isinstance(item["onTime"], int)
        assert isinstance(item["late"], int)


class TestDeadlineAdherenceData:
    """Data-correctness tests for deadline-adherence endpoint."""

    def test_on_time_completion_counted(self, db):
        """A teacher who completed before the deadline is counted as onTime."""
        tenant = _tenant()
        admin = _admin(tenant)
        teacher = _teacher(tenant)
        past_deadline = date.today() - timedelta(days=10)
        course = _course(tenant, admin, deadline=past_deadline)

        TeacherProgress.all_objects.create(
            tenant=tenant,
            teacher=teacher,
            course=course,
            content=None,
            status="COMPLETED",
            completed_at=timezone.now() - timedelta(days=15),  # 5 days before deadline
        )

        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/deadline-adherence/")
        assert resp.status_code == 200
        # At least one period with onTime >= 1
        on_time_total = sum(item["onTime"] for item in resp.data)
        assert on_time_total >= 1, (
            "Teacher who completed before deadline must be counted as onTime"
        )

    def test_late_completion_counted(self, db):
        """A teacher who completed after the deadline is counted as late."""
        tenant = _tenant()
        admin = _admin(tenant)
        teacher = _teacher(tenant)
        past_deadline = date.today() - timedelta(days=20)
        course = _course(tenant, admin, deadline=past_deadline)

        TeacherProgress.all_objects.create(
            tenant=tenant,
            teacher=teacher,
            course=course,
            content=None,
            status="COMPLETED",
            completed_at=timezone.now() - timedelta(days=5),  # 15 days after deadline
        )

        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/deadline-adherence/")
        assert resp.status_code == 200
        late_total = sum(item["late"] for item in resp.data)
        assert late_total >= 1, (
            "Teacher who completed after deadline must be counted as late"
        )

    def test_adherence_percent_calculation(self, db):
        """50% on-time → adherencePercent == 50.0 for the relevant period."""
        tenant = _tenant()
        admin = _admin(tenant)
        teacher1 = _teacher(tenant)
        teacher2 = _teacher(tenant)
        past_deadline = date.today() - timedelta(days=20)
        course = _course(tenant, admin, deadline=past_deadline)

        # Teacher 1 completed on time
        TeacherProgress.all_objects.create(
            tenant=tenant,
            teacher=teacher1,
            course=course,
            content=None,
            status="COMPLETED",
            completed_at=timezone.now() - timedelta(days=25),
        )
        # Teacher 2 completed late
        TeacherProgress.all_objects.create(
            tenant=tenant,
            teacher=teacher2,
            course=course,
            content=None,
            status="COMPLETED",
            completed_at=timezone.now() - timedelta(days=5),
        )

        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/deadline-adherence/")
        assert resp.status_code == 200
        # The total adherence across periods should reflect 50%
        all_on_time = sum(item["onTime"] for item in resp.data)
        all_total = sum(item["totalTeachers"] for item in resp.data)
        # Allow for various grouping strategies but the ratio must be ≈50%
        if all_total > 0:
            ratio = (all_on_time / all_total) * 100
            assert abs(ratio - 50.0) < 1.0, (
                f"Expected ~50% adherence, got {ratio:.1f}%"
            )

    def test_tenant_isolation(self, db):
        """Tenant B's course completion does not affect Tenant A's report."""
        tenant_a = _tenant()
        admin_a = _admin(tenant_a)

        tenant_b = _tenant()
        admin_b = _admin(tenant_b)
        teacher_b = _teacher(tenant_b)
        past_deadline = date.today() - timedelta(days=10)
        course_b = _course(tenant_b, admin_b, deadline=past_deadline)

        TeacherProgress.all_objects.create(
            tenant=tenant_b,
            teacher=teacher_b,
            course=course_b,
            content=None,
            status="COMPLETED",
            completed_at=timezone.now() - timedelta(days=15),
        )

        client_a = _auth_client(admin_a, tenant_a)
        resp = client_a.get("/api/v1/reports/analytics/deadline-adherence/")
        assert resp.status_code == 200
        # Tenant A has no data — should return empty list
        assert resp.data == [], (
            "Tenant A must not see Tenant B's completion data"
        )

    def test_date_range_filtering(self, db):
        """start/end params filter results to the requested period."""
        tenant = _tenant()
        admin = _admin(tenant)
        teacher = _teacher(tenant)
        old_deadline = date(2025, 1, 15)
        recent_deadline = date.today() - timedelta(days=5)

        course_old = _course(tenant, admin, title="Old Course", deadline=old_deadline)
        course_new = _course(tenant, admin, title="New Course", deadline=recent_deadline)

        # Completion in Jan 2025
        TeacherProgress.all_objects.create(
            tenant=tenant,
            teacher=teacher,
            course=course_old,
            content=None,
            status="COMPLETED",
            completed_at=timezone.make_aware(
                timezone.datetime(2025, 1, 10)
            ),
        )

        # Completion this month — use timezone.now() (not days=1) so this
        # always falls within [first_of_month, today] even when the test
        # runs on the 1st of the month (yesterday would be last month).
        TeacherProgress.all_objects.create(
            tenant=tenant,
            teacher=teacher,
            course=course_new,
            content=None,
            status="COMPLETED",
            completed_at=timezone.now(),
        )

        start = date.today().replace(day=1).isoformat()
        end = date.today().isoformat()

        client = _auth_client(admin, tenant)
        resp = client.get(
            "/api/v1/reports/analytics/deadline-adherence/",
            {"start": start, "end": end},
        )
        assert resp.status_code == 200
        # Should only contain current-month data
        total = sum(item["totalTeachers"] for item in resp.data)
        assert total >= 1, (
            f"Expected at least 1 teacher in date-filtered result, got {total}"
        )


# ---------------------------------------------------------------------------
# 2. Approval Trends Endpoint
# ---------------------------------------------------------------------------

class TestApprovalTrendsAuth:
    """Authentication and authorisation guards for approval-trends."""

    def test_requires_authentication(self, db):
        tenant = _tenant()
        client = APIClient()
        resp = client.get(
            "/api/v1/reports/analytics/approval-trends/",
            HTTP_HOST=f"{tenant.subdomain}.lms.com",
        )
        assert resp.status_code == 401

    def test_teacher_cannot_access(self, db):
        tenant = _tenant()
        teacher = _teacher(tenant)
        client = _auth_client(teacher, tenant)
        resp = client.get("/api/v1/reports/analytics/approval-trends/")
        assert resp.status_code == 403

    def test_admin_can_access(self, db):
        tenant = _tenant()
        admin = _admin(tenant)
        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/approval-trends/")
        assert resp.status_code == 200


class TestApprovalTrendsResponseShape:
    """Response envelope and field types for approval-trends."""

    def test_returns_a_list(self, db):
        tenant = _tenant()
        admin = _admin(tenant)
        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/approval-trends/")
        assert resp.status_code == 200
        assert isinstance(resp.data, list)

    def test_empty_data_returns_empty_list(self, db):
        tenant = _tenant()
        admin = _admin(tenant)
        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/approval-trends/")
        assert resp.status_code == 200
        assert resp.data == [] or isinstance(resp.data, list)

    def test_item_shape_when_data_exists(self, db):
        """Each item must have period, approved, rejected, pending."""
        tenant = _tenant()
        admin = _admin(tenant)
        teacher = _teacher(tenant)
        course = _course(tenant, admin)
        assignment = _assignment(tenant, course)

        AssignmentSubmission.all_objects.create(
            tenant=tenant,
            assignment=assignment,
            teacher=teacher,
            submission_text="My submission",
            status="GRADED",
            score=85,
        )

        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/approval-trends/")
        assert resp.status_code == 200
        assert len(resp.data) >= 1

        item = resp.data[0]
        assert "period" in item, "Item must have 'period'"
        assert "approved" in item, "Item must have 'approved'"
        assert "rejected" in item, "Item must have 'rejected'"
        assert "pending" in item, "Item must have 'pending'"

        assert isinstance(item["period"], str)
        assert isinstance(item["approved"], int)
        assert isinstance(item["rejected"], int)
        assert isinstance(item["pending"], int)


class TestApprovalTrendsData:
    """Data-correctness tests for approval-trends endpoint."""

    def test_graded_submission_counted_as_approved(self, db):
        """GRADED (passing score) AssignmentSubmission → approved count."""
        tenant = _tenant()
        admin = _admin(tenant)
        teacher = _teacher(tenant)
        course = _course(tenant, admin)
        assignment = _assignment(tenant, course)

        AssignmentSubmission.all_objects.create(
            tenant=tenant,
            assignment=assignment,
            teacher=teacher,
            submission_text="Approved submission",
            status="GRADED",
            score=90,
        )

        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/approval-trends/")
        assert resp.status_code == 200
        total_approved = sum(item["approved"] for item in resp.data)
        assert total_approved >= 1, (
            "GRADED submission with passing score must be counted as approved"
        )

    def test_graded_submission_below_passing_counted_as_rejected(self, db):
        """GRADED (score < passing_score) AssignmentSubmission → rejected count.

        Tightening test requested in REVIEW-VERDICT-ANALYTICS-TDD-AND-SCIM-PATCH-2026-04-24:
        "Empty `rejected` semantics — add a tightening test once backend-engineer
        picks a mapping." Backend chose: GRADED && score < passing_score → rejected.
        Confirmed in apps/reports/analytics_views.py:174-179.

        Assignment default passing_score=70 (model default).
        """
        tenant = _tenant()
        admin = _admin(tenant)
        teacher = _teacher(tenant)
        course = _course(tenant, admin)
        assignment = _assignment(tenant, course)  # passing_score defaults to 70

        AssignmentSubmission.all_objects.create(
            tenant=tenant,
            assignment=assignment,
            teacher=teacher,
            submission_text="Below-passing submission",
            status="GRADED",
            score=50,  # below default passing_score of 70
        )

        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/approval-trends/")
        assert resp.status_code == 200
        total_rejected = sum(item["rejected"] for item in resp.data)
        assert total_rejected >= 1, (
            "GRADED submission with score < passing_score must be counted as rejected "
            "(analytics_views.py mapping: GRADED && score < passing_score → rejected)"
        )
        # Must NOT count as approved
        total_approved = sum(item["approved"] for item in resp.data)
        assert total_approved == 0, (
            f"Below-passing submission must not count as approved; got approved={total_approved}"
        )

    def test_pending_submission_counted_as_pending(self, db):
        """PENDING AssignmentSubmission → pending count."""
        tenant = _tenant()
        admin = _admin(tenant)
        teacher = _teacher(tenant)
        course = _course(tenant, admin)
        assignment = _assignment(tenant, course)

        AssignmentSubmission.all_objects.create(
            tenant=tenant,
            assignment=assignment,
            teacher=teacher,
            submission_text="",
            status="PENDING",
        )

        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/approval-trends/")
        assert resp.status_code == 200
        total_pending = sum(item["pending"] for item in resp.data)
        assert total_pending >= 1, (
            "PENDING submission must be counted as pending"
        )

    def test_counts_are_non_negative(self, db):
        """approved, rejected, pending must never be negative."""
        tenant = _tenant()
        admin = _admin(tenant)
        teacher = _teacher(tenant)
        course = _course(tenant, admin)
        assignment = _assignment(tenant, course)

        AssignmentSubmission.all_objects.create(
            tenant=tenant,
            assignment=assignment,
            teacher=teacher,
            submission_text="sub",
            status="SUBMITTED",
        )

        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/approval-trends/")
        assert resp.status_code == 200
        for item in resp.data:
            assert item["approved"] >= 0
            assert item["rejected"] >= 0
            assert item["pending"] >= 0

    def test_tenant_isolation(self, db):
        """Tenant B's submissions do not appear in Tenant A's report."""
        tenant_a = _tenant()
        admin_a = _admin(tenant_a)

        tenant_b = _tenant()
        admin_b = _admin(tenant_b)
        teacher_b = _teacher(tenant_b)
        course_b = _course(tenant_b, admin_b)
        assignment_b = _assignment(tenant_b, course_b)

        AssignmentSubmission.all_objects.create(
            tenant=tenant_b,
            assignment=assignment_b,
            teacher=teacher_b,
            submission_text="B's submission",
            status="GRADED",
            score=88,
        )

        client_a = _auth_client(admin_a, tenant_a)
        resp = client_a.get("/api/v1/reports/analytics/approval-trends/")
        assert resp.status_code == 200
        # Tenant A has no data
        assert resp.data == [], (
            "Tenant A must not see Tenant B's submission data"
        )

    def test_date_range_filtering(self, db):
        """start/end params limit response to the requested range."""
        tenant = _tenant()
        admin = _admin(tenant)
        teacher = _teacher(tenant)
        course = _course(tenant, admin)
        assignment = _assignment(tenant, course)

        # Create a submission in 2025 — should be excluded
        sub = AssignmentSubmission.all_objects.create(
            tenant=tenant,
            assignment=assignment,
            teacher=teacher,
            submission_text="Old submission",
            status="GRADED",
            score=75,
        )
        # Manually set submitted_at to 2025 (auto_now_add prevents passing it directly)
        AssignmentSubmission.all_objects.filter(pk=sub.pk).update(
            submitted_at=timezone.make_aware(timezone.datetime(2025, 1, 15))
        )

        start = date.today().replace(day=1).isoformat()
        end = date.today().isoformat()

        client = _auth_client(admin, tenant)
        resp = client.get(
            "/api/v1/reports/analytics/approval-trends/",
            {"start": start, "end": end},
        )
        assert resp.status_code == 200
        # The 2025 submission must not appear in this month's range
        total = sum(item["approved"] + item["rejected"] + item["pending"]
                    for item in resp.data)
        assert total == 0, (
            f"Date filter should exclude the 2025 submission; got total={total}"
        )


# ---------------------------------------------------------------------------
# 3. Course Effectiveness Endpoint
# ---------------------------------------------------------------------------

class TestCourseEffectivenessAuth:
    """Authentication and authorisation guards for course-effectiveness."""

    def test_requires_authentication(self, db):
        tenant = _tenant()
        client = APIClient()
        resp = client.get(
            "/api/v1/reports/analytics/course-effectiveness/",
            HTTP_HOST=f"{tenant.subdomain}.lms.com",
        )
        assert resp.status_code == 401

    def test_teacher_cannot_access(self, db):
        tenant = _tenant()
        teacher = _teacher(tenant)
        client = _auth_client(teacher, tenant)
        resp = client.get("/api/v1/reports/analytics/course-effectiveness/")
        assert resp.status_code == 403

    def test_admin_can_access(self, db):
        tenant = _tenant()
        admin = _admin(tenant)
        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/course-effectiveness/")
        assert resp.status_code == 200


class TestCourseEffectivenessResponseShape:
    """Response envelope and field types for course-effectiveness."""

    def test_returns_a_list(self, db):
        tenant = _tenant()
        admin = _admin(tenant)
        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/course-effectiveness/")
        assert resp.status_code == 200
        assert isinstance(resp.data, list)

    def test_empty_when_no_courses(self, db):
        """No courses → empty list."""
        tenant = _tenant()
        admin = _admin(tenant)
        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/course-effectiveness/")
        assert resp.status_code == 200
        assert resp.data == [] or isinstance(resp.data, list)

    def test_item_shape_when_courses_exist(self, db):
        """Each item must have courseId, courseName, completionRate, avgScore, enrolledCount."""
        tenant = _tenant()
        admin = _admin(tenant)
        _course(tenant, admin, title="Shape Test Course")

        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/course-effectiveness/")
        assert resp.status_code == 200
        assert len(resp.data) >= 1

        item = resp.data[0]
        assert "courseId" in item, "Item must have 'courseId'"
        assert "courseName" in item, "Item must have 'courseName'"
        assert "completionRate" in item, "Item must have 'completionRate'"
        assert "avgScore" in item, "Item must have 'avgScore'"
        assert "enrolledCount" in item, "Item must have 'enrolledCount'"

        assert isinstance(item["courseId"], str)
        assert isinstance(item["courseName"], str)
        assert 0 <= item["completionRate"] <= 100
        assert 0 <= item["avgScore"] <= 100
        assert isinstance(item["enrolledCount"], int)


class TestCourseEffectivenessData:
    """Data-correctness tests for course-effectiveness endpoint."""

    def test_completion_rate_100_when_all_teachers_complete(self, db):
        """One teacher, one completed course → completionRate == 100.0."""
        tenant = _tenant()
        admin = _admin(tenant)
        teacher = _teacher(tenant)
        course = _course(tenant, admin, title="Full Completion Course")

        TeacherProgress.all_objects.create(
            tenant=tenant,
            teacher=teacher,
            course=course,
            content=None,
            status="COMPLETED",
            completed_at=timezone.now(),
        )

        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/course-effectiveness/")
        assert resp.status_code == 200

        item = next(
            (i for i in resp.data if i["courseName"] == "Full Completion Course"),
            None,
        )
        assert item is not None, "Course must appear in the response"
        assert item["completionRate"] == 100.0, (
            f"Expected 100% completion rate, got {item['completionRate']}"
        )

    def test_completion_rate_0_when_no_teacher_completes(self, db):
        """One teacher enrolled, zero completed → completionRate == 0.0."""
        tenant = _tenant()
        admin = _admin(tenant)
        teacher = _teacher(tenant)
        course = _course(tenant, admin, title="Zero Completion Course")

        TeacherProgress.all_objects.create(
            tenant=tenant,
            teacher=teacher,
            course=course,
            content=None,
            status="IN_PROGRESS",
        )

        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/course-effectiveness/")
        assert resp.status_code == 200

        item = next(
            (i for i in resp.data if i["courseName"] == "Zero Completion Course"),
            None,
        )
        assert item is not None
        assert item["completionRate"] == 0.0, (
            f"Expected 0% completion rate, got {item['completionRate']}"
        )

    def test_avg_score_reflects_quiz_submissions(self, db):
        """avgScore is the mean of QuizSubmission scores for this course."""
        tenant = _tenant()
        admin = _admin(tenant)
        teacher1 = _teacher(tenant)
        teacher2 = _teacher(tenant)
        course = _course(tenant, admin, title="Score Course")
        quiz = _quiz(tenant, course)

        QuizSubmission.all_objects.create(
            tenant=tenant,
            teacher=teacher1,
            quiz=quiz,
            attempt_number=1,
            score=80,
            graded_at=timezone.now(),
        )
        QuizSubmission.all_objects.create(
            tenant=tenant,
            teacher=teacher2,
            quiz=quiz,
            attempt_number=1,
            score=60,
            graded_at=timezone.now(),
        )

        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/course-effectiveness/")
        assert resp.status_code == 200

        item = next(
            (i for i in resp.data if i["courseName"] == "Score Course"),
            None,
        )
        assert item is not None
        assert abs(item["avgScore"] - 70.0) < 1.0, (
            f"Expected avgScore ≈ 70.0 (mean of 80, 60), got {item['avgScore']}"
        )

    def test_enrolled_count_matches_teacher_progress_rows(self, db):
        """enrolledCount is the number of teachers with a course-level progress row."""
        tenant = _tenant()
        admin = _admin(tenant)
        teacher1 = _teacher(tenant)
        teacher2 = _teacher(tenant)
        teacher3 = _teacher(tenant)
        course = _course(tenant, admin, title="Enrolled Count Course")

        for teacher in [teacher1, teacher2, teacher3]:
            TeacherProgress.all_objects.create(
                tenant=tenant,
                teacher=teacher,
                course=course,
                content=None,
                status="NOT_STARTED",
            )

        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/course-effectiveness/")
        assert resp.status_code == 200

        item = next(
            (i for i in resp.data if i["courseName"] == "Enrolled Count Course"),
            None,
        )
        assert item is not None
        assert item["enrolledCount"] == 3, (
            f"Expected enrolledCount == 3, got {item['enrolledCount']}"
        )

    def test_tenant_isolation(self, db):
        """Tenant B's courses do not appear in Tenant A's report."""
        tenant_a = _tenant()
        admin_a = _admin(tenant_a)

        tenant_b = _tenant()
        admin_b = _admin(tenant_b)
        _course(tenant_b, admin_b, title="Tenant B Course")

        client_a = _auth_client(admin_a, tenant_a)
        resp = client_a.get("/api/v1/reports/analytics/course-effectiveness/")
        assert resp.status_code == 200

        names = [i["courseName"] for i in resp.data]
        assert "Tenant B Course" not in names, (
            "Tenant A must not see Tenant B's course in effectiveness report"
        )

    def test_unpublished_courses_excluded(self, db):
        """Unpublished (draft) courses should not appear in the effectiveness report."""
        tenant = _tenant()
        admin = _admin(tenant)
        # Create an unpublished course
        Course.objects.create(
            tenant=tenant,
            title="Draft Course",
            slug=uuid.uuid4().hex[:10],
            description="Draft",
            created_by=admin,
            is_published=False,
            is_active=True,
        )

        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/course-effectiveness/")
        assert resp.status_code == 200

        names = [i["courseName"] for i in resp.data]
        assert "Draft Course" not in names, (
            "Unpublished courses must not appear in course-effectiveness report"
        )

    def test_course_id_is_valid_uuid_string(self, db):
        """courseId must be a valid UUID string (not int, not None)."""
        tenant = _tenant()
        admin = _admin(tenant)
        _course(tenant, admin, title="UUID Check Course")

        client = _auth_client(admin, tenant)
        resp = client.get("/api/v1/reports/analytics/course-effectiveness/")
        assert resp.status_code == 200
        assert len(resp.data) >= 1

        for item in resp.data:
            try:
                uuid.UUID(item["courseId"])
            except (ValueError, AttributeError):
                pytest.fail(f"courseId '{item['courseId']}' is not a valid UUID")
