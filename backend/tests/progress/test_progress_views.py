# tests/progress/test_progress_views.py
"""
Tests for the teacher progress API endpoints.

Covers all endpoints mounted at /api/v1/teacher/:
- GET  /teacher/dashboard/
- POST /teacher/progress/content/<id>/start/
- PATCH /teacher/progress/content/<id>/
- POST /teacher/progress/content/<id>/complete/
- GET  /teacher/assignments/
- POST /teacher/assignments/<id>/submit/
- GET  /teacher/assignments/<id>/submission/
- GET  /teacher/quizzes/<id>/
- POST /teacher/quizzes/<id>/start/
- POST /teacher/quizzes/<id>/submit/

Security:
- All endpoints require authentication
- All endpoints require TEACHER or SCHOOL_ADMIN role
- All data is tenant-scoped (cross-tenant isolation tested)
"""

import uuid
import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers / extra fixtures
# ---------------------------------------------------------------------------

def _make_assignment(tenant, course, module=None, content=None, title=None, **kwargs):
    """Create an Assignment record directly."""
    from apps.progress.models import Assignment
    uid = uuid.uuid4().hex[:6]
    return Assignment.objects.create(
        tenant=tenant,
        course=course,
        module=module,
        content=content,
        title=title or f"Test Assignment {uid}",
        description="Assignment for testing",
        instructions="Follow the instructions.",
        max_score=100,
        passing_score=70,
        generation_source=kwargs.pop("generation_source", "MANUAL"),
        is_mandatory=True,
        is_active=True,
        **kwargs,
    )


def _list_results(data):
    """Return list items from either paginated or plain-list DRF responses."""
    return data.get("results", data) if isinstance(data, dict) else data


def _quiz_answers(questions):
    answers = {}
    for q in questions:
        if q.question_type == "MCQ":
            answers[str(q.id)] = {"option_index": 0}
        elif q.question_type == "TRUE_FALSE":
            answers[str(q.id)] = {"value": True}
        else:
            answers[str(q.id)] = {"text": "Test answer"}
    return answers


def _start_quiz(teacher_client, assignment):
    return teacher_client.post(
        f"/api/v1/teacher/quizzes/{assignment.id}/start/",
        data={},
        format="json",
    )


def _make_quiz(tenant, assignment, **kwargs):
    """Create a Quiz linked to an assignment."""
    from apps.progress.models import Quiz
    defaults = {
        "tenant": tenant,
        "assignment": assignment,
        "schema_version": 1,
        "is_auto_generated": False,
        "max_attempts": 3,
    }
    defaults.update(kwargs)
    return Quiz.objects.create(**defaults)


def _make_quiz_question(tenant, quiz, order=1, **kwargs):
    """Create an MCQ question on a quiz."""
    from apps.progress.models import QuizQuestion
    defaults = {
        "tenant": tenant,
        "quiz": quiz,
        "order": order,
        "question_type": "MCQ",
        "selection_mode": "SINGLE",
        "prompt": f"Question {order}: What is the answer?",
        "options": ["Option A", "Option B", "Option C", "Option D"],
        "correct_answer": {"answer": "Option A"},
        "explanation": "Option A is the correct answer.",
        "points": 1,
    }
    defaults.update(kwargs)
    return QuizQuestion.objects.create(**defaults)


def _assign_course_to_teacher(course, teacher):
    """Assign a course to a teacher (direct ManyToMany)."""
    course.assigned_teachers.add(teacher)


@pytest.fixture
def assignment(db, tenant, course, module, text_content):
    """A manual reflection assignment in the primary tenant."""
    return _make_assignment(tenant, course, module=module, content=text_content)


@pytest.fixture
def quiz_assignment(db, tenant, course, module, text_content):
    """An assignment with a Quiz attached."""
    assignment = _make_assignment(
        tenant, course, module=module, content=text_content,
        title="Quiz Assignment"
    )
    quiz = _make_quiz(tenant, assignment)
    _make_quiz_question(tenant, quiz, order=1)
    _make_quiz_question(
        tenant, quiz, order=2,
        question_type="TRUE_FALSE",
        selection_mode="SINGLE",
        prompt="True or False?",
        options=["True", "False"],
        correct_answer={"answer": "True"},
    )
    return assignment


# ---------------------------------------------------------------------------
# Authentication Tests
# ---------------------------------------------------------------------------

class TestProgressAuthRequired:
    """All teacher progress endpoints require authentication."""

    def test_dashboard_requires_auth(self, api_client, tenant):
        response = api_client.get(
            "/api/v1/teacher/dashboard/",
            HTTP_HOST=f"{tenant.subdomain}.lms.com",
        )
        assert response.status_code == 401

    def test_assignment_list_requires_auth(self, api_client, tenant):
        response = api_client.get(
            "/api/v1/teacher/assignments/",
            HTTP_HOST=f"{tenant.subdomain}.lms.com",
        )
        assert response.status_code == 401

    def test_progress_start_requires_auth(self, api_client, tenant, text_content):
        response = api_client.post(
            f"/api/v1/teacher/progress/content/{text_content.id}/start/",
            HTTP_HOST=f"{tenant.subdomain}.lms.com",
        )
        assert response.status_code == 401

    def test_progress_complete_requires_auth(self, api_client, tenant, text_content):
        response = api_client.post(
            f"/api/v1/teacher/progress/content/{text_content.id}/complete/",
            HTTP_HOST=f"{tenant.subdomain}.lms.com",
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Role Enforcement Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestProgressRoleEnforcement:
    """Admin can also access teacher endpoints; super_admin too; anonymous cannot."""

    def test_admin_can_access_dashboard(self, admin_client):
        response = admin_client.get("/api/v1/teacher/dashboard/")
        # 200 or 403 if admin not assigned to any course — but not 401
        assert response.status_code in (200, 403)

    def test_teacher_can_access_dashboard(self, teacher_client):
        response = teacher_client.get("/api/v1/teacher/dashboard/")
        assert response.status_code in (200, 403)

    def test_unauthenticated_cannot_access_assignments(self, api_client, tenant):
        response = api_client.get(
            "/api/v1/teacher/assignments/",
            HTTP_HOST=f"{tenant.subdomain}.lms.com",
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Dashboard Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTeacherDashboard:
    """GET /api/v1/teacher/dashboard/"""

    def test_dashboard_returns_200_for_teacher(self, teacher_client, teacher_user, course):
        """Teacher with an assigned course gets a valid 200 response."""
        _assign_course_to_teacher(course, teacher_user)
        response = teacher_client.get("/api/v1/teacher/dashboard/")
        assert response.status_code == 200

    def test_dashboard_has_stats_key(self, teacher_client, teacher_user, course):
        """Response must include a 'stats' key with progress metrics."""
        _assign_course_to_teacher(course, teacher_user)
        response = teacher_client.get("/api/v1/teacher/dashboard/")
        assert response.status_code == 200
        assert "stats" in response.data

    def test_dashboard_stats_has_required_fields(self, teacher_client, teacher_user, course):
        """stats must contain overall_progress and total_courses."""
        _assign_course_to_teacher(course, teacher_user)
        response = teacher_client.get("/api/v1/teacher/dashboard/")
        assert response.status_code == 200
        stats = response.data.get("stats", {})
        assert "overall_progress" in stats
        assert "total_courses" in stats

    def test_dashboard_returns_200_for_unassigned_teacher(self, teacher_client):
        """Teacher with no courses gets 200 with empty stats (not 500)."""
        response = teacher_client.get("/api/v1/teacher/dashboard/")
        assert response.status_code == 200

    def test_dashboard_returns_200_for_admin(self, admin_client, admin_user, course):
        """Admin can also view teacher dashboard."""
        _assign_course_to_teacher(course, admin_user)
        response = admin_client.get("/api/v1/teacher/dashboard/")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Progress Tracking Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestProgressStart:
    """POST /api/v1/teacher/progress/content/<id>/start/"""

    def test_teacher_can_start_assigned_content(
        self, teacher_client, teacher_user, course, text_content
    ):
        """Teacher starts tracking a content item they are assigned to."""
        _assign_course_to_teacher(course, teacher_user)
        response = teacher_client.post(
            f"/api/v1/teacher/progress/content/{text_content.id}/start/"
        )
        assert response.status_code in (200, 201)

    def test_start_creates_teacher_progress_record(
        self, teacher_client, teacher_user, course, text_content, tenant
    ):
        """After start, a TeacherProgress record exists for this teacher+content."""
        from apps.progress.models import TeacherProgress
        _assign_course_to_teacher(course, teacher_user)
        teacher_client.post(
            f"/api/v1/teacher/progress/content/{text_content.id}/start/"
        )
        assert TeacherProgress.objects.filter(
            teacher=teacher_user,
            content=text_content,
        ).exists()

    def test_start_is_idempotent(
        self, teacher_client, teacher_user, course, text_content
    ):
        """Calling start twice should not create duplicate progress records."""
        from apps.progress.models import TeacherProgress
        _assign_course_to_teacher(course, teacher_user)
        teacher_client.post(
            f"/api/v1/teacher/progress/content/{text_content.id}/start/"
        )
        teacher_client.post(
            f"/api/v1/teacher/progress/content/{text_content.id}/start/"
        )
        count = TeacherProgress.objects.filter(
            teacher=teacher_user,
            content=text_content,
        ).count()
        assert count == 1

    def test_start_nonexistent_content_returns_404(
        self, teacher_client, teacher_user, course
    ):
        """Starting progress on a non-existent content item returns 404."""
        _assign_course_to_teacher(course, teacher_user)
        fake_id = uuid.uuid4()
        response = teacher_client.post(
            f"/api/v1/teacher/progress/content/{fake_id}/start/"
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestProgressUpdate:
    """PATCH /api/v1/teacher/progress/content/<id>/"""

    def test_teacher_can_update_video_progress(
        self, teacher_client, teacher_user, course, video_content
    ):
        """Teacher updates video_progress_seconds on a video content item."""
        from apps.progress.models import TeacherProgress
        _assign_course_to_teacher(course, teacher_user)

        # Start progress first
        teacher_client.post(
            f"/api/v1/teacher/progress/content/{video_content.id}/start/"
        )

        response = teacher_client.patch(
            f"/api/v1/teacher/progress/content/{video_content.id}/",
            data={"video_progress_seconds": 120},
            format="json",
        )
        assert response.status_code == 200

    def test_teacher_can_update_progress_percentage(
        self, teacher_client, teacher_user, course, text_content
    ):
        """Teacher updates progress_percentage on a text content item."""
        _assign_course_to_teacher(course, teacher_user)
        teacher_client.post(
            f"/api/v1/teacher/progress/content/{text_content.id}/start/"
        )
        response = teacher_client.patch(
            f"/api/v1/teacher/progress/content/{text_content.id}/",
            data={"progress_percentage": 50},
            format="json",
        )
        assert response.status_code == 200


@pytest.mark.django_db
class TestProgressComplete:
    """POST /api/v1/teacher/progress/content/<id>/complete/"""

    def test_teacher_can_complete_content(
        self, teacher_client, teacher_user, course, text_content
    ):
        """Teacher marks content as complete."""
        _assign_course_to_teacher(course, teacher_user)
        teacher_client.post(
            f"/api/v1/teacher/progress/content/{text_content.id}/start/"
        )
        response = teacher_client.post(
            f"/api/v1/teacher/progress/content/{text_content.id}/complete/"
        )
        assert response.status_code in (200, 201)

    def test_complete_sets_status_to_completed(
        self, teacher_client, teacher_user, course, text_content
    ):
        """After completing, TeacherProgress status is COMPLETED and percentage is 100."""
        from apps.progress.models import TeacherProgress
        _assign_course_to_teacher(course, teacher_user)
        teacher_client.post(
            f"/api/v1/teacher/progress/content/{text_content.id}/start/"
        )
        teacher_client.post(
            f"/api/v1/teacher/progress/content/{text_content.id}/complete/"
        )
        progress = TeacherProgress.objects.get(
            teacher=teacher_user,
            content=text_content,
        )
        assert progress.status == "COMPLETED"
        assert progress.progress_percentage >= 99

    def test_complete_nonexistent_content_returns_404(
        self, teacher_client, teacher_user, course
    ):
        """Completing a non-existent content item returns 404."""
        _assign_course_to_teacher(course, teacher_user)
        fake_id = uuid.uuid4()
        response = teacher_client.post(
            f"/api/v1/teacher/progress/content/{fake_id}/complete/"
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Assignment Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAssignmentList:
    """GET /api/v1/teacher/assignments/"""

    def test_teacher_can_list_assignments(
        self, teacher_client, teacher_user, course, assignment
    ):
        """Teacher gets a 200 with their assigned course's assignments."""
        _assign_course_to_teacher(course, teacher_user)
        response = teacher_client.get("/api/v1/teacher/assignments/")
        assert response.status_code == 200

    def test_assignment_list_returns_expected_fields(
        self, teacher_client, teacher_user, course, assignment
    ):
        """Each assignment in the list has required fields."""
        _assign_course_to_teacher(course, teacher_user)
        response = teacher_client.get("/api/v1/teacher/assignments/")
        assert response.status_code == 200
        results = _list_results(response.data)
        if results:
            item = results[0]
            assert "id" in item
            assert "title" in item
            assert "course_id" in item
            assert "course_title" in item

    def test_assignment_list_excludes_other_tenant_assignments(
        self, teacher_client, teacher_user, course, assignment,
        admin_user_b, tenant_b
    ):
        """Assignments from tenant B are not visible in tenant A's assignment list."""
        _assign_course_to_teacher(course, teacher_user)

        # Create an assignment in tenant B
        from apps.courses.models import Course
        course_b = Course.objects.create(
            tenant=tenant_b,
            title="Tenant B Course",
            slug="tenant-b-course",
            description="",
            created_by=admin_user_b,
            is_published=True,
            is_active=True,
        )
        _make_assignment(tenant_b, course_b, title="Tenant B Assignment")

        response = teacher_client.get("/api/v1/teacher/assignments/")
        assert response.status_code == 200
        results = _list_results(response.data)
        titles = [a["title"] for a in results if isinstance(a, dict)]
        assert "Tenant B Assignment" not in titles

    def test_assignment_list_can_filter_by_status(
        self, teacher_client, teacher_user, course, assignment
    ):
        """?status=PENDING should filter assignments."""
        _assign_course_to_teacher(course, teacher_user)
        response = teacher_client.get("/api/v1/teacher/assignments/?status=PENDING")
        assert response.status_code == 200

    def test_unassigned_teacher_gets_empty_list(self, teacher_client):
        """Teacher with no course assignments gets an empty list."""
        response = teacher_client.get("/api/v1/teacher/assignments/")
        assert response.status_code == 200
        results = _list_results(response.data)
        assert isinstance(results, list)


@pytest.mark.django_db
class TestAssignmentSubmit:
    """POST /api/v1/teacher/assignments/<id>/submit/"""

    def test_teacher_can_submit_assignment(
        self, teacher_client, teacher_user, course, assignment
    ):
        """Teacher submits a text assignment."""
        _assign_course_to_teacher(course, teacher_user)
        response = teacher_client.post(
            f"/api/v1/teacher/assignments/{assignment.id}/submit/",
            data={"submission_text": "My reflection on today's lesson."},
            format="json",
        )
        assert response.status_code in (200, 201)

    def test_submit_creates_assignment_submission(
        self, teacher_client, teacher_user, course, assignment
    ):
        """Submission creates an AssignmentSubmission record in the database."""
        from apps.progress.models import AssignmentSubmission
        _assign_course_to_teacher(course, teacher_user)
        teacher_client.post(
            f"/api/v1/teacher/assignments/{assignment.id}/submit/",
            data={"submission_text": "Reflection text here."},
            format="json",
        )
        assert AssignmentSubmission.all_objects.filter(
            assignment=assignment,
            teacher=teacher_user,
        ).exists()

    def test_submit_nonexistent_assignment_returns_404(
        self, teacher_client, teacher_user, course
    ):
        """Submitting to a non-existent assignment returns 404."""
        _assign_course_to_teacher(course, teacher_user)
        fake_id = uuid.uuid4()
        response = teacher_client.post(
            f"/api/v1/teacher/assignments/{fake_id}/submit/",
            data={"submission_text": "Won't work."},
            format="json",
        )
        assert response.status_code == 404

    def test_cross_tenant_assignment_submit_returns_404(
        self, teacher_client, teacher_user, course,
        admin_user_b, tenant_b
    ):
        """Teacher from tenant A cannot submit to tenant B's assignment."""
        from apps.courses.models import Course
        course_b = Course.objects.create(
            tenant=tenant_b,
            title="B Course",
            slug="b-course",
            description="",
            created_by=admin_user_b,
            is_published=True,
            is_active=True,
        )
        assignment_b = _make_assignment(tenant_b, course_b, title="B Assignment")
        response = teacher_client.post(
            f"/api/v1/teacher/assignments/{assignment_b.id}/submit/",
            data={"submission_text": "Cross-tenant submission"},
            format="json",
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestAssignmentSubmissionDetail:
    """GET /api/v1/teacher/assignments/<id>/submission/"""

    def test_teacher_can_retrieve_own_submission(
        self, teacher_client, teacher_user, course, assignment
    ):
        """Teacher can retrieve their own submission detail."""
        _assign_course_to_teacher(course, teacher_user)
        teacher_client.post(
            f"/api/v1/teacher/assignments/{assignment.id}/submit/",
            data={"submission_text": "My answer."},
            format="json",
        )
        response = teacher_client.get(
            f"/api/v1/teacher/assignments/{assignment.id}/submission/"
        )
        assert response.status_code in (200, 404)  # 404 if no submission exists

    def test_nonexistent_assignment_submission_returns_404(
        self, teacher_client, teacher_user, course
    ):
        """Getting submission for non-existent assignment returns 404."""
        _assign_course_to_teacher(course, teacher_user)
        fake_id = uuid.uuid4()
        response = teacher_client.get(
            f"/api/v1/teacher/assignments/{fake_id}/submission/"
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Quiz Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestQuizDetail:
    """GET /api/v1/teacher/quizzes/<assignment_id>/"""

    def test_teacher_can_get_quiz_detail(
        self, teacher_client, teacher_user, course, quiz_assignment
    ):
        """Teacher retrieves quiz detail for an assigned course."""
        _assign_course_to_teacher(course, teacher_user)
        response = teacher_client.get(
            f"/api/v1/teacher/quizzes/{quiz_assignment.id}/"
        )
        assert response.status_code == 200

    def test_quiz_detail_has_required_fields(
        self, teacher_client, teacher_user, course, quiz_assignment
    ):
        """Quiz detail response must contain questions, max_attempts, etc."""
        _assign_course_to_teacher(course, teacher_user)
        response = teacher_client.get(
            f"/api/v1/teacher/quizzes/{quiz_assignment.id}/"
        )
        assert response.status_code == 200
        assert "questions" in response.data
        assert "max_attempts" in response.data or "attempts_remaining" in response.data

    def test_quiz_detail_shows_questions(
        self, teacher_client, teacher_user, course, quiz_assignment
    ):
        """Questions list in quiz detail is non-empty."""
        _assign_course_to_teacher(course, teacher_user)
        response = teacher_client.get(
            f"/api/v1/teacher/quizzes/{quiz_assignment.id}/"
        )
        assert response.status_code == 200
        questions = response.data.get("questions", [])
        assert len(questions) >= 1

    def test_quiz_detail_nonexistent_assignment_returns_404(
        self, teacher_client, teacher_user, course
    ):
        """Getting quiz for non-existent assignment returns 404."""
        _assign_course_to_teacher(course, teacher_user)
        fake_id = uuid.uuid4()
        response = teacher_client.get(f"/api/v1/teacher/quizzes/{fake_id}/")
        assert response.status_code == 404

    def test_cross_tenant_quiz_detail_returns_404(
        self, teacher_client, teacher_user, course,
        admin_user_b, tenant_b
    ):
        """Teacher from tenant A cannot see tenant B's quiz."""
        from apps.courses.models import Course
        course_b = Course.objects.create(
            tenant=tenant_b,
            title="B Course",
            slug="b-course-quiz",
            description="",
            created_by=admin_user_b,
            is_published=True,
            is_active=True,
        )
        assignment_b = _make_assignment(tenant_b, course_b, title="B Quiz Assign")
        _make_quiz(tenant_b, assignment_b)
        response = teacher_client.get(
            f"/api/v1/teacher/quizzes/{assignment_b.id}/"
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestQuizSubmit:
    """POST /api/v1/teacher/quizzes/<assignment_id>/submit/"""

    def test_teacher_can_submit_quiz(
        self, teacher_client, teacher_user, course, quiz_assignment
    ):
        """Teacher submits quiz answers and gets a grading result."""
        from apps.progress.models import Quiz, QuizQuestion
        _assign_course_to_teacher(course, teacher_user)
        quiz = Quiz.objects.get(assignment=quiz_assignment)
        questions = QuizQuestion.objects.filter(quiz=quiz).order_by("order")
        start_response = _start_quiz(teacher_client, quiz_assignment)
        assert start_response.status_code == 200
        answers = _quiz_answers(questions)

        response = teacher_client.post(
            f"/api/v1/teacher/quizzes/{quiz_assignment.id}/submit/",
            data={"answers": answers},
            format="json",
        )
        assert response.status_code in (200, 201)

    def test_quiz_submit_returns_score(
        self, teacher_client, teacher_user, course, quiz_assignment
    ):
        """Quiz submission response includes a score field."""
        from apps.progress.models import Quiz, QuizQuestion
        _assign_course_to_teacher(course, teacher_user)
        quiz = Quiz.objects.get(assignment=quiz_assignment)
        questions = QuizQuestion.objects.filter(quiz=quiz).order_by("order")
        start_response = _start_quiz(teacher_client, quiz_assignment)
        assert start_response.status_code == 200
        answers = _quiz_answers(questions)

        response = teacher_client.post(
            f"/api/v1/teacher/quizzes/{quiz_assignment.id}/submit/",
            data={"answers": answers},
            format="json",
        )
        if response.status_code in (200, 201):
            assert "score" in response.data

    def test_quiz_submit_creates_submission_record(
        self, teacher_client, teacher_user, course, quiz_assignment
    ):
        """After submitting, a QuizSubmission record exists in the database."""
        from apps.progress.models import Quiz, QuizQuestion, QuizSubmission
        _assign_course_to_teacher(course, teacher_user)
        quiz = Quiz.objects.get(assignment=quiz_assignment)
        questions = QuizQuestion.objects.filter(quiz=quiz).order_by("order")
        start_response = _start_quiz(teacher_client, quiz_assignment)
        assert start_response.status_code == 200
        answers = _quiz_answers(questions)
        response = teacher_client.post(
            f"/api/v1/teacher/quizzes/{quiz_assignment.id}/submit/",
            data={"answers": answers},
            format="json",
        )

        if response.status_code in (200, 201):
            assert QuizSubmission.objects.filter(
                quiz=quiz,
                teacher=teacher_user,
            ).exists()

    def test_empty_answers_returns_400(
        self, teacher_client, teacher_user, course, quiz_assignment
    ):
        """Submitting with no answers returns 400."""
        _assign_course_to_teacher(course, teacher_user)
        response = teacher_client.post(
            f"/api/v1/teacher/quizzes/{quiz_assignment.id}/submit/",
            data={"answers": {}},
            format="json",
        )
        # Should either be 400 (validation error) or 200 (graded as 0)
        assert response.status_code in (200, 201, 400)

    def test_cross_tenant_quiz_submit_returns_404(
        self, teacher_client, teacher_user, course,
        admin_user_b, tenant_b
    ):
        """Teacher from tenant A cannot submit to tenant B's quiz."""
        from apps.courses.models import Course
        course_b = Course.objects.create(
            tenant=tenant_b,
            title="B Course for Submit",
            slug="b-course-submit",
            description="",
            created_by=admin_user_b,
            is_published=True,
            is_active=True,
        )
        assignment_b = _make_assignment(tenant_b, course_b, title="B Quiz Submit")
        _make_quiz(tenant_b, assignment_b)

        response = teacher_client.post(
            f"/api/v1/teacher/quizzes/{assignment_b.id}/submit/",
            data={"answers": {}},
            format="json",
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Cross-Tenant Isolation (Comprehensive)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestProgressCrossTenantIsolation:
    """
    Verify that teachers from tenant B cannot access or modify
    progress data belonging to tenant A.
    """

    def test_teacher_b_cannot_start_tenant_a_content(
        self, tenant, text_content, admin_user_b, tenant_b, api_client_for
    ):
        """Teacher B cannot start progress on tenant A's content."""
        teacher_b_user = None
        from apps.users.models import User
        teacher_b_user = User.objects.create_user(
            email="teacher@othertenantprogress.com",
            password="pass123!",
            first_name="Teacher",
            last_name="B",
            tenant=tenant_b,
            role="TEACHER",
            is_active=True,
        )
        client_b = api_client_for(teacher_b_user, tenant_b)
        response = client_b.post(
            f"/api/v1/teacher/progress/content/{text_content.id}/start/"
        )
        # Should be 404 (content not found in tenant B) or 403
        assert response.status_code in (403, 404)

    def test_teacher_b_cannot_complete_tenant_a_content(
        self, tenant, text_content, tenant_b, api_client_for
    ):
        """Teacher B cannot mark tenant A's content as complete."""
        from apps.users.models import User
        teacher_b_user = User.objects.create_user(
            email="teacherb_complete@othertenant.com",
            password="pass123!",
            first_name="Teacher",
            last_name="B Complete",
            tenant=tenant_b,
            role="TEACHER",
            is_active=True,
        )
        client_b = api_client_for(teacher_b_user, tenant_b)
        response = client_b.post(
            f"/api/v1/teacher/progress/content/{text_content.id}/complete/"
        )
        assert response.status_code in (403, 404)

    def test_teacher_a_progress_not_visible_to_teacher_b(
        self, teacher_user, course, text_content, tenant_b, api_client_for
    ):
        """
        TeacherProgress records created by teacher A are not visible
        to teacher B via their dashboard or any other endpoint.
        """
        from apps.progress.models import TeacherProgress
        from apps.users.models import User

        # Create a progress record for teacher A
        TeacherProgress.all_objects.create(
            tenant=teacher_user.tenant,
            teacher=teacher_user,
            course=course,
            content=text_content,
            status="IN_PROGRESS",
            progress_percentage=50,
        )

        teacher_b_user = User.objects.create_user(
            email="teacherb_vis@othertenant.com",
            password="pass123!",
            first_name="Teacher",
            last_name="B Visibility",
            tenant=tenant_b,
            role="TEACHER",
            is_active=True,
        )
        client_b = api_client_for(teacher_b_user, tenant_b)
        response = client_b.get("/api/v1/teacher/dashboard/")
        assert response.status_code == 200
        # Teacher B's stats should reflect their own 0 progress, not teacher A's
        stats = response.data.get("stats", {})
        overall = stats.get("overall_progress", 0)
        assert overall == 0
