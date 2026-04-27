# apps/progress/tests_progress_views.py
"""
Tests for progress teacher_views.py endpoints:
  - teacher_dashboard
  - teacher_calendar
  - teacher_search
  - progress_start, progress_update, progress_complete
  - assignment_list, assignment_submit, assignment_submission_detail
  - quiz_detail, quiz_start, quiz_submit

Focuses on auth guards, status transitions, and edge cases.
"""
import uuid
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.courses.models import Course, Module, Content
from apps.progress.models import (
    TeacherProgress, Assignment, Quiz, QuizQuestion, QuizSubmission,
)


HOST = "test.lms.com"


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class ProgressViewsBase(TestCase):
    """Base setup for progress view tests."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Progress School", slug="prog-school", subdomain="test",
            email="prog@test.com", is_active=True,
        )
        self.admin = User.objects.create_user(
            email="padmin@test.com", password="Pass!1234",
            first_name="Admin", last_name="P",
            tenant=self.tenant, role="SCHOOL_ADMIN", is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="pteacher@test.com", password="Pass!1234",
            first_name="Teacher", last_name="P",
            tenant=self.tenant, role="TEACHER", is_active=True,
        )
        self.course = Course.objects.create(
            tenant=self.tenant, title="Test Course",
            slug="test-course-prog", description="Test",
            created_by=self.admin, is_published=True, is_active=True,
            assigned_to_all=True,
        )
        self.module = Module.objects.create(
            course=self.course, title="Module 1", order=1, is_active=True,
        )
        self.content = Content.objects.create(
            module=self.module, title="Text Content",
            content_type="TEXT", order=1, text_content="<p>Hi</p>",
            is_active=True, is_mandatory=False,
        )
        self.teacher_client = APIClient()
        self.teacher_client.force_authenticate(user=self.teacher)

        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin)


class TeacherDashboardTestCase(ProgressViewsBase):
    """Tests for GET /api/v1/teacher/dashboard/"""

    def test_unauthenticated_returns_401(self):
        response = APIClient().get("/api/v1/teacher/dashboard/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_teacher_dashboard_returns_200(self):
        response = self.teacher_client.get("/api/v1/teacher/dashboard/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_dashboard_has_stats_key(self):
        response = self.teacher_client.get("/api/v1/teacher/dashboard/", HTTP_HOST=HOST)
        self.assertIn("stats", response.data)
        self.assertIn("overall_progress", response.data["stats"])

    def test_dashboard_has_deadlines_key(self):
        response = self.teacher_client.get("/api/v1/teacher/dashboard/", HTTP_HOST=HOST)
        self.assertIn("deadlines", response.data)

    def test_dashboard_has_continue_learning_key(self):
        response = self.teacher_client.get("/api/v1/teacher/dashboard/", HTTP_HOST=HOST)
        self.assertIn("continue_learning", response.data)

    def test_admin_can_access_dashboard(self):
        response = self.admin_client.get("/api/v1/teacher/dashboard/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TeacherCalendarTestCase(ProgressViewsBase):
    """Tests for GET /api/v1/teacher/calendar/"""

    def test_unauthenticated_returns_401(self):
        response = APIClient().get("/api/v1/teacher/calendar/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_calendar_returns_200(self):
        response = self.teacher_client.get("/api/v1/teacher/calendar/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_calendar_accepts_days_param(self):
        response = self.teacher_client.get("/api/v1/teacher/calendar/?days=7", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_calendar_handles_invalid_days_param(self):
        response = self.teacher_client.get("/api/v1/teacher/calendar/?days=bad", HTTP_HOST=HOST)
        # Should default to 5 days (graceful)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TeacherSearchTestCase(ProgressViewsBase):
    """Tests for GET /api/v1/teacher/search/"""

    def test_unauthenticated_returns_401(self):
        response = APIClient().get("/api/v1/teacher/search/?q=test", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_short_query_returns_empty(self):
        response = self.teacher_client.get("/api/v1/teacher/search/?q=a", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("courses"), [])

    def test_search_returns_matching_courses(self):
        response = self.teacher_client.get("/api/v1/teacher/search/?q=Test", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("courses", response.data)
        self.assertIn("assignments", response.data)

    def test_no_query_param_returns_empty(self):
        response = self.teacher_client.get("/api/v1/teacher/search/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ProgressStartTestCase(ProgressViewsBase):
    """Tests for POST /api/v1/teacher/progress/content/<id>/start/"""

    def test_unauthenticated_returns_401(self):
        response = APIClient().post(
            f"/api/v1/teacher/progress/content/{self.content.id}/start/", HTTP_HOST=HOST
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_start_creates_progress_record(self):
        response = self.teacher_client.post(
            f"/api/v1/teacher/progress/content/{self.content.id}/start/", HTTP_HOST=HOST
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        exists = TeacherProgress.objects.filter(
            teacher=self.teacher, course=self.course, content=self.content
        ).exists()
        self.assertTrue(exists)

    def test_start_nonexistent_content_returns_404(self):
        response = self.teacher_client.post(
            f"/api/v1/teacher/progress/content/{uuid.uuid4()}/start/", HTTP_HOST=HOST
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_start_content_not_assigned_course_returns_403(self):
        other_admin = User.objects.create_user(
            email="oadmin2@test.com", password="pass", tenant=self.tenant,
            role="SCHOOL_ADMIN", is_active=True,
        )
        other_course = Course.objects.create(
            tenant=self.tenant, title="Other", slug="other-prg", description="",
            created_by=other_admin, is_published=True, is_active=True,
            assigned_to_all=False,  # Not assigned to teacher
        )
        other_mod = Module.objects.create(course=other_course, title="M", order=1, is_active=True)
        other_content = Content.objects.create(
            module=other_mod, title="C", content_type="TEXT", order=1,
            text_content="x", is_active=True,
        )
        response = self.teacher_client.post(
            f"/api/v1/teacher/progress/content/{other_content.id}/start/", HTTP_HOST=HOST
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ProgressUpdateTestCase(ProgressViewsBase):
    """Tests for PATCH /api/v1/teacher/progress/content/<id>/"""

    def test_unauthenticated_returns_401(self):
        response = APIClient().patch(
            f"/api/v1/teacher/progress/content/{self.content.id}/",
            {"progress_percentage": 50},
            HTTP_HOST=HOST,
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_progress_percentage(self):
        response = self.teacher_client.patch(
            f"/api/v1/teacher/progress/content/{self.content.id}/",
            {"progress_percentage": 50},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        prog = TeacherProgress.objects.get(teacher=self.teacher, content=self.content)
        self.assertEqual(float(prog.progress_percentage), 50.0)

    def test_update_invalid_percentage_returns_400(self):
        response = self.teacher_client.patch(
            f"/api/v1/teacher/progress/content/{self.content.id}/",
            {"progress_percentage": 150},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_negative_percentage_returns_400(self):
        response = self.teacher_client.patch(
            f"/api/v1/teacher/progress/content/{self.content.id}/",
            {"progress_percentage": -5},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_video_progress_seconds(self):
        video_content = Content.objects.create(
            module=self.module, title="Video", content_type="VIDEO",
            order=2, text_content="", duration=600, is_active=True,
        )
        response = self.teacher_client.patch(
            f"/api/v1/teacher/progress/content/{video_content.id}/",
            {"video_progress_seconds": 300},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        prog = TeacherProgress.objects.get(teacher=self.teacher, content=video_content)
        self.assertEqual(prog.video_progress_seconds, 300)

    def test_update_negative_video_seconds_returns_400(self):
        response = self.teacher_client.patch(
            f"/api/v1/teacher/progress/content/{self.content.id}/",
            {"video_progress_seconds": -1},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ProgressCompleteTestCase(ProgressViewsBase):
    """Tests for POST /api/v1/teacher/progress/content/<id>/complete/"""

    def test_unauthenticated_returns_401(self):
        response = APIClient().post(
            f"/api/v1/teacher/progress/content/{self.content.id}/complete/", HTTP_HOST=HOST
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_complete_text_content_returns_200(self):
        response = self.teacher_client.post(
            f"/api/v1/teacher/progress/content/{self.content.id}/complete/", HTTP_HOST=HOST
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_complete_marks_status_completed(self):
        self.teacher_client.post(
            f"/api/v1/teacher/progress/content/{self.content.id}/complete/", HTTP_HOST=HOST
        )
        prog = TeacherProgress.objects.get(teacher=self.teacher, content=self.content)
        self.assertEqual(prog.status, "COMPLETED")
        self.assertEqual(float(prog.progress_percentage), 100.0)

    def test_complete_nonexistent_content_returns_404(self):
        response = self.teacher_client.post(
            f"/api/v1/teacher/progress/content/{uuid.uuid4()}/complete/", HTTP_HOST=HOST
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class AssignmentListTestCase(ProgressViewsBase):
    """Tests for GET /api/v1/teacher/assignments/"""

    def setUp(self):
        super().setUp()
        self.assignment = Assignment.objects.create(
            tenant=self.tenant,
            course=self.course,
            title="Test Assignment",
            description="Do something",
            is_active=True,
        )

    def test_unauthenticated_returns_401(self):
        response = APIClient().get("/api/v1/teacher/assignments/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_teacher_can_list_assignments(self):
        response = self.teacher_client.get("/api/v1/teacher/assignments/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_assignments_list_includes_active_assignment(self):
        response = self.teacher_client.get("/api/v1/teacher/assignments/", HTTP_HOST=HOST)
        ids = [item["id"] for item in response.data]
        self.assertIn(str(self.assignment.id), ids)

    def test_filter_by_pending_status(self):
        response = self.teacher_client.get("/api/v1/teacher/assignments/?status=PENDING", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_filter_by_submitted_status(self):
        response = self.teacher_client.get("/api/v1/teacher/assignments/?status=SUBMITTED", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class AssignmentSubmitTestCase(ProgressViewsBase):
    """Tests for POST /api/v1/teacher/assignments/<id>/submit/"""

    def setUp(self):
        super().setUp()
        self.assignment = Assignment.objects.create(
            tenant=self.tenant, course=self.course, title="Submit Test",
            description="Submit me", is_active=True,
        )

    def test_unauthenticated_returns_401(self):
        response = APIClient().post(
            f"/api/v1/teacher/assignments/{self.assignment.id}/submit/",
            {"submission_text": "My answer"},
            HTTP_HOST=HOST,
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_teacher_can_submit_assignment(self):
        response = self.teacher_client.post(
            f"/api/v1/teacher/assignments/{self.assignment.id}/submit/",
            {"submission_text": "My submission text"},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_submit_creates_submission_record(self):
        from apps.progress.models import AssignmentSubmission
        self.teacher_client.post(
            f"/api/v1/teacher/assignments/{self.assignment.id}/submit/",
            {"submission_text": "Done!"},
            HTTP_HOST=HOST,
            format="json",
        )
        exists = AssignmentSubmission.objects.filter(
            assignment=self.assignment, teacher=self.teacher
        ).exists()
        self.assertTrue(exists)

    def test_submit_nonexistent_assignment_returns_404(self):
        response = self.teacher_client.post(
            f"/api/v1/teacher/assignments/{uuid.uuid4()}/submit/",
            {"submission_text": "test"},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_teacher_not_assigned_to_course_returns_403(self):
        other_admin = User.objects.create_user(
            email="oadm@test.com", password="pass", tenant=self.tenant,
            role="SCHOOL_ADMIN", is_active=True,
        )
        other_course = Course.objects.create(
            tenant=self.tenant, title="Other", slug="other-assgn", description="",
            created_by=other_admin, is_published=True, is_active=True, assigned_to_all=False,
        )
        other_assignment = Assignment.objects.create(
            tenant=self.tenant, course=other_course, title="Other",
            description="", is_active=True,
        )
        response = self.teacher_client.post(
            f"/api/v1/teacher/assignments/{other_assignment.id}/submit/",
            {"submission_text": "sneaky"},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class QuizFlowTestCase(ProgressViewsBase):
    """Tests for quiz_detail, quiz_start, quiz_submit endpoints."""

    def setUp(self):
        super().setUp()
        self.assignment = Assignment.objects.create(
            tenant=self.tenant, course=self.course, title="Quiz Assignment",
            description="Take the quiz", is_active=True,
        )
        self.quiz = Quiz.objects.create(
            tenant=self.tenant,
            assignment=self.assignment,
            max_attempts=3,
            time_limit_minutes=None,
        )
        self.question = QuizQuestion.objects.create(
            tenant=self.tenant,
            quiz=self.quiz,
            question_type="MCQ",
            prompt="What is 2+2?",
            options=["2", "3", "4", "5"],
            correct_answer={"option_index": 2},
            order=1,
            points=10,
        )

    def test_quiz_detail_unauthenticated_returns_401(self):
        response = APIClient().get(
            f"/api/v1/teacher/quizzes/{self.assignment.id}/", HTTP_HOST=HOST
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_quiz_detail_returns_200(self):
        response = self.teacher_client.get(
            f"/api/v1/teacher/quizzes/{self.assignment.id}/", HTTP_HOST=HOST
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("quiz_id", response.data)
        self.assertIn("questions", response.data)

    def test_quiz_detail_no_in_progress_attempt_without_start(self):
        response = self.teacher_client.get(
            f"/api/v1/teacher/quizzes/{self.assignment.id}/", HTTP_HOST=HOST
        )
        self.assertIsNone(response.data.get("current_attempt"))

    def test_quiz_start_creates_in_progress_attempt(self):
        response = self.teacher_client.post(
            f"/api/v1/teacher/quizzes/{self.assignment.id}/start/", HTTP_HOST=HOST
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data.get("current_attempt"))

    def test_quiz_start_idempotent(self):
        # Starting twice should not error
        self.teacher_client.post(
            f"/api/v1/teacher/quizzes/{self.assignment.id}/start/", HTTP_HOST=HOST
        )
        response = self.teacher_client.post(
            f"/api/v1/teacher/quizzes/{self.assignment.id}/start/", HTTP_HOST=HOST
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_quiz_submit_without_start_returns_400(self):
        response = self.teacher_client.post(
            f"/api/v1/teacher/quizzes/{self.assignment.id}/submit/",
            {"answers": {str(self.question.id): {"option_index": 2}}},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_quiz_full_flow_start_then_submit(self):
        # Start
        self.teacher_client.post(
            f"/api/v1/teacher/quizzes/{self.assignment.id}/start/", HTTP_HOST=HOST
        )
        # Submit
        response = self.teacher_client.post(
            f"/api/v1/teacher/quizzes/{self.assignment.id}/submit/",
            {"answers": {str(self.question.id): {"option_index": 2}}},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("score", response.data)

    def test_quiz_submit_correct_answer_gets_full_score(self):
        self.teacher_client.post(
            f"/api/v1/teacher/quizzes/{self.assignment.id}/start/", HTTP_HOST=HOST
        )
        response = self.teacher_client.post(
            f"/api/v1/teacher/quizzes/{self.assignment.id}/submit/",
            {"answers": {str(self.question.id): {"option_index": 2}}},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(float(response.data["score"]), 100.0)

    def test_quiz_submit_wrong_answer_gets_zero(self):
        self.teacher_client.post(
            f"/api/v1/teacher/quizzes/{self.assignment.id}/start/", HTTP_HOST=HOST
        )
        response = self.teacher_client.post(
            f"/api/v1/teacher/quizzes/{self.assignment.id}/submit/",
            {"answers": {str(self.question.id): {"option_index": 0}}},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(float(response.data["score"]), 0.0)

    def test_quiz_detail_no_quiz_on_assignment_returns_404(self):
        plain_assignment = Assignment.objects.create(
            tenant=self.tenant, course=self.course, title="Plain",
            description="no quiz", is_active=True,
        )
        response = self.teacher_client.get(
            f"/api/v1/teacher/quizzes/{plain_assignment.id}/", HTTP_HOST=HOST
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_quiz_not_assigned_to_course_returns_403(self):
        other_admin = User.objects.create_user(
            email="oadm3@test.com", password="pass", tenant=self.tenant,
            role="SCHOOL_ADMIN", is_active=True,
        )
        other_course = Course.objects.create(
            tenant=self.tenant, title="Other", slug="other-quiz", description="",
            created_by=other_admin, is_published=True, is_active=True, assigned_to_all=False,
        )
        other_assignment = Assignment.objects.create(
            tenant=self.tenant, course=other_course, title="Private",
            description="", is_active=True,
        )
        Quiz.objects.create(tenant=self.tenant, assignment=other_assignment, max_attempts=1)
        response = self.teacher_client.get(
            f"/api/v1/teacher/quizzes/{other_assignment.id}/", HTTP_HOST=HOST
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
