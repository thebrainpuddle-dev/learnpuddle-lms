# TASK-013: Multiple Quiz Attempts + Timed Quizzes

**Priority:** P1 (Enterprise Feature)
**Phase:** 3
**Status:** done
**Assigned:** backend-engineer
**Estimated:** 3-4 hours

## Review History

- **r1** (2026-04-19): REQUEST_CHANGES — 3 majors (M1 stale started_at, M2 TOCTOU race, M3 GET mutation) + 3 minors
- **r2** (2026-04-19): APPROVE — all M1/M2/M3 + m1/m4/m5 resolved

## Open Follow-ups (non-blocking)

- **XP on timed-out attempts**: `on_quiz_submission` currently fires even for
  `time_expired=True, score=0` force-closes. Reviewer suggests guarding
  `award_xp` to skip timed-out zero-score submissions. Tracked as separate
  low-severity ticket. See `TASK-013-APPROVED.md` for detail.

## Problem

The current quiz system only allows a single attempt per teacher (`unique_together = [("quiz", "teacher")]`). There is no mechanism for:
- Configuring how many attempts a quiz allows
- Enforcing a time limit on quiz attempts
- Tracking best score across multiple attempts
- Showing attempt history to the teacher

## Fix Required

### 1. Quiz Model — Add attempt and timing configuration

```python
class Quiz(models.Model):
    # ... existing fields ...
    max_attempts = models.PositiveIntegerField(
        default=1,
        help_text="0 = unlimited attempts"
    )
    time_limit_minutes = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Time limit per attempt in minutes. NULL = no limit."
    )
```

### 2. QuizSubmission Model — Support multiple attempts

- Remove `unique_together = [("quiz", "teacher")]`
- Add `attempt_number = models.PositiveIntegerField(default=1)`
- Add `started_at = models.DateTimeField(null=True, blank=True)` — when attempt was started
- Add `time_expired = models.BooleanField(default=False)` — auto-submitted on timeout
- Add `unique_together = [("quiz", "teacher", "attempt_number")]`

### 3. quiz_detail View — Return attempt metadata

Return:
- `max_attempts` — from Quiz
- `time_limit_minutes` — from Quiz
- `attempt_count` — how many attempts this teacher has used
- `best_score` — best score across all attempts
- `current_attempt` — latest submission if it exists and is not graded (in-progress)
- `all_attempts` — summary of all submissions (attempt_number, score, submitted_at)

### 4. quiz_submit View — Enforce attempt limits and time

- Check `attempt_count < max_attempts` (or `max_attempts == 0`)
- Determine `attempt_number` = `attempt_count + 1`
- If `time_limit_minutes` is set, validate time hasn't expired
- Create new `QuizSubmission` per attempt (not get_or_create)

## Acceptance Criteria

- [x] Teacher can retake a quiz up to `max_attempts` times
- [x] 4xx response when `max_attempts` exceeded
- [x] Quiz with `time_limit_minutes=30` flags submission as time_expired after 30 minutes
- [x] `quiz_detail` endpoint returns attempt history and best score
- [x] Backward compatible: existing QuizSubmission rows get attempt_number=1 via migration default

## Files Changed

- `backend/apps/progress/models.py` — Quiz + QuizSubmission models
- `backend/apps/progress/migrations/0013_quiz_attempts_and_time_limit.py` — Migration
- `backend/apps/progress/teacher_views.py` — quiz_detail (read-only) + quiz_start + quiz_submit
- `backend/apps/progress/student_views.py` — student_quiz_detail (read-only) + student_quiz_start + student_quiz_submit
- `backend/apps/progress/quiz_helpers.py` — shared grading + attempt lifecycle helpers (extracted from teacher_views; M1/M2 fixes live here)
- `backend/apps/progress/teacher_urls.py` / `student_urls.py` — new `POST .../quizzes/<id>/start/` route

## Review fixes (2026-04-19)

Addressed REQUEST_CHANGES review
(`_coordination/reviews/review-TASK-013-quiz-attempts.md`):

- **M1 — Stale `started_at` on resume**: `start_quiz_attempt()` now detects an
  in-progress attempt whose `time_limit_minutes` has elapsed, closes it out
  (`time_expired=True, score=0`) and starts a fresh attempt if
  `max_attempts` allows. Option (b) from the review — time limits mean time
  limits.
- **M2 — TOCTOU on `attempt_number`**: `start_quiz_attempt()` wraps the
  check-and-create in `transaction.atomic()` + `select_for_update()` on all
  prior `(quiz, teacher)` submissions so parallel starts serialise and
  cannot race the `unique_together` constraint. Parallel submits on the
  same in-progress row are also locked via `select_for_update()` in
  `quiz_submit` / `student_quiz_submit` (addresses minor m3).
- **M3 — GET `quiz_detail` side-effecting**: GET is now strictly read-only.
  Attempt creation moved to the new `POST .../quizzes/<id>/start/` endpoint
  for both teacher and student routes.
- **m1 — cross-module private imports**: helpers extracted to
  `apps.progress.quiz_helpers`.
- **m4 — seed collision**: `seed_teacher_data.py` now uses
  `get_or_create(... attempt_number=1)`.
- **m5 — legacy `submission` field semantics**: `quiz_detail` /
  `student_quiz_detail` now return the **best-scoring** attempt as
  `submission` (aligned with `_quiz_submission()` serializer behaviour
  elsewhere), not the latest.
