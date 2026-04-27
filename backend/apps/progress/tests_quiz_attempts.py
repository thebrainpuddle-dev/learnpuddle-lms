"""
View-level tests for TASK-013: Multiple Quiz Attempts + Timed Quizzes.

These tests exercise the **target behavior** of the quiz attempt APIs. They
complement the model-level tests in ``backend/tests/progress/test_progress_models.py``
and are expected to go from RED -> GREEN as the backend-engineer's M1/M2/M3
fixes land (see ``_coordination/reviews/review-TASK-013-quiz-attempts.md``):

- M1: ``started_at`` on a stale in-progress row must not auto-expire a resumed
  attempt.
- M2: ``attempt_number`` allocation must be race-safe (no uncaught
  IntegrityError on concurrent first attempts).
- M3: GET ``quiz_detail`` must be idempotent -- it must not create a new
  ``QuizSubmission`` on every call; a dedicated POST ``/start/`` endpoint
  should mint the in-progress row.

Tests that depend on a fix that is not yet landed are marked ``xfail`` with a
pointer to the relevant Major issue, so CI stays green until the fix arrives.
"""

import threading
import uuid
from datetime import timedelta
from unittest import mock

import pytest
from django.db import IntegrityError, connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.courses.models import Content, Course, Module
from apps.progress.models import (
    Assignment,
    Quiz,
    QuizQuestion,
    QuizSubmission,
)
from apps.tenants.models import Tenant
from apps.users.models import User

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Local fixtures (self-contained so this file can be read independently).
# The root conftest.py already provides `tenant`, `teacher_user`, `admin_user`,
# etc.; we layer quiz-specific fixtures on top.
# ---------------------------------------------------------------------------


@pytest.fixture
def quiz_course(tenant, admin_user, teacher_user):
    """Published course assigned to all teachers in the tenant."""
    return Course.objects.create(
        tenant=tenant,
        title="Quiz Course",
        slug=f"quiz-course-{uuid.uuid4().hex[:6]}",
        description="Quiz attempt tests",
        created_by=admin_user,
        is_published=True,
        is_active=True,
        assigned_to_all=True,
    )


@pytest.fixture
def quiz_module(quiz_course):
    return Module.objects.create(
        course=quiz_course,
        title="M1",
        description="",
        order=1,
        is_active=True,
    )


@pytest.fixture
def quiz_content(quiz_module):
    return Content.objects.create(
        module=quiz_module,
        title="V",
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
        title="Quiz Assignment",
        description="d",
        instructions="",
        generation_source="VIDEO_AUTO",
        generation_metadata={},
    )


def _make_quiz(tenant, assignment, *, max_attempts=3, time_limit_minutes=None):
    """Create a Quiz + one single-answer MCQ so submissions produce a deterministic score."""
    quiz = Quiz.objects.create(
        tenant=tenant,
        assignment=assignment,
        is_auto_generated=True,
        max_attempts=max_attempts,
        time_limit_minutes=time_limit_minutes,
    )
    QuizQuestion.objects.create(
        tenant=tenant,
        quiz=quiz,
        order=1,
        question_type="MCQ",
        selection_mode="SINGLE",
        prompt="Pick A",
        options=["A", "B"],
        correct_answer={"option_index": 0},
        points=100,  # full score = 100 so it maps cleanly to percentages
    )
    return quiz


@pytest.fixture
def authed_client(teacher_user, tenant):
    """APIClient authenticated as the teacher on the tenant subdomain."""
    client = APIClient()
    client.force_authenticate(user=teacher_user)
    client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
    return client


def _correct_answer_payload(quiz):
    q = quiz.questions.first()
    return {"answers": {str(q.id): {"option_index": 0}}}


def _wrong_answer_payload(quiz):
    q = quiz.questions.first()
    return {"answers": {str(q.id): {"option_index": 1}}}


def _start_attempt(client, assignment_id):
    """Idiom: POST ``/start/`` to spawn / resume the in-progress attempt.

    After the M3 fix, GET ``quiz_detail`` is strictly read-only; attempt
    creation only happens via the dedicated POST ``/start/`` endpoint. The
    ``/start/`` response has the same shape as ``quiz_detail``.
    """
    return client.post(f"/api/teacher/quizzes/{assignment_id}/start/")


# ---------------------------------------------------------------------------
# 1. MaxAttemptsExhaustedTestCase -- POST quiz_submit returns 400 when exhausted.
# ---------------------------------------------------------------------------


class TestMaxAttemptsExhausted:
    def test_two_submissions_succeed_third_blocked(
        self, tenant, quiz_assignment, authed_client
    ):
        """With max_attempts=2, two submissions succeed, the third is 400."""
        quiz = _make_quiz(tenant, quiz_assignment, max_attempts=2)
        aid = quiz_assignment.id

        # Attempt 1: start + submit (correct).
        assert _start_attempt(authed_client, aid).status_code == 200
        resp1 = authed_client.post(
            f"/api/teacher/quizzes/{aid}/submit/",
            data=_correct_answer_payload(quiz),
            format="json",
        )
        assert resp1.status_code == 200, resp1.content
        assert resp1.json()["attempt_number"] == 1

        # Attempt 2: start + submit (correct).
        assert _start_attempt(authed_client, aid).status_code == 200
        resp2 = authed_client.post(
            f"/api/teacher/quizzes/{aid}/submit/",
            data=_correct_answer_payload(quiz),
            format="json",
        )
        assert resp2.status_code == 200, resp2.content
        assert resp2.json()["attempt_number"] == 2

        # Attempt 3: POST /start/ refuses with 400 (attempts exhausted).
        start3 = _start_attempt(authed_client, aid)
        assert start3.status_code == 400
        # GET (read-only) still returns detail surfacing attempts_exhausted.
        detail3 = authed_client.get(f"/api/teacher/quizzes/{aid}/")
        assert detail3.status_code == 200
        body3 = detail3.json()
        assert body3["attempts_exhausted"] is True
        assert body3["current_attempt"] is None
        assert body3["attempts_remaining"] == 0

        # And direct submit is rejected with a clear 400.
        resp3 = authed_client.post(
            f"/api/teacher/quizzes/{aid}/submit/",
            data=_correct_answer_payload(quiz),
            format="json",
        )
        assert resp3.status_code == 400, resp3.content
        err_msg = (resp3.json().get("error") or {}).get("message", "")
        assert "attempt" in err_msg.lower()
        assert "2" in err_msg  # limit surfaced in message

    def test_unlimited_attempts_when_max_attempts_zero(
        self, tenant, quiz_assignment, authed_client
    ):
        """max_attempts=0 => unlimited. Five submissions all succeed."""
        quiz = _make_quiz(tenant, quiz_assignment, max_attempts=0)
        aid = quiz_assignment.id

        for expected in range(1, 6):
            assert _start_attempt(authed_client, aid).status_code == 200
            resp = authed_client.post(
                f"/api/teacher/quizzes/{aid}/submit/",
                data=_correct_answer_payload(quiz),
                format="json",
            )
            assert resp.status_code == 200, resp.content
            assert resp.json()["attempt_number"] == expected

        # Sanity: 5 completed rows exist.
        completed = (
            QuizSubmission.all_objects.filter(quiz=quiz)
            .exclude(score__isnull=True)
            .count()
        )
        assert completed == 5


# ---------------------------------------------------------------------------
# 2. TimeLimitEnforcementTestCase -- elapsed > time_limit_minutes => time_expired.
# ---------------------------------------------------------------------------


class TestTimeLimitEnforcement:
    def test_time_expired_flag_set_after_limit(
        self, tenant, quiz_assignment, authed_client, teacher_user
    ):
        """10-minute quiz, submit after 11 minutes -> time_expired=True."""
        quiz = _make_quiz(tenant, quiz_assignment, time_limit_minutes=10)
        aid = quiz_assignment.id

        # Start the attempt normally (started_at = now).
        start_resp = _start_attempt(authed_client, aid)
        assert start_resp.status_code == 200
        attempt = QuizSubmission.all_objects.get(
            quiz=quiz, teacher=teacher_user, score__isnull=True
        )
        orig_started = attempt.started_at
        assert orig_started is not None

        # Simulate 11 minutes elapsing by backdating started_at. We avoid
        # freezegun to keep the test dependency-free; patching timezone.now
        # in the view is equivalent.
        attempt.started_at = orig_started - timedelta(minutes=11)
        attempt.save(update_fields=["started_at"])

        resp = authed_client.post(
            f"/api/teacher/quizzes/{aid}/submit/",
            data=_correct_answer_payload(quiz),
            format="json",
        )
        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert body["time_expired"] is True

        # Row persisted with the flag.
        attempt.refresh_from_db()
        assert attempt.time_expired is True

    def test_no_time_limit_never_expires(
        self, tenant, quiz_assignment, authed_client, teacher_user
    ):
        """time_limit_minutes=None -> time_expired=False even after hours."""
        quiz = _make_quiz(tenant, quiz_assignment, time_limit_minutes=None)
        aid = quiz_assignment.id

        assert _start_attempt(authed_client, aid).status_code == 200
        attempt = QuizSubmission.all_objects.get(
            quiz=quiz, teacher=teacher_user, score__isnull=True
        )
        attempt.started_at = attempt.started_at - timedelta(hours=5)
        attempt.save(update_fields=["started_at"])

        resp = authed_client.post(
            f"/api/teacher/quizzes/{aid}/submit/",
            data=_correct_answer_payload(quiz),
            format="json",
        )
        assert resp.status_code == 200, resp.content
        assert resp.json()["time_expired"] is False

    def test_stale_started_at_resume_does_not_auto_expire(
        self, tenant, quiz_assignment, authed_client, teacher_user
    ):
        """M1: Teacher opens quiz, leaves, comes back weeks later.

        After the M1 fix, re-opening the quiz closes out the stale
        in-progress row (``time_expired=True, score=0``) and starts a
        fresh attempt. The submitted attempt on that *fresh* row must NOT
        be auto-flagged time_expired.
        """
        quiz = _make_quiz(tenant, quiz_assignment, time_limit_minutes=10)
        aid = quiz_assignment.id

        # First POST /start/: spawn initial in-progress attempt.
        _start_attempt(authed_client, aid)
        attempt = QuizSubmission.all_objects.get(
            quiz=quiz, teacher=teacher_user, score__isnull=True
        )

        # Simulate the teacher walking away for 3 weeks.
        attempt.started_at = attempt.started_at - timedelta(days=21)
        attempt.save(update_fields=["started_at"])

        # Second POST /start/: the stale row is closed out and a fresh
        # attempt spawned.
        detail = _start_attempt(authed_client, aid)
        assert detail.status_code == 200

        # The stale attempt should now be closed out as time_expired=True.
        attempt.refresh_from_db()
        assert attempt.time_expired is True
        assert attempt.score == 0

        # A new in-progress row should exist with a fresh started_at.
        fresh = QuizSubmission.all_objects.get(
            quiz=quiz, teacher=teacher_user, score__isnull=True
        )
        assert fresh.id != attempt.id

        resp = authed_client.post(
            f"/api/teacher/quizzes/{aid}/submit/",
            data=_correct_answer_payload(quiz),
            format="json",
        )
        assert resp.status_code == 200
        # The fresh attempt must not be locked as expired just because the
        # original attempt was weeks ago.
        assert resp.json()["time_expired"] is False


# ---------------------------------------------------------------------------
# 3. AttemptsRemainingTestCase -- quiz_detail returns correct counts.
# ---------------------------------------------------------------------------


class TestAttemptsRemaining:
    def test_attempts_remaining_decrements_across_attempts(
        self, tenant, quiz_assignment, authed_client
    ):
        quiz = _make_quiz(tenant, quiz_assignment, max_attempts=3)
        aid = quiz_assignment.id

        # 0 completed attempts.
        d0 = _start_attempt(authed_client, aid).json()
        assert d0["attempts_used"] == 0
        assert d0["attempts_remaining"] == 3
        assert d0["attempts_exhausted"] is False

        # Submit attempt 1.
        authed_client.post(
            f"/api/teacher/quizzes/{aid}/submit/",
            data=_correct_answer_payload(quiz),
            format="json",
        )
        d1 = _start_attempt(authed_client, aid).json()
        assert d1["attempts_used"] == 1
        assert d1["attempts_remaining"] == 2
        assert d1["attempts_exhausted"] is False

        # Submit attempt 2.
        authed_client.post(
            f"/api/teacher/quizzes/{aid}/submit/",
            data=_correct_answer_payload(quiz),
            format="json",
        )
        d2 = _start_attempt(authed_client, aid).json()
        assert d2["attempts_used"] == 2
        assert d2["attempts_remaining"] == 1
        assert d2["attempts_exhausted"] is False

        # Submit attempt 3 -- now exhausted.
        authed_client.post(
            f"/api/teacher/quizzes/{aid}/submit/",
            data=_correct_answer_payload(quiz),
            format="json",
        )
        # POST /start/ is rejected once exhausted; use GET for the read-only
        # detail view.
        assert _start_attempt(authed_client, aid).status_code == 400
        d3 = authed_client.get(f"/api/teacher/quizzes/{aid}/").json()
        assert d3["attempts_used"] == 3
        assert d3["attempts_remaining"] == 0
        assert d3["attempts_exhausted"] is True
        assert d3["current_attempt"] is None

    def test_attempts_remaining_null_when_unlimited(
        self, tenant, quiz_assignment, authed_client
    ):
        _make_quiz(tenant, quiz_assignment, max_attempts=0)
        body = _start_attempt(authed_client, quiz_assignment.id).json()
        assert body["max_attempts"] == 0
        assert body["attempts_remaining"] is None
        assert body["attempts_exhausted"] is False


# ---------------------------------------------------------------------------
# 4. BestScoreAcrossAttemptsTestCase -- serializer returns best, not latest.
# ---------------------------------------------------------------------------


class TestBestScoreAcrossAttempts:
    def test_best_score_is_highest_not_latest(
        self, tenant, quiz_assignment, authed_client, teacher_user
    ):
        """Scores 60 -> 85 -> 70 => best = 85."""
        quiz = _make_quiz(tenant, quiz_assignment, max_attempts=3)
        aid = quiz_assignment.id

        # We bypass the submit grading path so we can pin exact scores by
        # faking the three attempts directly at the model layer. This matches
        # behaviour that the live API would produce for a multi-question quiz
        # with varying correctness, without us having to construct that quiz.
        def _complete(attempt_number, score):
            _start_attempt(authed_client, aid)  # spawn in-progress row
            row = QuizSubmission.all_objects.get(
                quiz=quiz, teacher=teacher_user, score__isnull=True
            )
            row.score = score
            row.graded_at = timezone.now()
            row.save()
            assert row.attempt_number == attempt_number

        _complete(1, 60)
        _complete(2, 85)
        _complete(3, 70)

        # quiz_detail's best_score — use GET (read-only) because POST /start/
        # returns 400 once max_attempts is exhausted.
        body = authed_client.get(f"/api/teacher/quizzes/{aid}/").json()
        # After 3 completed attempts with max_attempts=3, exhausted.
        assert body["attempts_exhausted"] is True
        assert body["best_score"] == 85.0

        # Assignment list serializer score should also reflect best (85).
        list_resp = authed_client.get("/api/teacher/assignments/")
        assert list_resp.status_code == 200
        entries = [a for a in list_resp.json() if a["id"] == str(aid)]
        assert entries, list_resp.json()
        assert entries[0]["score"] == 85.0

    def test_gamification_xp_awarded_per_submission_row(
        self, tenant, quiz_assignment, authed_client, teacher_user
    ):
        """XP is awarded per completed submission (per attempt), and each
        XPTransaction's reference_id points to the specific QuizSubmission
        that earned it -- not always the best-scoring one.

        This asserts the current product spec documented in
        ``gamification_signals.on_quiz_submission``: dedup is keyed per
        submission id, so each attempt earns its own XP.
        """
        from apps.progress.gamification_models import XPTransaction

        quiz = _make_quiz(tenant, quiz_assignment, max_attempts=3)
        aid = quiz_assignment.id

        # Two attempts via the real submit path (score 100 both).
        for _ in range(2):
            _start_attempt(authed_client, aid)
            authed_client.post(
                f"/api/teacher/quizzes/{aid}/submit/",
                data=_correct_answer_payload(quiz),
                format="json",
            )

        quiz_subs = list(
            QuizSubmission.all_objects.filter(quiz=quiz, teacher=teacher_user)
            .exclude(score__isnull=True)
            .order_by("attempt_number")
        )
        assert len(quiz_subs) == 2

        xp_rows = XPTransaction.all_objects.filter(
            teacher=teacher_user,
            reason="quiz_submission",
        )
        # One XP row per completed attempt.
        assert xp_rows.count() == 2
        # reference_ids map 1:1 to submission ids (no dedup collapsing).
        xp_ref_ids = set(str(x.reference_id) for x in xp_rows)
        sub_ids = set(str(s.id) for s in quiz_subs)
        assert xp_ref_ids == sub_ids


# ---------------------------------------------------------------------------
# 5. XPDedupAcrossAttemptsTestCase -- re-saving the same submission row does
#    NOT double-award. Per-attempt XP is the intended behaviour (per
#    gamification_signals.py comments).
# ---------------------------------------------------------------------------


class TestXPDedupAcrossAttempts:
    def test_resaving_submission_does_not_double_award(
        self, tenant, quiz_assignment, teacher_user
    ):
        """Admin manually re-grades a short-answer attempt -- XP must not
        be awarded twice for the same QuizSubmission row.
        """
        from apps.progress.gamification_models import XPTransaction

        quiz = _make_quiz(tenant, quiz_assignment, max_attempts=3)
        sub = QuizSubmission.objects.create(
            tenant=tenant,
            quiz=quiz,
            teacher=teacher_user,
            attempt_number=1,
            answers={"q1": "A"},
            score=80,
            graded_at=timezone.now(),
            started_at=timezone.now(),
        )
        first_count = XPTransaction.all_objects.filter(
            teacher=teacher_user,
            reason="quiz_submission",
            reference_id=sub.id,
        ).count()
        assert first_count == 1

        # Simulate admin re-grading (same row, new score).
        sub.score = 95
        sub.save()

        second_count = XPTransaction.all_objects.filter(
            teacher=teacher_user,
            reason="quiz_submission",
            reference_id=sub.id,
        ).count()
        assert second_count == 1  # no double-award


# ---------------------------------------------------------------------------
# 6. QuizDetailGetIdempotencyTestCase -- GET quiz_detail must not spawn a new
#    in-progress row every call (M3). Marked xfail until the M3 fix lands
#    (POST /start/ endpoint + read-only GET).
# ---------------------------------------------------------------------------


class TestQuizDetailGetIdempotency:
    def test_get_quiz_detail_does_not_create_second_in_progress_row(
        self, tenant, quiz_assignment, authed_client, teacher_user
    ):
        """Two GETs in a row must result in ONE in-progress row, not two.

        Today the view creates a row on first GET; subsequent GETs should
        return the same row. This is already the intended behaviour of
        ``_get_or_start_quiz_attempt`` (it looks up the in-progress row
        first), but we assert it explicitly to guard against regression.
        """
        quiz = _make_quiz(tenant, quiz_assignment, max_attempts=3)
        aid = quiz_assignment.id

        _start_attempt(authed_client, aid)
        _start_attempt(authed_client, aid)

        in_progress = QuizSubmission.all_objects.filter(
            quiz=quiz, teacher=teacher_user, score__isnull=True
        )
        assert in_progress.count() == 1

    def test_get_is_read_only_post_start_creates_row(
        self, tenant, quiz_assignment, authed_client, teacher_user
    ):
        """After M3, GET quiz_detail must NOT create any QuizSubmission
        row; only POST /api/teacher/quizzes/<id>/start/ mints an
        in-progress attempt. The start endpoint is idempotent: a second
        POST returns the existing in-progress row.
        """
        quiz = _make_quiz(tenant, quiz_assignment, max_attempts=3)
        aid = quiz_assignment.id

        # Pure GET must be read-only.
        resp = authed_client.get(f"/api/teacher/quizzes/{aid}/")
        assert resp.status_code == 200
        assert resp.json().get("current_attempt") is None
        assert (
            QuizSubmission.all_objects.filter(quiz=quiz, teacher=teacher_user).count()
            == 0
        )

        # Explicit start.
        start1 = authed_client.post(f"/api/teacher/quizzes/{aid}/start/")
        assert start1.status_code in (200, 201)
        assert (
            QuizSubmission.all_objects.filter(
                quiz=quiz, teacher=teacher_user, score__isnull=True
            ).count()
            == 1
        )

        # Second start is idempotent.
        start2 = authed_client.post(f"/api/teacher/quizzes/{aid}/start/")
        assert start2.status_code in (200, 201)
        assert (
            QuizSubmission.all_objects.filter(
                quiz=quiz, teacher=teacher_user, score__isnull=True
            ).count()
            == 1
        )


# ---------------------------------------------------------------------------
# 7. AttemptNumberRaceTestCase -- M2: concurrent starts must not raise an
#    uncaught IntegrityError / 500.
# ---------------------------------------------------------------------------


class TestAttemptNumberRace:
    def test_stale_count_does_not_500(
        self, tenant, quiz_assignment, authed_client, teacher_user
    ):
        """Monkeypatch the pre-create count read to return a stale value,
        then ask the view to start an attempt twice. After the M2 fix the
        second call must either succeed (attempt_number=2) or return a
        clean 4xx -- NEVER an uncaught IntegrityError / 500.
        """
        quiz = _make_quiz(tenant, quiz_assignment, max_attempts=5)
        aid = quiz_assignment.id

        # First call creates attempt_number=1 legitimately.
        r1 = _start_attempt(authed_client, aid)
        assert r1.status_code == 200

        # Complete attempt 1 so the next GET must spin up attempt 2.
        authed_client.post(
            f"/api/teacher/quizzes/{aid}/submit/",
            data=_correct_answer_payload(quiz),
            format="json",
        )

        # Simulate the stale read: pretend there are 0 completed attempts,
        # which is what a racing second request would observe. The helper
        # should still land safely.
        from apps.progress import teacher_views as tv

        real_create = QuizSubmission.all_objects.create
        call_state = {"first": True}

        def flaky_create(*args, **kwargs):
            # On the first attempt during this test, try to force a
            # duplicate attempt_number=2 to mimic two racing requests.
            if call_state["first"]:
                call_state["first"] = False
                kwargs["attempt_number"] = 2
                # Pre-create the "winner" row so the view's create collides.
                QuizSubmission.all_objects.create(
                    tenant=kwargs.get("tenant"),
                    quiz=kwargs.get("quiz"),
                    teacher=kwargs.get("teacher"),
                    attempt_number=2,
                    answers={},
                    started_at=timezone.now(),
                )
            return real_create(*args, **kwargs)

        with mock.patch.object(
            QuizSubmission.all_objects, "create", side_effect=flaky_create
        ):
            # This must NOT 500. It may 200 (returning the in-progress row
            # from the winner) or 409/400 with a clean error.
            resp = _start_attempt(authed_client, aid)
            assert resp.status_code < 500, resp.content

    @pytest.mark.django_db(transaction=True)
    def test_two_threads_do_not_raise_integrity_error(
        self, tenant, quiz_assignment, teacher_user
    ):
        """Direct threaded test against the helper. Two threads calling
        ``_get_or_start_quiz_attempt`` for the same (quiz, teacher) must
        both either return a valid submission or raise a well-defined
        error -- never bubble an IntegrityError.
        """
        from apps.progress.teacher_views import _get_or_start_quiz_attempt

        quiz = _make_quiz(tenant, quiz_assignment, max_attempts=5)

        results = []
        errors = []

        def worker():
            try:
                sub, err = _get_or_start_quiz_attempt(quiz, teacher_user, tenant)
                results.append((sub, err))
            except IntegrityError as exc:
                errors.append(exc)
            finally:
                connection.close()

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        # After the fix we expect zero IntegrityErrors bubbling out.
        assert not errors, f"IntegrityError raised from helper: {errors}"
        # And at most ONE in-progress row for (quiz, teacher).
        in_progress_count = QuizSubmission.all_objects.filter(
            quiz=quiz, teacher=teacher_user, score__isnull=True,
        ).count()
        assert in_progress_count <= 1


# ---------------------------------------------------------------------------
# 8. AbandonedTimedQuizXPGuardTestCase -- when ``start_quiz_attempt`` closes
#    out a stale/expired in-progress row with ``time_expired=True, score=0``,
#    no XPTransaction should be awarded for that abandoned attempt. Teachers
#    who never submitted must not earn XP.
# ---------------------------------------------------------------------------


class TestAbandonedTimedQuizXPGuard:
    def test_abandoned_timed_attempt_awards_no_xp(
        self, tenant, quiz_assignment, authed_client, teacher_user
    ):
        """Start a timed quiz, walk away past the time limit, re-start.

        The stale row is closed out by ``start_quiz_attempt`` with
        ``time_expired=True, score=0`` -- the teacher never submitted
        answers. The ``on_quiz_submission`` signal must NOT award XP for
        that abandoned row.
        """
        from apps.progress.gamification_models import XPTransaction

        quiz = _make_quiz(tenant, quiz_assignment, time_limit_minutes=10)
        aid = quiz_assignment.id

        # 1) First /start/: spawn initial in-progress attempt.
        r1 = _start_attempt(authed_client, aid)
        assert r1.status_code == 200

        stale = QuizSubmission.all_objects.get(
            quiz=quiz, teacher=teacher_user, score__isnull=True
        )

        # 2) Age it past the time limit -- teacher walked away.
        stale.started_at = stale.started_at - timedelta(hours=1)
        stale.save(update_fields=["started_at"])

        # 3) Second /start/: helper detects the stale row, closes it out
        #    with time_expired=True, score=0 and spawns a fresh attempt.
        r2 = _start_attempt(authed_client, aid)
        assert r2.status_code == 200

        stale.refresh_from_db()
        assert stale.time_expired is True
        assert stale.score == 0

        # 4) No XPTransaction should exist for the abandoned row.
        abandoned_xp = XPTransaction.all_objects.filter(
            teacher=teacher_user,
            reason="quiz_submission",
            reference_id=stale.id,
        )
        assert abandoned_xp.count() == 0, (
            "Abandoned timed quiz attempt must not award XP; "
            f"found {abandoned_xp.count()} transactions."
        )

    def test_submitted_attempt_after_abandon_still_earns_xp(
        self, tenant, quiz_assignment, authed_client, teacher_user
    ):
        """Sanity check: after a stale row is closed out, the fresh
        attempt the teacher actually *submits* still earns XP normally.
        This guards against the guard being too aggressive.
        """
        from apps.progress.gamification_models import XPTransaction

        quiz = _make_quiz(tenant, quiz_assignment, time_limit_minutes=10, max_attempts=5)
        aid = quiz_assignment.id

        # Stale attempt 1 -> abandoned.
        _start_attempt(authed_client, aid)
        stale = QuizSubmission.all_objects.get(
            quiz=quiz, teacher=teacher_user, score__isnull=True
        )
        stale.started_at = stale.started_at - timedelta(hours=1)
        stale.save(update_fields=["started_at"])

        # Re-start: closes out stale, spawns fresh attempt.
        _start_attempt(authed_client, aid)
        fresh = QuizSubmission.all_objects.get(
            quiz=quiz, teacher=teacher_user, score__isnull=True
        )
        assert fresh.id != stale.id

        # Teacher submits the fresh attempt.
        resp = authed_client.post(
            f"/api/teacher/quizzes/{aid}/submit/",
            data=_correct_answer_payload(quiz),
            format="json",
        )
        assert resp.status_code == 200, resp.content

        fresh.refresh_from_db()

        # The submitted (non-abandoned) attempt earns XP.
        submitted_xp = XPTransaction.all_objects.filter(
            teacher=teacher_user,
            reason="quiz_submission",
            reference_id=fresh.id,
        )
        assert submitted_xp.count() == 1, (
            "Submitted attempt after abandon must earn XP once."
        )

        # And the abandoned row still has none.
        abandoned_xp = XPTransaction.all_objects.filter(
            teacher=teacher_user,
            reason="quiz_submission",
            reference_id=stale.id,
        )
        assert abandoned_xp.count() == 0
