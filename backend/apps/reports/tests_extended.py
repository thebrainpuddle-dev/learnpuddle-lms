# apps/reports/tests_extended.py
#
# Supplementary tests for the reports app.
# These extend (do NOT modify) the existing tests.py.

import uuid

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.courses.models import Content, Course, Module
from apps.progress.models import Assignment, AssignmentSubmission, TeacherProgress


# ---------------------------------------------------------------------------
# Base class shared by most test cases
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class ReportsExtendedTestBase(TestCase):
    """
    Shared fixture for extended report tests.

    Creates:
      - one active tenant with subdomain="test"
      - one SCHOOL_ADMIN (self.admin)
      - two TEACHERs (self.teacher / self.teacher2)
      - one Course assigned to all teachers
      - one Module + one Content inside that course
      - one Assignment linked to that content
    """

    def setUp(self):
        self.client = APIClient()

        self.tenant = Tenant.objects.create(
            name="Reports School",
            slug="reports-school-ext",
            subdomain="test",
            email="t@t.com",
            is_active=True,
        )

        self.admin = User.objects.create_user(
            email="admin@reports.test",
            password="admin123",
            first_name="Admin",
            last_name="Reports",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )

        self.teacher = User.objects.create_user(
            email="teacher1@reports.test",
            password="teacher123",
            first_name="Alice",
            last_name="Smith",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )

        self.teacher2 = User.objects.create_user(
            email="teacher2@reports.test",
            password="teacher123",
            first_name="Bob",
            last_name="Jones",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )

        self.course = Course.objects.create(
            tenant=self.tenant,
            title="Test Course",
            slug="test-course-rep-ext",
            description="Test",
            created_by=self.admin,
            is_published=True,
            is_active=True,
            assigned_to_all=True,
        )

        self.module = Module.objects.create(
            course=self.course,
            title="Module 1",
            description="",
            order=1,
            is_active=True,
        )

        self.content = Content.objects.create(
            module=self.module,
            title="Lesson 1",
            content_type="TEXT",
            order=1,
            text_content="<p>Hello</p>",
            is_active=True,
        )

        self.assignment = Assignment.objects.create(
            tenant=self.tenant,
            course=self.course,
            module=self.module,
            content=self.content,
            title="Test Assignment",
            description="Describe what you learned.",
            generation_source="MANUAL",
            is_mandatory=True,
            is_active=True,
        )

        self.client.force_authenticate(user=self.admin)

    def _get(self, url, **kwargs):
        return self.client.get(url, HTTP_HOST="test.lms.com", **kwargs)


# ---------------------------------------------------------------------------
# 1. Authentication guard tests (no force_authenticate)
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class ReportsAuthTestCase(TestCase):
    """
    Unauthenticated requests to every report endpoint must return 401.
    """

    def setUp(self):
        self.client = APIClient()
        # Tenant must exist so middleware can resolve it from the Host header.
        self.tenant = Tenant.objects.create(
            name="Auth Test School",
            slug="auth-test-school",
            subdomain="test",
            email="auth@test.com",
            is_active=True,
        )
        self.course = Course.objects.create(
            tenant=self.tenant,
            title="Auth Course",
            slug="auth-course",
            description="Auth test",
            created_by=None,
            is_published=True,
            is_active=True,
            assigned_to_all=True,
        )
        self.assignment = Assignment.objects.create(
            tenant=self.tenant,
            course=self.course,
            title="Auth Assignment",
            description="Auth test assignment.",
            generation_source="MANUAL",
            is_active=True,
        )

    def _get(self, url, **kwargs):
        return self.client.get(url, HTTP_HOST="test.lms.com", **kwargs)

    def test_course_progress_unauthenticated_returns_401(self):
        resp = self._get(f"/api/reports/course-progress/?course_id={self.course.id}")
        self.assertEqual(resp.status_code, 401)

    def test_assignment_status_unauthenticated_returns_401(self):
        resp = self._get(f"/api/reports/assignment-status/?assignment_id={self.assignment.id}")
        self.assertEqual(resp.status_code, 401)

    def test_list_courses_unauthenticated_returns_401(self):
        resp = self._get("/api/reports/courses/")
        self.assertEqual(resp.status_code, 401)

    def test_list_assignments_unauthenticated_returns_401(self):
        resp = self._get("/api/reports/assignments/")
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# 2. Course progress report tests
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class CourseProgressReportTestCase(ReportsExtendedTestBase):
    """
    Tests for GET /api/reports/course-progress/
    """

    def test_missing_course_id_returns_400(self):
        """Omitting course_id query param must return 400 with an error key."""
        resp = self._get("/api/reports/course-progress/")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.data)

    def test_both_teachers_appear_in_results_for_assigned_to_all_course(self):
        """With assigned_to_all=True both active teachers must appear in results."""
        resp = self._get(f"/api/reports/course-progress/?course_id={self.course.id}")
        self.assertEqual(resp.status_code, 200)
        rows = resp.data["results"]
        teacher_ids = {str(r["teacher_id"]) for r in rows}
        self.assertIn(str(self.teacher.id), teacher_ids)
        self.assertIn(str(self.teacher2.id), teacher_ids)

    def test_status_filter_not_started_shows_teachers_without_progress(self):
        """
        Teachers who have no TeacherProgress row should show as NOT_STARTED.
        Filtering by ?status=NOT_STARTED must include them.
        """
        # No TeacherProgress records created — both teachers are NOT_STARTED.
        resp = self._get(
            f"/api/reports/course-progress/?course_id={self.course.id}&status=NOT_STARTED"
        )
        self.assertEqual(resp.status_code, 200)
        rows = resp.data["results"]
        self.assertTrue(len(rows) >= 2, "Both teachers should appear as NOT_STARTED")
        for row in rows:
            self.assertEqual(row["status"], "NOT_STARTED")

    def test_status_filter_completed_returns_only_completed_teacher(self):
        """
        After creating a COMPLETED TeacherProgress for teacher (Alice),
        ?status=COMPLETED must return Alice but not Bob.
        """
        TeacherProgress.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            course=self.course,
            content=self.content,
            status="COMPLETED",
            progress_percentage=100,
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )
        resp = self._get(
            f"/api/reports/course-progress/?course_id={self.course.id}&status=COMPLETED"
        )
        self.assertEqual(resp.status_code, 200)
        rows = resp.data["results"]
        # All returned rows must be COMPLETED
        for row in rows:
            self.assertEqual(row["status"], "COMPLETED")
        # Alice's row must be present
        teacher_ids_in_rows = {str(r["teacher_id"]) for r in rows}
        self.assertIn(str(self.teacher.id), teacher_ids_in_rows)
        # Bob must NOT be present (he has no progress)
        self.assertNotIn(str(self.teacher2.id), teacher_ids_in_rows)

    def test_search_filter_by_first_name_returns_matching_teacher(self):
        """?search=Alice must return Alice Smith's row only."""
        resp = self._get(
            f"/api/reports/course-progress/?course_id={self.course.id}&search=Alice"
        )
        self.assertEqual(resp.status_code, 200)
        rows = resp.data["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(str(rows[0]["teacher_id"]), str(self.teacher.id))

    def test_search_filter_case_insensitive_by_last_name(self):
        """?search=jones (lowercase) must return Bob Jones' row."""
        resp = self._get(
            f"/api/reports/course-progress/?course_id={self.course.id}&search=jones"
        )
        self.assertEqual(resp.status_code, 200)
        rows = resp.data["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(str(rows[0]["teacher_id"]), str(self.teacher2.id))

    def test_response_contains_expected_fields(self):
        """Each result row must contain the documented fields."""
        resp = self._get(f"/api/reports/course-progress/?course_id={self.course.id}")
        self.assertEqual(resp.status_code, 200)
        rows = resp.data["results"]
        self.assertTrue(len(rows) > 0)
        required_keys = {
            "teacher_id", "teacher_name", "teacher_email",
            "course_id", "course_title", "status",
        }
        for row in rows:
            self.assertTrue(required_keys.issubset(row.keys()))

    def test_nonexistent_course_id_returns_404(self):
        """A UUID that doesn't map to a course must return 404."""
        resp = self._get(f"/api/reports/course-progress/?course_id={uuid.uuid4()}")
        self.assertEqual(resp.status_code, 404)

    def test_status_filter_completed_excluded_from_not_started(self):
        """
        After marking Alice as COMPLETED, ?status=NOT_STARTED must not include her.
        """
        TeacherProgress.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            course=self.course,
            content=self.content,
            status="COMPLETED",
            progress_percentage=100,
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )
        resp = self._get(
            f"/api/reports/course-progress/?course_id={self.course.id}&status=NOT_STARTED"
        )
        self.assertEqual(resp.status_code, 200)
        rows = resp.data["results"]
        teacher_ids_in_rows = {str(r["teacher_id"]) for r in rows}
        self.assertNotIn(str(self.teacher.id), teacher_ids_in_rows)


# ---------------------------------------------------------------------------
# 3. Assignment status report tests
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class AssignmentStatusReportTestCase(ReportsExtendedTestBase):
    """
    Tests for GET /api/reports/assignment-status/
    """

    def test_missing_assignment_id_returns_400(self):
        """Omitting assignment_id query param must return 400 with an error key."""
        resp = self._get("/api/reports/assignment-status/")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.data)

    def test_nonexistent_assignment_id_returns_404(self):
        """A random UUID that doesn't map to an assignment returns 404."""
        resp = self._get(f"/api/reports/assignment-status/?assignment_id={uuid.uuid4()}")
        self.assertEqual(resp.status_code, 404)

    def test_teachers_show_pending_when_no_submission_exists(self):
        """
        Teachers assigned to the course but with no submission record
        must appear in results with status=PENDING.
        """
        resp = self._get(
            f"/api/reports/assignment-status/?assignment_id={self.assignment.id}"
        )
        self.assertEqual(resp.status_code, 200)
        rows = resp.data["results"]
        teacher_ids_in_rows = {str(r["teacher_id"]) for r in rows}
        self.assertIn(str(self.teacher.id), teacher_ids_in_rows)
        self.assertIn(str(self.teacher2.id), teacher_ids_in_rows)
        for row in rows:
            self.assertEqual(row["status"], "PENDING")

    def test_teacher_shows_submitted_after_submission_created(self):
        """
        After creating an AssignmentSubmission with status=SUBMITTED for Alice,
        her row must show SUBMITTED while Bob remains PENDING.
        """
        AssignmentSubmission.all_objects.create(
            tenant=self.tenant,
            assignment=self.assignment,
            teacher=self.teacher,
            submission_text="My answer.",
            status="SUBMITTED",
        )
        resp = self._get(
            f"/api/reports/assignment-status/?assignment_id={self.assignment.id}"
        )
        self.assertEqual(resp.status_code, 200)
        rows = resp.data["results"]
        row_map = {str(r["teacher_id"]): r for r in rows}

        self.assertIn(str(self.teacher.id), row_map)
        self.assertEqual(row_map[str(self.teacher.id)]["status"], "SUBMITTED")

        self.assertIn(str(self.teacher2.id), row_map)
        self.assertEqual(row_map[str(self.teacher2.id)]["status"], "PENDING")

    def test_status_filter_pending_excludes_submitted_teacher(self):
        """
        ?status=PENDING must return only teachers without a submission.
        """
        AssignmentSubmission.all_objects.create(
            tenant=self.tenant,
            assignment=self.assignment,
            teacher=self.teacher,
            submission_text="My answer.",
            status="SUBMITTED",
        )
        resp = self._get(
            f"/api/reports/assignment-status/?assignment_id={self.assignment.id}&status=PENDING"
        )
        self.assertEqual(resp.status_code, 200)
        rows = resp.data["results"]
        teacher_ids_in_rows = {str(r["teacher_id"]) for r in rows}
        # Bob is PENDING — must be present
        self.assertIn(str(self.teacher2.id), teacher_ids_in_rows)
        # Alice is SUBMITTED — must NOT be present
        self.assertNotIn(str(self.teacher.id), teacher_ids_in_rows)

    def test_search_filter_narrows_results(self):
        """?search=Alice must return only Alice's row."""
        resp = self._get(
            f"/api/reports/assignment-status/?assignment_id={self.assignment.id}&search=Alice"
        )
        self.assertEqual(resp.status_code, 200)
        rows = resp.data["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(str(rows[0]["teacher_id"]), str(self.teacher.id))

    def test_response_contains_expected_fields(self):
        """Each result row must contain the documented fields."""
        resp = self._get(
            f"/api/reports/assignment-status/?assignment_id={self.assignment.id}"
        )
        self.assertEqual(resp.status_code, 200)
        rows = resp.data["results"]
        self.assertTrue(len(rows) > 0)
        required_keys = {
            "teacher_id", "teacher_name", "teacher_email",
            "assignment_id", "assignment_title", "status",
        }
        for row in rows:
            self.assertTrue(required_keys.issubset(row.keys()))

    def test_graded_submission_shows_correct_status(self):
        """A submission with status=GRADED must be reflected in the report row."""
        AssignmentSubmission.all_objects.create(
            tenant=self.tenant,
            assignment=self.assignment,
            teacher=self.teacher,
            submission_text="Graded answer.",
            status="GRADED",
        )
        resp = self._get(
            f"/api/reports/assignment-status/?assignment_id={self.assignment.id}"
        )
        self.assertEqual(resp.status_code, 200)
        rows = resp.data["results"]
        row_map = {str(r["teacher_id"]): r for r in rows}
        self.assertEqual(row_map[str(self.teacher.id)]["status"], "GRADED")


# ---------------------------------------------------------------------------
# 4. CSV export tests
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class ReportsExportTestCase(ReportsExtendedTestBase):
    """
    Tests for the CSV export endpoints:
      - GET /api/reports/course-progress/export/
      - GET /api/reports/assignment-status/export/

    These endpoints require the feature_reports_export flag to be enabled on
    the tenant (stored as a BooleanField on the Tenant model).
    """

    def _enable_export_feature(self):
        self.tenant.feature_reports_export = True
        self.tenant.save(update_fields=["feature_reports_export"])

    # -- course progress export --

    def test_course_progress_export_without_feature_flag_returns_403(self):
        """feature_reports_export=False (default) → 403 upgrade_required."""
        # Ensure the flag is off
        self.tenant.feature_reports_export = False
        self.tenant.save(update_fields=["feature_reports_export"])

        resp = self._get(
            f"/api/reports/course-progress/export/?course_id={self.course.id}"
        )
        self.assertEqual(resp.status_code, 403)

    def test_course_progress_export_with_feature_flag_returns_200_csv(self):
        """feature_reports_export=True → HTTP 200 with text/csv content type."""
        self._enable_export_feature()

        resp = self._get(
            f"/api/reports/course-progress/export/?course_id={self.course.id}"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])

    def test_course_progress_csv_contains_teacher_columns(self):
        """Exported CSV must include Teacher Name and Email columns."""
        self._enable_export_feature()

        resp = self._get(
            f"/api/reports/course-progress/export/?course_id={self.course.id}"
        )
        self.assertEqual(resp.status_code, 200)
        # Django HttpResponse: read content as string
        content = resp.content.decode("utf-8")
        # Header row should contain the column names used in the view
        self.assertIn("Teacher Name", content)
        self.assertIn("Email", content)

    def test_course_progress_csv_contains_teacher_email(self):
        """Exported CSV data rows must contain Alice's email."""
        self._enable_export_feature()

        resp = self._get(
            f"/api/reports/course-progress/export/?course_id={self.course.id}"
        )
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn(self.teacher.email, content)

    def test_course_progress_export_missing_course_id_returns_400(self):
        """Omitting course_id with the feature enabled must return 400."""
        self._enable_export_feature()

        resp = self._get("/api/reports/course-progress/export/")
        self.assertEqual(resp.status_code, 400)

    # -- assignment status export --

    def test_assignment_status_export_without_feature_flag_returns_403(self):
        """feature_reports_export=False (default) → 403 upgrade_required."""
        self.tenant.feature_reports_export = False
        self.tenant.save(update_fields=["feature_reports_export"])

        resp = self._get(
            f"/api/reports/assignment-status/export/?assignment_id={self.assignment.id}"
        )
        self.assertEqual(resp.status_code, 403)

    def test_assignment_status_export_with_feature_flag_returns_200_csv(self):
        """feature_reports_export=True → HTTP 200 with text/csv content type."""
        self._enable_export_feature()

        resp = self._get(
            f"/api/reports/assignment-status/export/?assignment_id={self.assignment.id}"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])

    def test_assignment_status_csv_contains_teacher_columns(self):
        """Exported assignment CSV must include Teacher Name and Email columns."""
        self._enable_export_feature()

        resp = self._get(
            f"/api/reports/assignment-status/export/?assignment_id={self.assignment.id}"
        )
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("Teacher Name", content)
        self.assertIn("Email", content)

    def test_assignment_status_export_missing_assignment_id_returns_400(self):
        """Omitting assignment_id with the feature enabled must return 400."""
        self._enable_export_feature()

        resp = self._get("/api/reports/assignment-status/export/")
        self.assertEqual(resp.status_code, 400)

    def test_assignment_status_csv_reflects_submission_status(self):
        """After creating a SUBMITTED submission, the CSV must show SUBMITTED for that teacher."""
        self._enable_export_feature()

        AssignmentSubmission.all_objects.create(
            tenant=self.tenant,
            assignment=self.assignment,
            teacher=self.teacher,
            submission_text="Export test answer.",
            status="SUBMITTED",
        )

        resp = self._get(
            f"/api/reports/assignment-status/export/?assignment_id={self.assignment.id}"
        )
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("SUBMITTED", content)


# ---------------------------------------------------------------------------
# 5. List assignments with course_id filter
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class ListAssignmentsFilterTestCase(ReportsExtendedTestBase):
    """
    Tests for GET /api/reports/assignments/  (list_assignments_for_reports)
    """

    def setUp(self):
        super().setUp()
        # Create a second course + assignment for a different course
        self.course2 = Course.objects.create(
            tenant=self.tenant,
            title="Second Course",
            slug="second-course-rep-ext",
            description="Another test course",
            created_by=self.admin,
            is_published=True,
            is_active=True,
            assigned_to_all=True,
        )
        self.module2 = Module.objects.create(
            course=self.course2,
            title="Module A",
            description="",
            order=1,
            is_active=True,
        )
        self.assignment2 = Assignment.objects.create(
            tenant=self.tenant,
            course=self.course2,
            module=self.module2,
            title="Second Course Assignment",
            description="Assignment for the second course.",
            generation_source="MANUAL",
            is_mandatory=False,
            is_active=True,
        )

    def test_filter_by_course_id_returns_only_assignments_for_that_course(self):
        """?course_id=<id> must return assignments belonging to that course only."""
        resp = self._get(f"/api/reports/assignments/?course_id={self.course.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.data
        # All returned assignments must belong to self.course
        for item in data:
            self.assertEqual(str(item["course_id"]), str(self.course.id))
        # self.assignment must appear; self.assignment2 must not
        returned_ids = {str(item["id"]) for item in data}
        self.assertIn(str(self.assignment.id), returned_ids)
        self.assertNotIn(str(self.assignment2.id), returned_ids)

    def test_without_course_id_filter_returns_all_tenant_assignments(self):
        """Without course_id, all active assignments for the tenant must be returned."""
        resp = self._get("/api/reports/assignments/")
        self.assertEqual(resp.status_code, 200)
        data = resp.data
        returned_ids = {str(item["id"]) for item in data}
        self.assertIn(str(self.assignment.id), returned_ids)
        self.assertIn(str(self.assignment2.id), returned_ids)

    def test_filter_by_second_course_id_excludes_first_course_assignment(self):
        """?course_id=<course2_id> must not include the assignment from course 1."""
        resp = self._get(f"/api/reports/assignments/?course_id={self.course2.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.data
        returned_ids = {str(item["id"]) for item in data}
        self.assertIn(str(self.assignment2.id), returned_ids)
        self.assertNotIn(str(self.assignment.id), returned_ids)

    def test_assignments_response_contains_expected_fields(self):
        """Each item in the assignments list must contain id, title, course_id, due_date."""
        resp = self._get("/api/reports/assignments/")
        self.assertEqual(resp.status_code, 200)
        data = resp.data
        self.assertTrue(len(data) >= 1)
        required_keys = {"id", "title", "course_id", "due_date"}
        for item in data:
            self.assertTrue(required_keys.issubset(item.keys()))

    def test_teacher_cannot_access_list_assignments(self):
        """A TEACHER role must receive 403 when listing assignments for reports."""
        self.client.force_authenticate(user=self.teacher)
        resp = self._get("/api/reports/assignments/")
        self.assertEqual(resp.status_code, 403)
