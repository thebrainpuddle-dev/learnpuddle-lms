"""
Unit tests for ``apps.progress.quiz_helpers``.

The quiz helpers module was extracted in TASK-013 (M1/M2/M3 fixes) to
consolidate attempt lifecycle logic shared between teacher and student views.
These tests exercise each helper in isolation (no HTTP layer) to pin the
behaviour and catch regressions.

Coverage:
- ``validate_answers_payload`` — pure validation, no DB required
- ``grade_quiz_answers`` — auto-grading logic for MCQ / TRUE_FALSE / SHORT_ANSWER
- ``get_in_progress_attempt`` — read-only DB lookup
- ``start_quiz_attempt`` — full attempt lifecycle (create, resume, expiry, race-safety)
- ``serialize_attempt`` — pure serialisation, no DB required
- ``_is_expired`` — time-limit helper
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.progress.quiz_helpers import (
    _is_expired,
    get_in_progress_attempt,
    grade_quiz_answers,
    serialize_attempt,
    start_quiz_attempt,
    validate_answers_payload,
)
from apps.progress.models import (
    Assignment,
    Quiz,
    QuizQuestion,
    QuizSubmission,
)
from apps.courses.models import Content, Course, Module
from apps.users.models import User

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def quiz_course(tenant, admin_user, teacher_user):
    return Course.objects.create(
        tenant=tenant,
        title="Helper Quiz Course",
        slug=f"helper-quiz-course-{uuid.uuid4().hex[:6]}",
        description="For quiz_helpers unit tests",
        created_by=admin_user,
        is_published=True,
        is_active=True,
        assigned_to_all=True,
    )


@pytest.fixture
def quiz_module(quiz_course):
    return Module.objects.create(
        course=quiz_course,
        title="Module 1",
        description="",
        order=1,
        is_active=True,
    )


@pytest.fixture
def quiz_content(quiz_module):
    return Content.objects.create(
        module=quiz_module,
        title="Video",
        content_type="VIDEO",
        order=1,
        file_url="",
        file_size=1,
        duration=120,
        text_content="",
        is_mandatory=True,
        is_active=True,
    )


@pytest.fixture
def quiz_assignment(tenant, quiz_course, quiz_module, quiz_content):
    return Assignment.objects.create(
        tenant=tenant,
        course=quiz_course,
        module=quiz_module,
        content=quiz_content,
        title="Helper Quiz Assignment",
        description="Quiz for helper unit tests",
        generation_source="MANUAL",
    )


@pytest.fixture
def basic_quiz(tenant, quiz_assignment):
    """A Quiz with max_attempts=3 and no time limit."""
    return Quiz.objects.create(
        tenant=tenant,
        assignment=quiz_assignment,
        max_attempts=3,
        time_limit_minutes=None,
    )


@pytest.fixture
def timed_quiz(tenant, quiz_assignment):
    """A Quiz with a 10-minute time limit, max_attempts=3."""
    return Quiz.objects.create(
        tenant=tenant,
        assignment=quiz_assignment,
        max_attempts=3,
        time_limit_minutes=10,
    )


@pytest.fixture
def quiz_with_questions(basic_quiz, tenant):
    """A Quiz populated with one of each question type.

    QuizQuestion uses ``prompt`` (not ``question_text``) — see models.py.
    """
    QuizQuestion.objects.create(
        quiz=basic_quiz,
        tenant=tenant,
        order=1,
        prompt="What is 2+2?",
        question_type="MCQ",
        selection_mode="SINGLE",
        options=["3", "4", "5"],
        correct_answer={"option_index": 1},  # "4"
        points=2,
    )
    QuizQuestion.objects.create(
        quiz=basic_quiz,
        tenant=tenant,
        order=2,
        prompt="Select all prime numbers.",
        question_type="MCQ",
        selection_mode="MULTIPLE",
        options=["1", "2", "3", "4"],
        correct_answer={"option_indices": [1, 2]},  # "2" and "3"
        points=3,
    )
    QuizQuestion.objects.create(
        quiz=basic_quiz,
        tenant=tenant,
        order=3,
        prompt="Is the sky blue?",
        question_type="TRUE_FALSE",
        options=[],
        correct_answer={"value": True},
        points=1,
    )
    QuizQuestion.objects.create(
        quiz=basic_quiz,
        tenant=tenant,
        order=4,
        prompt="Explain photosynthesis.",
        question_type="SHORT_ANSWER",
        options=[],
        correct_answer={},
        points=5,
    )
    return basic_quiz


# ---------------------------------------------------------------------------
# 1. validate_answers_payload — pure function, no DB
# ---------------------------------------------------------------------------


class TestValidateAnswersPayload:
    """validate_answers_payload returns None on OK input, str on error."""

    def test_valid_simple_dict_returns_none(self):
        answers = {
            "q1": {"option_index": 0},
            "q2": {"value": True},
        }
        assert validate_answers_payload(answers) is None

    def test_non_dict_top_level_returns_error(self):
        error = validate_answers_payload([1, 2, 3])
        assert error is not None
        assert "object" in error

    def test_too_many_answers_returns_error(self):
        # 201 answers exceeds the limit of 200
        answers = {str(i): {"option_index": 0} for i in range(201)}
        error = validate_answers_payload(answers)
        assert error is not None
        assert "200" in error

    def test_exactly_200_answers_allowed(self):
        answers = {str(i): {"option_index": 0} for i in range(200)}
        assert validate_answers_payload(answers) is None

    def test_non_dict_answer_value_returns_error(self):
        answers = {"q1": "not_a_dict"}
        error = validate_answers_payload(answers)
        assert error is not None
        assert "object" in error

    def test_nested_object_in_answer_returns_error(self):
        answers = {"q1": {"option": {"nested": True}}}
        error = validate_answers_payload(answers)
        assert error is not None
        assert "nested" in error.lower()

    def test_option_indices_list_is_allowed(self):
        answers = {"q1": {"option_indices": [0, 2]}}
        assert validate_answers_payload(answers) is None

    def test_nested_list_for_non_option_indices_returns_error(self):
        answers = {"q1": {"other_key": [1, 2]}}
        error = validate_answers_payload(answers)
        assert error is not None

    def test_option_indices_with_nested_list_items_returns_error(self):
        answers = {"q1": {"option_indices": [[0, 1]]}}
        error = validate_answers_payload(answers)
        assert error is not None

    def test_empty_dict_is_valid(self):
        assert validate_answers_payload({}) is None

    def test_none_returns_error(self):
        error = validate_answers_payload(None)
        assert error is not None


# ---------------------------------------------------------------------------
# 2. grade_quiz_answers — needs DB (quiz model with questions)
# ---------------------------------------------------------------------------


class TestGradeQuizAnswers:
    """Auto-grading for MCQ / TRUE_FALSE / SHORT_ANSWER."""

    def test_correct_single_mcq_earns_full_points(self, quiz_with_questions):
        q = quiz_with_questions.questions.get(question_type="MCQ", selection_mode="SINGLE")
        answers = {str(q.id): {"option_index": 1}}
        score, has_sa = grade_quiz_answers(quiz_with_questions, answers)
        assert float(score) == 2.0
        assert has_sa is True  # SHORT_ANSWER question exists

    def test_wrong_single_mcq_earns_zero(self, quiz_with_questions):
        q = quiz_with_questions.questions.get(question_type="MCQ", selection_mode="SINGLE")
        answers = {str(q.id): {"option_index": 0}}  # wrong answer
        score, _ = grade_quiz_answers(quiz_with_questions, answers)
        assert float(score) == 0.0

    def test_correct_multi_mcq_earns_full_points(self, quiz_with_questions):
        q = quiz_with_questions.questions.get(question_type="MCQ", selection_mode="MULTIPLE")
        answers = {str(q.id): {"option_indices": [1, 2]}}
        score, _ = grade_quiz_answers(quiz_with_questions, answers)
        assert float(score) == 3.0

    def test_partial_multi_mcq_earns_zero(self, quiz_with_questions):
        """Multi-select MCQ requires exact match — partial gets 0."""
        q = quiz_with_questions.questions.get(question_type="MCQ", selection_mode="MULTIPLE")
        answers = {str(q.id): {"option_indices": [1]}}  # only one of two correct
        score, _ = grade_quiz_answers(quiz_with_questions, answers)
        assert float(score) == 0.0

    def test_true_false_correct_earns_points(self, quiz_with_questions):
        q = quiz_with_questions.questions.get(question_type="TRUE_FALSE")
        answers = {str(q.id): {"value": True}}
        score, _ = grade_quiz_answers(quiz_with_questions, answers)
        assert float(score) == 1.0

    def test_true_false_wrong_earns_zero(self, quiz_with_questions):
        q = quiz_with_questions.questions.get(question_type="TRUE_FALSE")
        answers = {str(q.id): {"value": False}}
        score, _ = grade_quiz_answers(quiz_with_questions, answers)
        assert float(score) == 0.0

    def test_short_answer_detected_but_not_scored(self, quiz_with_questions):
        """SHORT_ANSWER questions are not auto-graded — only detected."""
        q = quiz_with_questions.questions.get(question_type="SHORT_ANSWER")
        answers = {str(q.id): {"text": "Photosynthesis is..."}}
        score, has_sa = grade_quiz_answers(quiz_with_questions, answers)
        # Score comes from other objective questions only; SHORT_ANSWER
        # contributes nothing to the auto-score.
        assert has_sa is True
        # The short answer alone doesn't affect score.
        only_sa_answers = {str(q.id): {"text": "answer"}}
        sa_score, _ = grade_quiz_answers(quiz_with_questions, only_sa_answers)
        assert float(sa_score) == 0.0

    def test_all_correct_answers_scores_max(self, quiz_with_questions):
        """Answering all objective questions correctly returns 2+3+1=6."""
        sq = quiz_with_questions.questions.get(question_type="MCQ", selection_mode="SINGLE")
        mq = quiz_with_questions.questions.get(question_type="MCQ", selection_mode="MULTIPLE")
        tfq = quiz_with_questions.questions.get(question_type="TRUE_FALSE")
        answers = {
            str(sq.id): {"option_index": 1},
            str(mq.id): {"option_indices": [1, 2]},
            str(tfq.id): {"value": True},
        }
        score, _ = grade_quiz_answers(quiz_with_questions, answers)
        assert float(score) == 6.0

    def test_empty_answers_scores_zero(self, quiz_with_questions):
        score, has_sa = grade_quiz_answers(quiz_with_questions, {})
        assert float(score) == 0.0
        assert has_sa is True


# ---------------------------------------------------------------------------
# 3. serialize_attempt — pure function, no DB
# ---------------------------------------------------------------------------


class TestSerializeAttempt:
    """serialize_attempt converts a QuizSubmission instance to a dict."""

    def _make_stub_submission(self, **overrides):
        """Build a minimal stub object (not a real DB row)."""
        class _Stub:
            attempt_number = 1
            score = None
            graded_at = None
            submitted_at = None
            time_expired = False

        stub = _Stub()
        for k, v in overrides.items():
            setattr(stub, k, v)
        return stub

    def test_in_progress_attempt_serialized(self):
        sub = self._make_stub_submission(attempt_number=1, score=None)
        data = serialize_attempt(sub)
        assert data["attempt_number"] == 1
        assert data["score"] is None
        assert data["time_expired"] is False

    def test_completed_attempt_serialized(self):
        now = timezone.now()
        sub = self._make_stub_submission(
            attempt_number=2,
            score=85,
            graded_at=now,
            submitted_at=now,
            time_expired=False,
        )
        data = serialize_attempt(sub)
        assert data["attempt_number"] == 2
        assert float(data["score"]) == 85.0
        assert data["graded_at"] == now
        assert data["submitted_at"] == now

    def test_time_expired_reflected(self):
        sub = self._make_stub_submission(
            attempt_number=1, score=0, time_expired=True
        )
        data = serialize_attempt(sub)
        assert data["time_expired"] is True
        assert float(data["score"]) == 0.0


# ---------------------------------------------------------------------------
# 4. _is_expired — pure time check helper
# ---------------------------------------------------------------------------


class TestIsExpired:
    """_is_expired checks whether an in-progress attempt's time limit elapsed."""

    def _make_quiz_stub(self, time_limit_minutes):
        class _Quiz:
            pass
        q = _Quiz()
        q.time_limit_minutes = time_limit_minutes
        return q

    def _make_attempt_stub(self, started_minutes_ago):
        class _Attempt:
            pass
        a = _Attempt()
        a.started_at = timezone.now() - timedelta(minutes=started_minutes_ago)
        return a

    def test_no_time_limit_never_expires(self):
        quiz = self._make_quiz_stub(None)
        attempt = self._make_attempt_stub(9999)
        assert _is_expired(attempt, quiz) is False

    def test_within_time_limit_not_expired(self):
        quiz = self._make_quiz_stub(10)
        attempt = self._make_attempt_stub(9)
        assert _is_expired(attempt, quiz) is False

    def test_beyond_time_limit_expired(self):
        quiz = self._make_quiz_stub(10)
        attempt = self._make_attempt_stub(11)
        assert _is_expired(attempt, quiz) is True

    def test_zero_minutes_elapsed_not_expired(self):
        quiz = self._make_quiz_stub(10)
        attempt = self._make_attempt_stub(0)
        assert _is_expired(attempt, quiz) is False

    def test_no_started_at_not_expired(self):
        quiz = self._make_quiz_stub(10)

        class _Attempt:
            started_at = None

        assert _is_expired(_Attempt(), quiz) is False


# ---------------------------------------------------------------------------
# 5. get_in_progress_attempt — DB lookup
# ---------------------------------------------------------------------------


class TestGetInProgressAttempt:
    """get_in_progress_attempt fetches the current in-progress row (score IS NULL)."""

    def test_returns_none_when_no_attempts(self, basic_quiz, teacher_user):
        result = get_in_progress_attempt(basic_quiz, teacher_user)
        assert result is None

    def test_returns_in_progress_row(self, basic_quiz, teacher_user, tenant):
        sub = QuizSubmission.all_objects.create(
            quiz=basic_quiz,
            teacher=teacher_user,
            tenant=tenant,
            attempt_number=1,
            answers={},
            started_at=timezone.now(),
        )
        result = get_in_progress_attempt(basic_quiz, teacher_user)
        assert result is not None
        assert result.id == sub.id

    def test_returns_none_when_only_completed_attempts(
        self, basic_quiz, teacher_user, tenant
    ):
        QuizSubmission.all_objects.create(
            quiz=basic_quiz,
            teacher=teacher_user,
            tenant=tenant,
            attempt_number=1,
            answers={},
            score=75.0,
            started_at=timezone.now(),
        )
        result = get_in_progress_attempt(basic_quiz, teacher_user)
        assert result is None

    def test_returns_latest_in_progress_when_multiple(
        self, basic_quiz, teacher_user, tenant
    ):
        """Should return the highest attempt_number in-progress row."""
        QuizSubmission.all_objects.create(
            quiz=basic_quiz, teacher=teacher_user, tenant=tenant,
            attempt_number=1, answers={}, score=60.0, started_at=timezone.now(),
        )
        sub2 = QuizSubmission.all_objects.create(
            quiz=basic_quiz, teacher=teacher_user, tenant=tenant,
            attempt_number=2, answers={}, started_at=timezone.now(),
        )
        result = get_in_progress_attempt(basic_quiz, teacher_user)
        assert result.id == sub2.id


# ---------------------------------------------------------------------------
# 6. start_quiz_attempt — full lifecycle
# ---------------------------------------------------------------------------


class TestStartQuizAttempt:
    """start_quiz_attempt covers create, resume, stale-close, exhaustion."""

    def test_creates_first_attempt(self, basic_quiz, teacher_user, tenant):
        sub, err = start_quiz_attempt(basic_quiz, teacher_user, tenant)
        assert err is None
        assert sub is not None
        assert sub.attempt_number == 1
        assert sub.score is None  # in-progress

    def test_resumes_existing_in_progress_attempt(
        self, basic_quiz, teacher_user, tenant
    ):
        sub1, _ = start_quiz_attempt(basic_quiz, teacher_user, tenant)
        sub2, err = start_quiz_attempt(basic_quiz, teacher_user, tenant)
        assert err is None
        assert sub2.id == sub1.id  # same row returned

    def test_returns_error_when_max_attempts_exhausted(
        self, basic_quiz, teacher_user, tenant
    ):
        """max_attempts=3: three completed attempts → error on next start."""
        for i in range(1, 4):
            QuizSubmission.all_objects.create(
                quiz=basic_quiz, teacher=teacher_user, tenant=tenant,
                attempt_number=i, answers={}, score=float(i * 10),
                started_at=timezone.now(),
            )
        sub, err = start_quiz_attempt(basic_quiz, teacher_user, tenant)
        assert sub is None
        assert err is not None
        assert "Maximum attempts" in err

    def test_unlimited_attempts_when_max_zero(
        self, quiz_assignment, tenant, teacher_user
    ):
        """max_attempts=0 means unlimited."""
        unlimited = Quiz.objects.create(
            tenant=tenant,
            assignment=quiz_assignment,
            max_attempts=0,
            time_limit_minutes=None,
        )
        # Complete 10 attempts — should never get an error.
        for i in range(1, 11):
            QuizSubmission.all_objects.create(
                quiz=unlimited, teacher=teacher_user, tenant=tenant,
                attempt_number=i, answers={}, score=float(i * 5),
                started_at=timezone.now(),
            )
        sub, err = start_quiz_attempt(unlimited, teacher_user, tenant)
        assert err is None
        assert sub is not None
        assert sub.attempt_number == 11

    def test_stale_in_progress_closed_out_and_new_attempt_started(
        self, timed_quiz, teacher_user, tenant
    ):
        """M1 fix: a stale in-progress row (time expired) is closed and a
        fresh attempt is started on the next call to start_quiz_attempt."""
        # Create an in-progress row with a started_at in the past (11 min ago
        # for a 10-minute quiz).
        stale = QuizSubmission.all_objects.create(
            quiz=timed_quiz, teacher=teacher_user, tenant=tenant,
            attempt_number=1, answers={},
            started_at=timezone.now() - timedelta(minutes=11),
        )
        assert stale.score is None  # still in-progress

        new_sub, err = start_quiz_attempt(timed_quiz, teacher_user, tenant)
        assert err is None
        assert new_sub is not None
        assert new_sub.id != stale.id  # a NEW row was created

        # The stale row should be closed as time_expired=True, score=0.
        stale.refresh_from_db()
        assert stale.time_expired is True
        assert float(stale.score) == 0.0
        assert stale.graded_at is not None

        # The new attempt is fresh (score IS NULL).
        assert new_sub.score is None
        assert new_sub.attempt_number == 2

    def test_stale_close_respects_max_attempts(
        self, timed_quiz, teacher_user, tenant
    ):
        """M1 + max_attempts: if closing the stale attempt pushes completed
        count to max_attempts, start_quiz_attempt must return an error."""
        # timed_quiz has max_attempts=3. Pre-create 2 completed attempts.
        for i in range(1, 3):
            QuizSubmission.all_objects.create(
                quiz=timed_quiz, teacher=teacher_user, tenant=tenant,
                attempt_number=i, answers={}, score=float(i * 20),
                started_at=timezone.now(),
            )
        # Third is in-progress but stale.
        QuizSubmission.all_objects.create(
            quiz=timed_quiz, teacher=teacher_user, tenant=tenant,
            attempt_number=3, answers={},
            started_at=timezone.now() - timedelta(minutes=11),
        )

        sub, err = start_quiz_attempt(timed_quiz, teacher_user, tenant)
        assert sub is None, "Should be exhausted after stale close"
        assert err is not None
        assert "Maximum attempts" in err

    def test_attempt_number_monotonically_increases(
        self, basic_quiz, teacher_user, tenant
    ):
        """Attempt numbers must be sequential: 1, 2, 3, ..."""
        for expected_n in range(1, 4):
            sub, err = start_quiz_attempt(basic_quiz, teacher_user, tenant)
            assert err is None
            assert sub.attempt_number == expected_n
            # Complete the attempt so the next call creates a new one.
            sub.score = 80.0
            sub.save(update_fields=["score", "updated_at"])

    def test_attempt_number_is_per_teacher(
        self, basic_quiz, teacher_user, tenant
    ):
        """Two teachers within the same tenant each get their own attempt_number
        sequence — attempt_number is scoped to (quiz, teacher), not just quiz.

        Regression guard for TASK-013 M2: verifies the ``select_for_update``
        scoping correctly isolates counters per-teacher.
        """
        teacher_b = User.objects.create_user(
            email="teacher_b@otherschool.com",
            password="TeacherB!123",
            first_name="Teacher",
            last_name="B",
            tenant=teacher_user.tenant,
            role="TEACHER",
            is_active=True,
        )
        sub_a, _ = start_quiz_attempt(basic_quiz, teacher_user, tenant)
        sub_b, _ = start_quiz_attempt(basic_quiz, teacher_b, tenant)

        assert sub_a.attempt_number == 1
        assert sub_b.attempt_number == 1  # independent counter for teacher_b
        assert sub_a.id != sub_b.id
