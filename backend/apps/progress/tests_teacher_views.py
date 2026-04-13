# apps/progress/tests_teacher_views.py
#
# Tests for teacher-facing progress endpoints:
#   - Dashboard, calendar, gamification, search
#   - Progress start / update / complete
#   - Assignment list, submit, submission detail
#   - Quiz detail and submit (edge cases not covered by tests_quiz_api.py)
#   - Auth guards and tenant isolation

import uuid
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.courses.models import Content, Course, Module
from apps.progress.models import (
    Assignment,
    AssignmentSubmission,
    Quiz,
    QuizQuestion,
    QuizSubmission,
    TeacherProgress,
)
from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Shared setup
# ---------------------------------------------------------------------------

HOST = "test.lms.com"


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class TeacherViewsTestBase(TestCase):
    """
    Common fixtures shared by all teacher-view test classes.

    Creates:
      - tenant (subdomain="test")
      - admin (SCHOOL_ADMIN)
      - teacher (TEACHER)
      - course (published, assigned_to_all)
      - module + two contents (TEXT, one mandatory)
      - assignment + quiz + question
    """

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Teacher Views School",
            slug="tv-school",
            subdomain="test",
            email="tv@test.com",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            email="admin@tv.test",
            password="pass123",
            first_name="Admin",
            last_name="TV",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@tv.test",
            password="pass123",
            first_name="Teacher",
            last_name="TV",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )
        self.course = Course.objects.create(
            tenant=self.tenant,
            title="Progress Course",
            slug="progress-course",
            description="x",
            created_by=self.admin,
            is_published=True,
            is_active=True,
            assigned_to_all=True,
            deadline=timezone.localdate() + timedelta(days=7),
        )
        self.module = Module.objects.create(
            course=self.course,
            title="Module 1",
            description="",
            order=1,
            is_active=True,
        )
        self.content1 = Content.objects.create(
            module=self.module,
            title="Lesson 1",
            content_type="TEXT",
            order=1,
            text_content="<p>Hello</p>",
            is_mandatory=True,
            is_active=True,
        )
        self.content2 = Content.objects.create(
            module=self.module,
            title="Lesson 2",
            content_type="TEXT",
            order=2,
            text_content="<p>World</p>",
            is_mandatory=True,
            is_active=True,
        )
        self.assignment = Assignment.objects.create(
            tenant=self.tenant,
            course=self.course,
            module=self.module,
            content=self.content1,
            title="Test Assignment",
            description="Submit your work.",
            instructions="Write 200 words.",
            due_date=timezone.now() + timedelta(days=3),
            generation_source="MANUAL",
            is_active=True,
        )

    def _auth_teacher(self):
        self.client.force_authenticate(user=self.teacher)

    def _auth_admin(self):
        self.client.force_authenticate(user=self.admin)

    def _get(self, url, **kw):
        return self.client.get(url, HTTP_HOST=HOST, **kw)

    def _post(self, url, data=None, **kw):
        return self.client.post(url, data, format="json", HTTP_HOST=HOST, **kw)

    def _patch(self, url, data=None, **kw):
        return self.client.patch(url, data, format="json", HTTP_HOST=HOST, **kw)


# ===========================================================================
# 1. Authentication guards
# ===========================================================================


class TeacherViewsAuthTestCase(TeacherViewsTestBase):
    """All teacher endpoints must reject unauthenticated requests."""

    def test_dashboard_requires_auth(self):
        resp = self._get("/api/teacher/dashboard/")
        self.assertEqual(resp.status_code, 401)

    def test_calendar_requires_auth(self):
        resp = self._get("/api/teacher/calendar/")
        self.assertEqual(resp.status_code, 401)

    def test_gamification_requires_auth(self):
        resp = self._get("/api/teacher/gamification/summary/")
        self.assertEqual(resp.status_code, 401)

    def test_search_requires_auth(self):
        resp = self._get("/api/teacher/search/?q=test")
        self.assertEqual(resp.status_code, 401)

    def test_progress_start_requires_auth(self):
        resp = self._post(f"/api/teacher/progress/content/{self.content1.id}/start/")
        self.assertEqual(resp.status_code, 401)

    def test_assignments_list_requires_auth(self):
        resp = self._get("/api/teacher/assignments/")
        self.assertEqual(resp.status_code, 401)


# ===========================================================================
# 2. Dashboard endpoint
# ===========================================================================


class TeacherDashboardTestCase(TeacherViewsTestBase):
    """Tests for GET /api/teacher/dashboard/."""

    def setUp(self):
        super().setUp()
        self._auth_teacher()

    def test_dashboard_returns_200(self):
        resp = self._get("/api/teacher/dashboard/")
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_contains_expected_keys(self):
        resp = self._get("/api/teacher/dashboard/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("stats", data)
        self.assertIn("continue_learning", data)
        self.assertIn("deadlines", data)

    def test_dashboard_stats_include_counts(self):
        resp = self._get("/api/teacher/dashboard/")
        stats = resp.json()["stats"]
        self.assertIn("overall_progress", stats)
        self.assertIn("total_courses", stats)
        self.assertIn("completed_courses", stats)
        self.assertIn("pending_assignments", stats)

    def test_dashboard_total_courses_matches_assigned(self):
        resp = self._get("/api/teacher/dashboard/")
        stats = resp.json()["stats"]
        self.assertEqual(stats["total_courses"], 1)

    def test_dashboard_pending_assignments_count(self):
        resp = self._get("/api/teacher/dashboard/")
        stats = resp.json()["stats"]
        self.assertEqual(stats["pending_assignments"], 1)

    def test_dashboard_continue_learning_null_when_no_progress(self):
        resp = self._get("/api/teacher/dashboard/")
        self.assertIsNone(resp.json()["continue_learning"])

    def test_dashboard_continue_learning_populated_after_starting(self):
        TeacherProgress.objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            course=self.course,
            content=self.content1,
            status="IN_PROGRESS",
            started_at=timezone.now(),
        )
        resp = self._get("/api/teacher/dashboard/")
        cl = resp.json()["continue_learning"]
        self.assertIsNotNone(cl)
        self.assertEqual(cl["course_id"], str(self.course.id))
        self.assertEqual(cl["content_id"], str(self.content1.id))

    def test_dashboard_deadlines_include_course_deadline(self):
        resp = self._get("/api/teacher/dashboard/")
        deadlines = resp.json()["deadlines"]
        course_deadlines = [d for d in deadlines if d["type"] == "course"]
        self.assertTrue(len(course_deadlines) >= 1)

    def test_dashboard_deadlines_include_assignment_deadline(self):
        resp = self._get("/api/teacher/dashboard/")
        deadlines = resp.json()["deadlines"]
        assignment_deadlines = [d for d in deadlines if d["type"] == "assignment"]
        self.assertTrue(len(assignment_deadlines) >= 1)


# ===========================================================================
# 3. Progress start / complete / update
# ===========================================================================


class ProgressStartCompleteTestCase(TeacherViewsTestBase):
    """Tests for progress start, update, and complete endpoints."""

    def setUp(self):
        super().setUp()
        self._auth_teacher()

    def test_start_content_creates_progress(self):
        resp = self._post(f"/api/teacher/progress/content/{self.content1.id}/start/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "IN_PROGRESS")
        self.assertIsNotNone(data["started_at"])

    def test_start_same_content_twice_is_idempotent(self):
        self._post(f"/api/teacher/progress/content/{self.content1.id}/start/")
        resp = self._post(f"/api/teacher/progress/content/{self.content1.id}/start/")
        self.assertEqual(resp.status_code, 200)

    def test_complete_content_sets_status(self):
        resp = self._post(f"/api/teacher/progress/content/{self.content1.id}/complete/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "COMPLETED")
        self.assertEqual(float(data["progress_percentage"]), 100.0)

    def test_complete_nonexistent_content_returns_404(self):
        fake_id = uuid.uuid4()
        resp = self._post(f"/api/teacher/progress/content/{fake_id}/complete/")
        self.assertEqual(resp.status_code, 404)

    def test_update_progress_percentage(self):
        self._post(f"/api/teacher/progress/content/{self.content1.id}/start/")
        resp = self._patch(
            f"/api/teacher/progress/content/{self.content1.id}/",
            {"progress_percentage": 50.0},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(float(resp.json()["progress_percentage"]), 50.0)

    def test_update_invalid_percentage_returns_400(self):
        self._post(f"/api/teacher/progress/content/{self.content1.id}/start/")
        resp = self._patch(
            f"/api/teacher/progress/content/{self.content1.id}/",
            {"progress_percentage": 150.0},
        )
        self.assertEqual(resp.status_code, 400)

    def test_update_negative_percentage_returns_400(self):
        self._post(f"/api/teacher/progress/content/{self.content1.id}/start/")
        resp = self._patch(
            f"/api/teacher/progress/content/{self.content1.id}/",
            {"progress_percentage": -10.0},
        )
        self.assertEqual(resp.status_code, 400)

    def test_update_video_seconds_negative_returns_400(self):
        self._post(f"/api/teacher/progress/content/{self.content1.id}/start/")
        resp = self._patch(
            f"/api/teacher/progress/content/{self.content1.id}/",
            {"video_progress_seconds": -5},
        )
        self.assertEqual(resp.status_code, 400)

    def test_update_video_seconds_non_integer_returns_400(self):
        self._post(f"/api/teacher/progress/content/{self.content1.id}/start/")
        resp = self._patch(
            f"/api/teacher/progress/content/{self.content1.id}/",
            {"video_progress_seconds": "abc"},
        )
        self.assertEqual(resp.status_code, 400)


# ===========================================================================
# 4. Assignment list + submit
# ===========================================================================


class AssignmentListSubmitTestCase(TeacherViewsTestBase):
    """Tests for assignment list and submit endpoints."""

    def setUp(self):
        super().setUp()
        self._auth_teacher()

    def test_assignment_list_returns_200(self):
        resp = self._get("/api/teacher/assignments/")
        self.assertEqual(resp.status_code, 200)

    def test_assignment_list_includes_assignment(self):
        resp = self._get("/api/teacher/assignments/")
        ids = [str(a["id"]) for a in resp.json()]
        self.assertIn(str(self.assignment.id), ids)

    def test_assignment_list_contains_expected_fields(self):
        resp = self._get("/api/teacher/assignments/")
        data = resp.json()
        self.assertTrue(len(data) >= 1)
        item = data[0]
        for field in ("id", "title", "submission_status", "is_quiz"):
            self.assertIn(field, item, msg=f"Missing field: {field}")

    def test_assignment_list_status_filter_pending(self):
        resp = self._get("/api/teacher/assignments/?status=PENDING")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for item in data:
            self.assertEqual(item["submission_status"], "PENDING")

    def test_assignment_submit_creates_submission(self):
        resp = self._post(
            f"/api/teacher/assignments/{self.assignment.id}/submit/",
            {"submission_text": "My answer."},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "SUBMITTED")
        self.assertEqual(data["submission_text"], "My answer.")

    def test_assignment_submit_nonexistent_returns_404(self):
        resp = self._post(
            f"/api/teacher/assignments/{uuid.uuid4()}/submit/",
            {"submission_text": "x"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_assignment_submission_detail(self):
        AssignmentSubmission.objects.create(
            tenant=self.tenant,
            assignment=self.assignment,
            teacher=self.teacher,
            submission_text="Earlier submission.",
            status="SUBMITTED",
        )
        resp = self._get(f"/api/teacher/assignments/{self.assignment.id}/submission/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["submission_text"], "Earlier submission.")

    def test_assignment_submission_detail_before_submit_returns_404(self):
        resp = self._get(f"/api/teacher/assignments/{self.assignment.id}/submission/")
        self.assertEqual(resp.status_code, 404)

    def test_assignment_resubmit_updates_existing(self):
        """Submitting twice updates the existing record."""
        self._post(
            f"/api/teacher/assignments/{self.assignment.id}/submit/",
            {"submission_text": "First attempt."},
        )
        resp = self._post(
            f"/api/teacher/assignments/{self.assignment.id}/submit/",
            {"submission_text": "Second attempt."},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["submission_text"], "Second attempt.")
        # Only one submission record
        count = AssignmentSubmission.all_objects.filter(
            assignment=self.assignment, teacher=self.teacher
        ).count()
        self.assertEqual(count, 1)


# ===========================================================================
# 5. Quiz submit edge cases
# ===========================================================================


class QuizSubmitEdgeCasesTestCase(TeacherViewsTestBase):
    """Edge-case tests for quiz submission validation."""

    def setUp(self):
        super().setUp()
        self.quiz = Quiz.objects.create(
            tenant=self.tenant,
            assignment=self.assignment,
            is_auto_generated=False,
        )
        self.q1 = QuizQuestion.objects.create(
            tenant=self.tenant,
            quiz=self.quiz,
            order=1,
            question_type="MCQ",
            selection_mode="SINGLE",
            prompt="Pick one",
            options=["A", "B", "C"],
            correct_answer={"option_index": 0},
            points=1,
        )
        self._auth_teacher()

    def test_quiz_submit_invalid_answers_type_returns_400(self):
        resp = self._post(
            f"/api/teacher/quizzes/{self.assignment.id}/submit/",
            {"answers": "not a dict"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_quiz_submit_nested_objects_returns_400(self):
        resp = self._post(
            f"/api/teacher/quizzes/{self.assignment.id}/submit/",
            {"answers": {str(self.q1.id): {"option_index": {"nested": True}}}},
        )
        self.assertEqual(resp.status_code, 400)

    def test_quiz_submit_non_option_indices_array_returns_400(self):
        resp = self._post(
            f"/api/teacher/quizzes/{self.assignment.id}/submit/",
            {"answers": {str(self.q1.id): {"custom_list": [1, 2, 3]}}},
        )
        self.assertEqual(resp.status_code, 400)

    def test_quiz_submit_correct_answer_scores_points(self):
        resp = self._post(
            f"/api/teacher/quizzes/{self.assignment.id}/submit/",
            {"answers": {str(self.q1.id): {"option_index": 0}}},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["score"], 1.0)
        self.assertIsNotNone(data["graded_at"])

    def test_quiz_submit_wrong_answer_scores_zero(self):
        resp = self._post(
            f"/api/teacher/quizzes/{self.assignment.id}/submit/",
            {"answers": {str(self.q1.id): {"option_index": 2}}},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["score"], 0.0)

    def test_quiz_detail_returns_questions_without_correct_answer(self):
        resp = self._get(f"/api/teacher/quizzes/{self.assignment.id}/")
        self.assertEqual(resp.status_code, 200)
        questions = resp.json()["questions"]
        self.assertEqual(len(questions), 1)
        # Must NOT expose correct_answer
        self.assertNotIn("correct_answer", questions[0])

    def test_quiz_detail_nonexistent_assignment_returns_404(self):
        resp = self._get(f"/api/teacher/quizzes/{uuid.uuid4()}/")
        self.assertEqual(resp.status_code, 404)

    def test_quiz_detail_assignment_without_quiz_returns_404(self):
        # Create a non-quiz assignment
        plain_assignment = Assignment.objects.create(
            tenant=self.tenant,
            course=self.course,
            module=self.module,
            title="Plain Assignment",
            description="No quiz",
            generation_source="MANUAL",
            is_active=True,
        )
        resp = self._get(f"/api/teacher/quizzes/{plain_assignment.id}/")
        self.assertEqual(resp.status_code, 404)


# ===========================================================================
# 6. Teacher search
# ===========================================================================


class TeacherSearchTestCase(TeacherViewsTestBase):
    """Tests for GET /api/teacher/search/."""

    def setUp(self):
        super().setUp()
        self._auth_teacher()

    def test_search_requires_min_2_chars(self):
        resp = self._get("/api/teacher/search/?q=x")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["courses"], [])
        self.assertEqual(data["assignments"], [])

    def test_search_empty_query_returns_empty(self):
        resp = self._get("/api/teacher/search/?q=")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["courses"], [])

    def test_search_matches_course_title(self):
        resp = self._get("/api/teacher/search/?q=Progress")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(len(data["courses"]) >= 1)
        self.assertEqual(data["courses"][0]["title"], "Progress Course")

    def test_search_matches_assignment_title(self):
        resp = self._get("/api/teacher/search/?q=Test+Assignment")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(len(data["assignments"]) >= 1)

    def test_search_no_match_returns_empty(self):
        resp = self._get("/api/teacher/search/?q=ZzzNonexistent")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["courses"]), 0)
        self.assertEqual(len(data["assignments"]), 0)


# ===========================================================================
# 7. Calendar endpoint
# ===========================================================================


class TeacherCalendarTestCase(TeacherViewsTestBase):
    """Tests for GET /api/teacher/calendar/."""

    def setUp(self):
        super().setUp()
        self._auth_teacher()

    def test_calendar_returns_200(self):
        resp = self._get("/api/teacher/calendar/")
        self.assertEqual(resp.status_code, 200)

    def test_calendar_custom_days_param(self):
        resp = self._get("/api/teacher/calendar/?days=3")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["window"]["days"], 3)
        self.assertEqual(len(data["days"]), 3)

    def test_calendar_invalid_days_defaults_to_5(self):
        resp = self._get("/api/teacher/calendar/?days=abc")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["window"]["days"], 5)


# ===========================================================================
# 8. Cross-tenant isolation
# ===========================================================================


@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
)
class ProgressCrossTenantTestCase(TestCase):
    """
    A teacher from tenant B must not be able to start/complete content
    belonging to tenant A.
    """

    def setUp(self):
        self.client = APIClient()
        self.tenant_a = Tenant.objects.create(
            name="School A", slug="xiso-a", subdomain="testa", email="a@a.com", is_active=True
        )
        self.tenant_b = Tenant.objects.create(
            name="School B", slug="xiso-b", subdomain="testb", email="b@b.com", is_active=True
        )
        admin_a = User.objects.create_user(
            email="admin@a.test", password="pass123",
            first_name="Admin", last_name="A",
            tenant=self.tenant_a, role="SCHOOL_ADMIN", is_active=True,
        )
        self.teacher_b = User.objects.create_user(
            email="teacher@b.test", password="pass123",
            first_name="Teacher", last_name="B",
            tenant=self.tenant_b, role="TEACHER", is_active=True,
        )
        course_a = Course.objects.create(
            tenant=self.tenant_a, title="A's Course", slug="a-course",
            description="x", created_by=admin_a,
            is_published=True, is_active=True, assigned_to_all=True,
        )
        module_a = Module.objects.create(
            course=course_a, title="M", description="", order=1, is_active=True,
        )
        self.content_a = Content.objects.create(
            module=module_a, title="L", content_type="TEXT", order=1,
            text_content="x", is_active=True,
        )
        self.client.force_authenticate(user=self.teacher_b)

    def test_teacher_b_cannot_start_tenant_a_content(self):
        resp = self.client.post(
            f"/api/teacher/progress/content/{self.content_a.id}/start/",
            HTTP_HOST="testb.lms.com",
        )
        # Should be 404 (tenant filter) or 403 (not assigned)
        self.assertIn(resp.status_code, [403, 404])

    def test_teacher_b_cannot_complete_tenant_a_content(self):
        resp = self.client.post(
            f"/api/teacher/progress/content/{self.content_a.id}/complete/",
            HTTP_HOST="testb.lms.com",
        )
        self.assertIn(resp.status_code, [403, 404])
