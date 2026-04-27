# tests/reports/test_reports_views.py
"""
Tests for the reports app.

Covers:
- Authentication requirements (401 without token)
- Role-based access control (admin only)
- course_progress_report: requires course_id, returns row per teacher
- assignment_status_report: requires assignment_id, returns row per teacher
- list_courses_for_reports: returns tenant-scoped courses
- list_assignments_for_reports: returns assignments filtered by course
- CSV export endpoints (feature-gated)
- Tenant isolation (admin B cannot see tenant A's report data)
"""

import pytest
from rest_framework.test import APIClient

from apps.courses.models import Course, Module
from apps.progress.models import Assignment, AssignmentSubmission


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_course(tenant, admin_user, title="Report Course", assigned_to_all=True):
    """Create a course with assigned_to_all=True so teachers appear in reports."""
    return Course.objects.create(
        tenant=tenant,
        title=title,
        slug=title.lower().replace(" ", "-"),
        description="Test course",
        created_by=admin_user,
        is_published=True,
        is_active=True,
        assigned_to_all=assigned_to_all,
    )


def _make_assignment(tenant, course, title="Report Assignment"):
    """Create an Assignment for a course."""
    return Assignment.objects.create(
        tenant=tenant,
        course=course,
        title=title,
        description="Test assignment description",
        is_active=True,
    )


# ---------------------------------------------------------------------------
# Authentication Tests
# ---------------------------------------------------------------------------

class TestReportsAuthRequired:
    """All report endpoints require authentication."""

    def test_course_progress_requires_auth(self, api_client, tenant):
        response = api_client.get(
            "/api/v1/reports/course-progress/",
            HTTP_HOST=f"{tenant.subdomain}.lms.com",
        )
        assert response.status_code == 401

    def test_assignment_status_requires_auth(self, api_client, tenant):
        response = api_client.get(
            "/api/v1/reports/assignment-status/",
            HTTP_HOST=f"{tenant.subdomain}.lms.com",
        )
        assert response.status_code == 401

    def test_list_courses_requires_auth(self, api_client, tenant):
        response = api_client.get(
            "/api/v1/reports/courses/",
            HTTP_HOST=f"{tenant.subdomain}.lms.com",
        )
        assert response.status_code == 401

    def test_list_assignments_requires_auth(self, api_client, tenant):
        response = api_client.get(
            "/api/v1/reports/assignments/",
            HTTP_HOST=f"{tenant.subdomain}.lms.com",
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Role Enforcement Tests
# ---------------------------------------------------------------------------

class TestReportsRoleEnforcement:
    """Report endpoints are admin-only."""

    def test_teacher_cannot_access_course_progress(self, teacher_client):
        response = teacher_client.get("/api/v1/reports/course-progress/")
        assert response.status_code == 403

    def test_teacher_cannot_access_assignment_status(self, teacher_client):
        response = teacher_client.get("/api/v1/reports/assignment-status/")
        assert response.status_code == 403

    def test_teacher_cannot_list_courses_for_reports(self, teacher_client):
        response = teacher_client.get("/api/v1/reports/courses/")
        assert response.status_code == 403

    def test_teacher_cannot_list_assignments_for_reports(self, teacher_client):
        response = teacher_client.get("/api/v1/reports/assignments/")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Course Progress Report Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCourseProgressReport:
    """GET /api/v1/reports/course-progress/"""

    def test_missing_course_id_returns_400(self, admin_client):
        response = admin_client.get("/api/v1/reports/course-progress/")
        assert response.status_code == 400

    def test_nonexistent_course_returns_404(self, admin_client):
        import uuid
        fake_id = uuid.uuid4()
        response = admin_client.get(f"/api/v1/reports/course-progress/?course_id={fake_id}")
        assert response.status_code == 404

    def test_valid_course_returns_200(self, admin_client, admin_user, tenant):
        course = _make_course(tenant, admin_user)
        response = admin_client.get(
            f"/api/v1/reports/course-progress/?course_id={course.id}"
        )
        assert response.status_code == 200
        assert "results" in response.data

    def test_teacher_appears_in_report_when_assigned_to_all(
        self, admin_client, admin_user, teacher_user, tenant
    ):
        """With assigned_to_all=True, the teacher appears in the progress report."""
        course = _make_course(tenant, admin_user, assigned_to_all=True)
        response = admin_client.get(
            f"/api/v1/reports/course-progress/?course_id={course.id}"
        )
        assert response.status_code == 200
        rows = response.data["results"]
        emails = [r["teacher_email"] for r in rows]
        assert teacher_user.email in emails

    def test_not_started_status_for_untracked_teacher(
        self, admin_client, admin_user, teacher_user, tenant
    ):
        """Teacher with no progress record appears with NOT_STARTED status."""
        course = _make_course(tenant, admin_user, assigned_to_all=True)
        response = admin_client.get(
            f"/api/v1/reports/course-progress/?course_id={course.id}"
        )
        assert response.status_code == 200
        rows = response.data["results"]
        teacher_row = next(
            (r for r in rows if r["teacher_email"] == teacher_user.email), None
        )
        assert teacher_row is not None
        assert teacher_row["status"] == "NOT_STARTED"

    def test_course_belongs_to_different_tenant_returns_404(
        self, admin_client, admin_user, tenant, admin_user_b, tenant_b, api_client_for
    ):
        """Report for a course from another tenant returns 404."""
        # Course belongs to tenant_b
        course_b = _make_course(tenant_b, admin_user_b, title="B Course")
        # Request with admin client of tenant_a
        response = admin_client.get(
            f"/api/v1/reports/course-progress/?course_id={course_b.id}"
        )
        assert response.status_code == 404

    def test_status_filter_works(self, admin_client, admin_user, teacher_user, tenant):
        """?status=NOT_STARTED filters rows by status."""
        course = _make_course(tenant, admin_user, assigned_to_all=True)
        response = admin_client.get(
            f"/api/v1/reports/course-progress/?course_id={course.id}&status=NOT_STARTED"
        )
        assert response.status_code == 200
        for row in response.data["results"]:
            assert row["status"] == "NOT_STARTED"

    def test_search_filter_works(self, admin_client, admin_user, teacher_user, tenant):
        """?search=<email> filters results."""
        course = _make_course(tenant, admin_user, assigned_to_all=True)
        # Search by teacher's unique first name
        response = admin_client.get(
            f"/api/v1/reports/course-progress/?course_id={course.id}&search=Teacher"
        )
        assert response.status_code == 200
        rows = response.data["results"]
        emails = [r["teacher_email"] for r in rows]
        assert teacher_user.email in emails


# ---------------------------------------------------------------------------
# Assignment Status Report Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAssignmentStatusReport:
    """GET /api/v1/reports/assignment-status/"""

    def test_missing_assignment_id_returns_400(self, admin_client):
        response = admin_client.get("/api/v1/reports/assignment-status/")
        assert response.status_code == 400

    def test_nonexistent_assignment_returns_404(self, admin_client):
        import uuid
        fake_id = uuid.uuid4()
        response = admin_client.get(
            f"/api/v1/reports/assignment-status/?assignment_id={fake_id}"
        )
        assert response.status_code == 404

    def test_valid_assignment_returns_200(self, admin_client, admin_user, tenant):
        course = _make_course(tenant, admin_user)
        assignment = _make_assignment(tenant, course)
        response = admin_client.get(
            f"/api/v1/reports/assignment-status/?assignment_id={assignment.id}"
        )
        assert response.status_code == 200
        assert "results" in response.data

    def test_teacher_has_pending_status_without_submission(
        self, admin_client, admin_user, teacher_user, tenant
    ):
        """Teacher with no submission is shown as PENDING."""
        course = _make_course(tenant, admin_user, assigned_to_all=True)
        assignment = _make_assignment(tenant, course)
        response = admin_client.get(
            f"/api/v1/reports/assignment-status/?assignment_id={assignment.id}"
        )
        assert response.status_code == 200
        rows = response.data["results"]
        teacher_row = next(
            (r for r in rows if r["teacher_email"] == teacher_user.email), None
        )
        assert teacher_row is not None
        assert teacher_row["status"] == "PENDING"

    def test_teacher_shows_submitted_status_after_submission(
        self, admin_client, admin_user, teacher_user, tenant
    ):
        """Teacher with a SUBMITTED record shows correct status."""
        course = _make_course(tenant, admin_user, assigned_to_all=True)
        assignment = _make_assignment(tenant, course)
        AssignmentSubmission.objects.create(
            tenant=tenant,
            assignment=assignment,
            teacher=teacher_user,
            status="SUBMITTED",
        )
        response = admin_client.get(
            f"/api/v1/reports/assignment-status/?assignment_id={assignment.id}"
        )
        assert response.status_code == 200
        rows = response.data["results"]
        teacher_row = next(
            (r for r in rows if r["teacher_email"] == teacher_user.email), None
        )
        assert teacher_row is not None
        assert teacher_row["status"] == "SUBMITTED"

    def test_assignment_from_another_tenant_returns_404(
        self, admin_client, admin_user_b, tenant_b
    ):
        """Report for an assignment from another tenant returns 404."""
        course_b = _make_course(tenant_b, admin_user_b, title="B Course")
        assignment_b = _make_assignment(tenant_b, course_b)
        # admin_client is for tenant A
        response = admin_client.get(
            f"/api/v1/reports/assignment-status/?assignment_id={assignment_b.id}"
        )
        assert response.status_code == 404

    def test_status_filter_returns_only_matching(
        self, admin_client, admin_user, teacher_user, tenant
    ):
        """?status=PENDING returns only PENDING rows."""
        course = _make_course(tenant, admin_user, assigned_to_all=True)
        assignment = _make_assignment(tenant, course)
        response = admin_client.get(
            f"/api/v1/reports/assignment-status/?assignment_id={assignment.id}&status=PENDING"
        )
        assert response.status_code == 200
        for row in response.data["results"]:
            assert row["status"] == "PENDING"


# ---------------------------------------------------------------------------
# List Courses for Reports
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestListCoursesForReports:
    """GET /api/v1/reports/courses/"""

    def test_admin_can_list_courses(self, admin_client):
        response = admin_client.get("/api/v1/reports/courses/")
        assert response.status_code == 200
        assert isinstance(response.data, list)

    def test_lists_only_active_courses(self, admin_client, admin_user, tenant):
        active = _make_course(tenant, admin_user, title="Active Course")
        inactive = _make_course(tenant, admin_user, title="Inactive Course")
        inactive.is_active = False
        inactive.save()
        response = admin_client.get("/api/v1/reports/courses/")
        assert response.status_code == 200
        titles = [c["title"] for c in response.data]
        assert "Active Course" in titles
        assert "Inactive Course" not in titles

    def test_courses_have_required_fields(self, admin_client, admin_user, tenant):
        _make_course(tenant, admin_user, title="Fields Test Course")
        response = admin_client.get("/api/v1/reports/courses/")
        assert response.status_code == 200
        assert len(response.data) > 0
        course_data = response.data[0]
        assert "id" in course_data
        assert "title" in course_data
        assert "deadline" in course_data

    def test_only_tenant_courses_listed(
        self, admin_client, admin_user, tenant, admin_user_b, tenant_b
    ):
        """Tenant B courses must not appear in tenant A's report."""
        _make_course(tenant, admin_user, title="Tenant A Course")
        _make_course(tenant_b, admin_user_b, title="Tenant B Course")
        response = admin_client.get("/api/v1/reports/courses/")
        assert response.status_code == 200
        titles = [c["title"] for c in response.data]
        assert "Tenant A Course" in titles
        assert "Tenant B Course" not in titles


# ---------------------------------------------------------------------------
# List Assignments for Reports
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestListAssignmentsForReports:
    """GET /api/v1/reports/assignments/"""

    def test_admin_can_list_assignments(self, admin_client, admin_user, tenant):
        course = _make_course(tenant, admin_user)
        _make_assignment(tenant, course, title="Assignment 1")
        response = admin_client.get("/api/v1/reports/assignments/")
        assert response.status_code == 200
        assert isinstance(response.data, list)

    def test_filter_by_course_id(self, admin_client, admin_user, tenant):
        course1 = _make_course(tenant, admin_user, title="Course 1")
        course2 = _make_course(tenant, admin_user, title="Course 2")
        _make_assignment(tenant, course1, title="C1 Assignment")
        _make_assignment(tenant, course2, title="C2 Assignment")
        response = admin_client.get(
            f"/api/v1/reports/assignments/?course_id={course1.id}"
        )
        assert response.status_code == 200
        titles = [a["title"] for a in response.data]
        assert "C1 Assignment" in titles
        assert "C2 Assignment" not in titles

    def test_assignments_have_required_fields(self, admin_client, admin_user, tenant):
        course = _make_course(tenant, admin_user)
        _make_assignment(tenant, course, title="Field Test Assignment")
        response = admin_client.get("/api/v1/reports/assignments/")
        assert response.status_code == 200
        assert len(response.data) > 0
        a = response.data[0]
        assert "id" in a
        assert "title" in a
        assert "course_id" in a
        assert "due_date" in a


# ---------------------------------------------------------------------------
# CSV Export Tests (feature-gated)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCourseProgressExport:
    """GET /api/v1/reports/course-progress/export/ — feature-gated CSV."""

    def test_export_blocked_without_feature_flag(self, admin_client, admin_user, tenant):
        """Feature flag OFF → 403."""
        # Ensure flag is off
        tenant.feature_reports_export = False
        tenant.save()
        course = _make_course(tenant, admin_user)
        response = admin_client.get(
            f"/api/v1/reports/course-progress/export/?course_id={course.id}"
        )
        assert response.status_code == 403

    def test_export_requires_course_id(self, admin_client, admin_user, tenant):
        tenant.feature_reports_export = True
        tenant.save()
        response = admin_client.get("/api/v1/reports/course-progress/export/")
        assert response.status_code == 400

    def test_export_returns_csv_with_feature_enabled(
        self, admin_client, admin_user, tenant
    ):
        tenant.feature_reports_export = True
        tenant.save()
        course = _make_course(tenant, admin_user)
        response = admin_client.get(
            f"/api/v1/reports/course-progress/export/?course_id={course.id}"
        )
        assert response.status_code == 200
        assert "text/csv" in response.get("Content-Type", "")
        assert "attachment" in response.get("Content-Disposition", "")


@pytest.mark.django_db
class TestAssignmentStatusExport:
    """GET /api/v1/reports/assignment-status/export/ — feature-gated CSV."""

    def test_export_blocked_without_feature_flag(self, admin_client, admin_user, tenant):
        tenant.feature_reports_export = False
        tenant.save()
        course = _make_course(tenant, admin_user)
        assignment = _make_assignment(tenant, course)
        response = admin_client.get(
            f"/api/v1/reports/assignment-status/export/?assignment_id={assignment.id}"
        )
        assert response.status_code == 403

    def test_export_requires_assignment_id(self, admin_client, admin_user, tenant):
        tenant.feature_reports_export = True
        tenant.save()
        response = admin_client.get("/api/v1/reports/assignment-status/export/")
        assert response.status_code == 400

    def test_export_returns_csv_with_feature_enabled(
        self, admin_client, admin_user, tenant
    ):
        tenant.feature_reports_export = True
        tenant.save()
        course = _make_course(tenant, admin_user)
        assignment = _make_assignment(tenant, course)
        response = admin_client.get(
            f"/api/v1/reports/assignment-status/export/?assignment_id={assignment.id}"
        )
        assert response.status_code == 200
        assert "text/csv" in response.get("Content-Type", "")
