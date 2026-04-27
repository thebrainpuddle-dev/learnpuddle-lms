"""
Tests for the progress app models.

Covers:
- TeacherProgress: creation, str(), unique_together constraint, progress_percentage range
- Assignment: creation, soft-delete, generation_source choices, defaults
- Quiz: OneToOne link to Assignment, defaults
- QuizQuestion: creation, question_type choices
- QuizSubmission: creation, unique_together constraint
- AssignmentSubmission: creation, status choices
"""

import pytest
from django.db import IntegrityError
from django.utils import timezone

pytestmark = pytest.mark.django_db


# ─────────────────────────────────────────────────────────────
# Helpers / fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def teacher_user2(db, tenant):
    """A second TEACHER user on the primary tenant (for isolation tests)."""
    from apps.users.models import User
    return User.objects.create_user(
        email="teacher2@testschool.com",
        password="TeacherPass2!123",
        first_name="Teacher",
        last_name="Two",
        tenant=tenant,
        role="TEACHER",
        is_active=True,
    )


@pytest.fixture
def assignment(db, tenant, course, module, text_content):
    """A manual assignment linked to a content item."""
    from apps.progress.models import Assignment
    return Assignment.objects.create(
        tenant=tenant,
        course=course,
        module=module,
        content=text_content,
        title="Test Reflection Assignment",
        description="Reflect on the lesson.",
        instructions="Write 150–300 words.",
        max_score=100,
        passing_score=70,
        generation_source="MANUAL",
        is_mandatory=True,
        is_active=True,
    )


@pytest.fixture
def quiz(db, tenant, assignment):
    """A Quiz linked to an assignment."""
    from apps.progress.models import Quiz
    return Quiz.objects.create(
        tenant=tenant,
        assignment=assignment,
        schema_version=1,
        is_auto_generated=False,
        generation_model="",
        max_attempts=3,
    )


# ─────────────────────────────────────────────────────────────
# TeacherProgress
# ─────────────────────────────────────────────────────────────

class TestTeacherProgressModel:
    def test_create_progress(self, tenant, teacher_user, course, text_content):
        from apps.progress.models import TeacherProgress
        progress = TeacherProgress.all_objects.create(
            tenant=tenant,
            teacher=teacher_user,
            course=course,
            content=text_content,
            status="IN_PROGRESS",
            progress_percentage=50,
            video_progress_seconds=120,
        )
        assert progress.pk is not None
        assert progress.status == "IN_PROGRESS"
        assert progress.progress_percentage == 50
        assert progress.video_progress_seconds == 120

    def test_str_representation(self, tenant, teacher_user, course, text_content):
        from apps.progress.models import TeacherProgress
        progress = TeacherProgress.all_objects.create(
            tenant=tenant,
            teacher=teacher_user,
            course=course,
            content=text_content,
            status="COMPLETED",
        )
        expected = f"{teacher_user.email} - {course.title} - COMPLETED"
        assert str(progress) == expected

    def test_default_status_is_not_started(self, tenant, teacher_user, course):
        from apps.progress.models import TeacherProgress
        progress = TeacherProgress.all_objects.create(
            tenant=tenant,
            teacher=teacher_user,
            course=course,
        )
        assert progress.status == "NOT_STARTED"
        assert progress.progress_percentage == 0
        assert progress.video_progress_seconds == 0

    def test_unique_together_teacher_course_content(self, tenant, teacher_user, course, text_content):
        """Duplicate (teacher, course, content) rows must be rejected."""
        from apps.progress.models import TeacherProgress
        TeacherProgress.all_objects.create(
            tenant=tenant,
            teacher=teacher_user,
            course=course,
            content=text_content,
        )
        with pytest.raises(IntegrityError):
            TeacherProgress.all_objects.create(
                tenant=tenant,
                teacher=teacher_user,
                course=course,
                content=text_content,
            )

    def test_course_level_progress_no_content(self, tenant, teacher_user, course):
        """A course-level progress record (content=None) is allowed."""
        from apps.progress.models import TeacherProgress
        progress = TeacherProgress.all_objects.create(
            tenant=tenant,
            teacher=teacher_user,
            course=course,
            content=None,
        )
        assert progress.content is None

    def test_all_status_choices(self, tenant, teacher_user, course):
        """All three status choices are valid."""
        from apps.progress.models import TeacherProgress
        valid_statuses = ["NOT_STARTED", "IN_PROGRESS", "COMPLETED"]
        for i, status in enumerate(valid_statuses):
            # Create a unique record per status by varying content (None + index trick)
            progress = TeacherProgress.all_objects.create(
                tenant=tenant,
                teacher=teacher_user,
                course=course,
                content=None,
                status=status,
            )
            assert progress.status == status
            # Clean up so unique_together doesn't conflict for next iteration
            progress.delete()

    def test_completed_at_can_be_set(self, tenant, teacher_user, course):
        from apps.progress.models import TeacherProgress
        now = timezone.now()
        progress = TeacherProgress.all_objects.create(
            tenant=tenant,
            teacher=teacher_user,
            course=course,
            status="COMPLETED",
            completed_at=now,
            progress_percentage=100,
        )
        assert progress.completed_at is not None


# ─────────────────────────────────────────────────────────────
# Assignment
# ─────────────────────────────────────────────────────────────

class TestAssignmentModel:
    def test_create_manual_assignment(self, assignment):
        assert assignment.pk is not None
        assert assignment.generation_source == "MANUAL"
        assert assignment.is_active is True
        assert assignment.is_mandatory is True

    def test_str_representation(self, assignment, course):
        expected = f"{course.title} - {assignment.title}"
        assert str(assignment) == expected

    def test_default_max_score_and_passing_score(self, tenant, course, module):
        from apps.progress.models import Assignment
        a = Assignment.objects.create(
            tenant=tenant,
            course=course,
            module=module,
            title="Defaults Test",
            description="desc",
        )
        assert float(a.max_score) == 100.0
        assert float(a.passing_score) == 70.0

    def test_generation_source_video_auto(self, tenant, course, module, text_content):
        from apps.progress.models import Assignment
        a = Assignment.objects.create(
            tenant=tenant,
            course=course,
            module=module,
            content=text_content,
            title="Auto Quiz",
            description="desc",
            generation_source="VIDEO_AUTO",
            generation_metadata={"video_asset_id": "abc-123", "type": "quiz"},
        )
        assert a.generation_source == "VIDEO_AUTO"
        assert a.generation_metadata["type"] == "quiz"

    def test_soft_delete_sets_is_deleted(self, assignment):
        """SoftDeleteMixin.delete() marks is_deleted=True (soft delete)."""
        assignment.delete()
        assignment.refresh_from_db()
        assert assignment.is_deleted is True
        assert assignment.deleted_at is not None

    def test_soft_deleted_excluded_from_default_manager(self, assignment):
        """Default manager should not return soft-deleted records."""
        from apps.progress.models import Assignment
        assignment.delete()
        assert not Assignment.objects.filter(pk=assignment.pk).exists()

    def test_due_date_optional(self, tenant, course, module):
        from apps.progress.models import Assignment
        a = Assignment.objects.create(
            tenant=tenant,
            course=course,
            module=module,
            title="No Due Date",
            description="desc",
        )
        assert a.due_date is None

    def test_generation_metadata_defaults_empty(self, tenant, course, module):
        from apps.progress.models import Assignment
        a = Assignment.objects.create(
            tenant=tenant,
            course=course,
            module=module,
            title="Meta test",
            description="desc",
        )
        assert a.generation_metadata == {}


# ─────────────────────────────────────────────────────────────
# Quiz
# ─────────────────────────────────────────────────────────────

class TestQuizModel:
    def test_create_quiz(self, quiz, assignment):
        assert quiz.pk is not None
        assert quiz.assignment == assignment
        assert quiz.schema_version == 1
        assert quiz.is_auto_generated is False

    def test_str_representation(self, quiz):
        """str() should not crash (basic smoke test)."""
        assert str(quiz) is not None

    def test_max_attempts_default(self, tenant, assignment):
        from apps.progress.models import Quiz
        q = Quiz.objects.create(
            tenant=tenant,
            assignment=assignment,
        )
        # Default max_attempts = 1 (from model)
        assert q.max_attempts == 1

    def test_time_limit_optional(self, quiz):
        assert quiz.time_limit_minutes is None

    def test_quiz_is_one_to_one_with_assignment(self, quiz, assignment):
        """A second Quiz on the same assignment must raise IntegrityError."""
        from apps.progress.models import Quiz
        with pytest.raises(IntegrityError):
            Quiz.objects.create(
                assignment=assignment,
            )

    def test_auto_generated_flag(self, tenant, assignment):
        from apps.progress.models import Quiz
        # Need a fresh assignment for this
        from apps.progress.models import Assignment
        new_assignment = Assignment.objects.create(
            tenant=tenant,
            course=assignment.course,
            module=assignment.module,
            title="Auto Quiz Test",
            description="desc",
            generation_source="VIDEO_AUTO",
        )
        q = Quiz.objects.create(
            tenant=tenant,
            assignment=new_assignment,
            is_auto_generated=True,
            generation_model="gpt-4o-mini",
        )
        assert q.is_auto_generated is True
        assert q.generation_model == "gpt-4o-mini"


# ─────────────────────────────────────────────────────────────
# QuizQuestion
# ─────────────────────────────────────────────────────────────

class TestQuizQuestionModel:
    def _make_question(self, tenant, quiz, question_type="MCQ", order=1, **kwargs):
        from apps.progress.models import QuizQuestion
        defaults = {
            "tenant": tenant,
            "quiz": quiz,
            "order": order,
            "question_type": question_type,
            "selection_mode": "SINGLE",
            "prompt": f"What is the answer? (Q{order})",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct_answer": {"answer": "Option A"},
            "explanation": "Option A is correct because…",
            "points": 1,
        }
        defaults.update(kwargs)
        return QuizQuestion.objects.create(**defaults)

    def test_create_mcq(self, tenant, quiz):
        q = self._make_question(tenant, quiz, "MCQ")
        assert q.pk is not None
        assert q.question_type == "MCQ"
        assert q.selection_mode == "SINGLE"

    def test_create_true_false(self, tenant, quiz):
        q = self._make_question(
            tenant, quiz, "TRUE_FALSE", order=2,
            options=["True", "False"],
            correct_answer={"answer": "True"},
        )
        assert q.question_type == "TRUE_FALSE"

    def test_create_short_answer(self, tenant, quiz):
        q = self._make_question(
            tenant, quiz, "SHORT_ANSWER", order=3,
            options=[],
            correct_answer={},
        )
        assert q.question_type == "SHORT_ANSWER"
        assert q.options == []

    def test_default_points(self, tenant, quiz):
        from apps.progress.models import QuizQuestion
        q = QuizQuestion.objects.create(
            tenant=tenant,
            quiz=quiz,
            order=4,
            question_type="MCQ",
            prompt="Default points question",
        )
        assert q.points == 1

    def test_questions_ordered(self, tenant, quiz):
        """Quiz.questions should be retrievable in order."""
        for i in range(1, 4):
            self._make_question(tenant, quiz, "MCQ", order=i)
        questions = quiz.questions.order_by("order")
        orders = list(questions.values_list("order", flat=True))
        assert orders == [1, 2, 3]


# ─────────────────────────────────────────────────────────────
# QuizSubmission
# ─────────────────────────────────────────────────────────────

class TestQuizSubmissionModel:
    def test_create_submission(self, tenant, quiz, teacher_user):
        from apps.progress.models import QuizSubmission
        sub = QuizSubmission.objects.create(
            tenant=tenant,
            quiz=quiz,
            teacher=teacher_user,
            attempt_number=1,
            answers={"q1": "Option A"},
            score=85,
            graded_at=timezone.now(),
        )
        assert sub.pk is not None
        assert sub.attempt_number == 1
        assert float(sub.score) == 85.0

    def test_unique_together_quiz_teacher_attempt(self, tenant, quiz, teacher_user):
        """Duplicate (quiz, teacher, attempt_number) must be rejected."""
        from apps.progress.models import QuizSubmission
        QuizSubmission.objects.create(
            tenant=tenant,
            quiz=quiz,
            teacher=teacher_user,
            attempt_number=1,
        )
        with pytest.raises(IntegrityError):
            QuizSubmission.objects.create(
                tenant=tenant,
                quiz=quiz,
                teacher=teacher_user,
                attempt_number=1,
            )

    def test_multiple_attempts_allowed(self, tenant, quiz, teacher_user):
        """Different attempt numbers on same (quiz, teacher) are allowed."""
        from apps.progress.models import QuizSubmission
        s1 = QuizSubmission.objects.create(
            tenant=tenant, quiz=quiz, teacher=teacher_user, attempt_number=1,
        )
        s2 = QuizSubmission.objects.create(
            tenant=tenant, quiz=quiz, teacher=teacher_user, attempt_number=2,
        )
        assert s1.pk != s2.pk

    def test_time_expired_default_false(self, tenant, quiz, teacher_user):
        from apps.progress.models import QuizSubmission
        sub = QuizSubmission.objects.create(
            tenant=tenant, quiz=quiz, teacher=teacher_user, attempt_number=1,
        )
        assert sub.time_expired is False

    def test_score_nullable(self, tenant, quiz, teacher_user):
        """score=None (ungraded) is valid."""
        from apps.progress.models import QuizSubmission
        sub = QuizSubmission.objects.create(
            tenant=tenant, quiz=quiz, teacher=teacher_user, attempt_number=1, score=None,
        )
        assert sub.score is None


# ─────────────────────────────────────────────────────────────
# AssignmentSubmission
# ─────────────────────────────────────────────────────────────

class TestAssignmentSubmissionModel:
    def test_create_submission(self, tenant, assignment, teacher_user):
        from apps.progress.models import AssignmentSubmission
        sub = AssignmentSubmission.objects.create(
            tenant=tenant,
            assignment=assignment,
            teacher=teacher_user,
            submission_text="Here is my reflection.",
            status="SUBMITTED",
        )
        assert sub.pk is not None
        assert sub.status == "SUBMITTED"

    def test_default_status_pending(self, tenant, assignment, teacher_user):
        from apps.progress.models import AssignmentSubmission
        sub = AssignmentSubmission.objects.create(
            tenant=tenant,
            assignment=assignment,
            teacher=teacher_user,
        )
        assert sub.status == "PENDING"

    def test_unique_together_assignment_teacher(self, tenant, assignment, teacher_user):
        """One submission per (assignment, teacher)."""
        from apps.progress.models import AssignmentSubmission
        AssignmentSubmission.objects.create(
            tenant=tenant,
            assignment=assignment,
            teacher=teacher_user,
        )
        with pytest.raises(IntegrityError):
            AssignmentSubmission.objects.create(
                tenant=tenant,
                assignment=assignment,
                teacher=teacher_user,
            )

    def test_grading_workflow(self, tenant, assignment, teacher_user, admin_user):
        """Grade a submission: set score, feedback, graded_by, status=GRADED."""
        from apps.progress.models import AssignmentSubmission
        sub = AssignmentSubmission.objects.create(
            tenant=tenant,
            assignment=assignment,
            teacher=teacher_user,
            submission_text="Reflection text here.",
            status="SUBMITTED",
        )
        sub.score = 88
        sub.feedback = "Excellent work!"
        sub.graded_by = admin_user
        sub.graded_at = timezone.now()
        sub.status = "GRADED"
        sub.save()
        sub.refresh_from_db()
        assert float(sub.score) == 88.0
        assert sub.status == "GRADED"
        assert sub.graded_by == admin_user

    def test_file_url_optional(self, tenant, assignment, teacher_user):
        from apps.progress.models import AssignmentSubmission
        sub = AssignmentSubmission.objects.create(
            tenant=tenant,
            assignment=assignment,
            teacher=teacher_user,
        )
        assert sub.file_url in (None, "")

    def test_two_teachers_can_submit_same_assignment(
        self, tenant, assignment, teacher_user, teacher_user2
    ):
        """Two different teachers may each submit once."""
        from apps.progress.models import AssignmentSubmission
        s1 = AssignmentSubmission.objects.create(
            tenant=tenant, assignment=assignment, teacher=teacher_user,
        )
        s2 = AssignmentSubmission.objects.create(
            tenant=tenant, assignment=assignment, teacher=teacher_user2,
        )
        assert s1.pk != s2.pk
