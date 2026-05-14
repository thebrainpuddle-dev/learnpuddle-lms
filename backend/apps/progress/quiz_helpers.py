"""
Shared helpers for quiz viewing, attempt creation and grading.

Extracted from ``teacher_views`` / ``student_views`` so both role-scoped view
modules can import them without cross-importing private (underscore-prefixed)
symbols from each other.

Attempt-creation semantics (see TASK-013):

* A ``QuizSubmission`` row with ``score IS NULL`` represents an **in-progress**
  attempt — the teacher has started but not yet submitted.
* ``score IS NOT NULL`` (including ``score = 0``) represents a **completed**
  attempt.
* ``attempt_number`` is 1-based and unique per ``(quiz, teacher)`` via the
  model's ``unique_together`` constraint.
* Attempt creation is wrapped in ``transaction.atomic()`` + ``select_for_update``
  to close the TOCTOU window between counting completed attempts and
  inserting the new one (M2 fix).
* If a teacher resumes a quiz whose time limit has already elapsed, the stale
  in-progress row is **closed out** (``time_expired=True``, ``score=0``) and
  a fresh attempt is started when ``max_attempts`` permits (M1 fix,
  option (b) from the review — it is more honest than silently refreshing the
  clock).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Tuple

from django.db import IntegrityError, connection, transaction
from django.utils import timezone as dj_timezone

from apps.progress.models import QuizSubmission


def _utcnow():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Answer payload validation / grading
# ---------------------------------------------------------------------------

def validate_answers_payload(answers):
    """Validate the answers dict from the request body.

    Returns an error string if invalid, or ``None`` if OK.
    """
    if not isinstance(answers, dict):
        return "answers must be an object"
    max_answers = 200
    if len(answers) > max_answers:
        return f"Too many answers (max {max_answers})"
    for key, val in answers.items():
        if not isinstance(val, dict):
            return f"Each answer must be an object, got {type(val).__name__} for '{key}'"
        # Reject nested objects. Allow option_indices as a flat list for multi-select MCQ.
        for inner_key, inner_val in val.items():
            if isinstance(inner_val, dict):
                return "Answer values cannot contain nested objects"
            if isinstance(inner_val, list):
                if inner_key != "option_indices":
                    return "Only option_indices may be an array value"
                if any(isinstance(v, (dict, list)) for v in inner_val):
                    return "option_indices must be a flat array"
    return None


def grade_quiz_answers(quiz, answers):
    """Auto-grade objective questions (MCQ, TRUE_FALSE).

    Returns ``(mcq_score: float, has_short_answer: bool)``.
    """
    all_questions = list(quiz.questions.all())
    has_short_answer = any(q.question_type == "SHORT_ANSWER" for q in all_questions)
    mcq_score = 0.0

    for q in all_questions:
        if q.question_type == "SHORT_ANSWER":
            continue

        got = answers.get(str(q.id)) or {}
        if not isinstance(got, dict):
            continue

        if q.question_type == "MCQ":
            mode = (q.selection_mode or "SINGLE").upper()
            if mode == "MULTIPLE":
                expected_raw = (q.correct_answer or {}).get("option_indices") or []
                if not isinstance(expected_raw, list):
                    continue
                try:
                    expected = {int(v) for v in expected_raw}
                except Exception:
                    continue
                selected_raw = got.get("option_indices") or []
                if not isinstance(selected_raw, list):
                    continue
                try:
                    selected = {int(v) for v in selected_raw}
                except Exception:
                    continue
                if selected and selected == expected:
                    mcq_score += float(q.points or 1)
                continue

            try:
                expected = int((q.correct_answer or {}).get("option_index"))
            except Exception:
                continue
            try:
                selected = int(got.get("option_index"))
            except Exception:
                selected = None
            if selected is not None and selected == expected:
                mcq_score += float(q.points or 1)
            continue

        if q.question_type == "TRUE_FALSE":
            expected = (q.correct_answer or {}).get("value")
            selected = got.get("value")
            if isinstance(expected, bool) and isinstance(selected, bool) and selected == expected:
                mcq_score += float(q.points or 1)
            continue

    return mcq_score, has_short_answer


# ---------------------------------------------------------------------------
# Attempt lifecycle
# ---------------------------------------------------------------------------

def _is_expired(in_progress, quiz) -> bool:
    """Return True if the in-progress attempt's time limit has elapsed."""
    if not quiz.time_limit_minutes or not in_progress.started_at:
        return False
    elapsed_seconds = (dj_timezone.now() - in_progress.started_at).total_seconds()
    return elapsed_seconds > quiz.time_limit_minutes * 60


def get_in_progress_attempt(quiz, teacher) -> Optional[QuizSubmission]:
    """Return the current in-progress ``QuizSubmission`` (``score IS NULL``)
    for this ``(quiz, teacher)`` pair, or ``None`` if none exists.

    This is **read-only** — it never creates a row. Use ``start_quiz_attempt``
    to explicitly start a new attempt (e.g. from a POST ``/start/`` endpoint).
    """
    return (
        QuizSubmission.all_objects.filter(quiz=quiz, teacher=teacher, score__isnull=True)
        .order_by("-attempt_number")
        .first()
    )


def start_quiz_attempt(quiz, teacher, tenant) -> Tuple[Optional[QuizSubmission], Optional[str]]:
    """Return (or create) the in-progress attempt for ``(quiz, teacher)``.

    Semantics:

    1. If an in-progress attempt exists AND it has not expired: return it
       (resumes the current attempt).
    2. If an in-progress attempt exists BUT its time limit has elapsed:
       close it out as ``time_expired=True, score=0`` and start a new
       attempt — subject to ``max_attempts``. This honours the time-limit
       guarantee (see M1 fix in review TASK-013).
    3. If no in-progress attempt exists: create one subject to
       ``max_attempts``.

    The whole check-and-create sequence runs inside ``transaction.atomic()``
    with ``select_for_update`` on prior ``(quiz, teacher)`` submissions so
    parallel starts (double-click, two tabs) cannot both land the same
    ``attempt_number`` and race the ``unique_together`` constraint (M2 fix).

    Returns ``(submission, None)`` on success, or ``(None, error_str)`` when
    the teacher has exhausted ``max_attempts``.
    """
    max_attempts = quiz.max_attempts  # 0 = unlimited

    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s), hashtext(%s))",
                    [str(quiz.id), str(teacher.id)],
                )

        # Lock all prior submissions for this (quiz, teacher) pair so parallel
        # callers serialise through this block. We materialise the queryset
        # via list(...) so the SELECT ... FOR UPDATE actually executes.
        prior_locked = list(
            QuizSubmission.all_objects.select_for_update()
            .filter(quiz=quiz, teacher=teacher)
            .order_by("attempt_number")
        )

        completed = [s for s in prior_locked if s.score is not None]
        in_progress_rows = [s for s in prior_locked if s.score is None]
        in_progress = in_progress_rows[-1] if in_progress_rows else None

        # Case 1: live in-progress row.
        if in_progress and not _is_expired(in_progress, quiz):
            return in_progress, None

        # Case 2: stale in-progress row — close it out as a spent attempt.
        # This preserves the unique_together slot for attempt_number and
        # consumes one max_attempts slot (option (b) from the review).
        if in_progress and _is_expired(in_progress, quiz):
            in_progress.time_expired = True
            in_progress.score = 0
            in_progress.graded_at = _utcnow()
            in_progress.save(update_fields=["time_expired", "score", "graded_at", "updated_at"])
            # Recompute completed list now that the stale attempt is counted.
            completed = completed + [in_progress]

        completed_count = len(completed)
        if max_attempts > 0 and completed_count >= max_attempts:
            return None, f"Maximum attempts reached ({max_attempts})"

        # Next attempt number = max existing attempt_number + 1 (falls back to
        # completed_count+1 for empty history). This is race-safe because we
        # hold row locks on every prior (quiz, teacher) row above.
        next_attempt = (
            max((s.attempt_number for s in prior_locked), default=0) + 1
        )

        try:
            with transaction.atomic():
                submission = QuizSubmission.all_objects.create(
                    quiz=quiz,
                    teacher=teacher,
                    tenant=tenant,
                    attempt_number=next_attempt,
                    started_at=_utcnow(),
                    answers={},
                    # score remains NULL until submit.
                )
        except IntegrityError:
            winner = (
                QuizSubmission.all_objects.filter(
                    quiz=quiz,
                    teacher=teacher,
                    score__isnull=True,
                )
                .order_by("-attempt_number")
                .first()
            )
            if winner:
                return winner, None
            return None, "Another attempt was just started; please refresh."
        return submission, None


def serialize_attempt(sub):
    return {
        "attempt_number": sub.attempt_number,
        "score": float(sub.score) if sub.score is not None else None,
        "graded_at": sub.graded_at,
        "submitted_at": sub.submitted_at,
        "time_expired": sub.time_expired,
    }
