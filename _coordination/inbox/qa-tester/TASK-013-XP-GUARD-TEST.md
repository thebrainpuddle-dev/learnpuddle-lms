# TASK-013 follow-up: test the XP guard on abandoned timed quizzes

**From**: backend-engineer
**Date**: 2026-04-19
**Priority**: low / follow-up to TASK-013 r2 APPROVE

**STATUS: PROCESSED 2026-04-19 by qa-tester.** `TestAbandonedTimedQuizXPGuard`
already lives at the bottom of
`backend/apps/progress/tests_quiz_attempts.py` with both the abandoned-no-XP
assertion and the positive-path companion. Traced statically through
`start_quiz_attempt` -> `gamification_signals.on_quiz_submission` XP guard
-> no `XPTransaction` row. Adequate.


## Context

Reviewer flagged a low-severity issue on TASK-013 r2: when
`quiz_helpers.start_quiz_attempt()` closes out an expired in-progress attempt
(M1 fix sets `time_expired=True, score=0, graded_at=now`), the
`post_save` signal on `QuizSubmission` would previously call `award_xp`,
silently awarding full quiz_submission XP to a teacher who abandoned the quiz.

## Fix applied (backend)

Guard added in `backend/apps/progress/gamification_signals.py` inside
`on_quiz_submission`:

```python
if getattr(instance, 'time_expired', False) and instance.score in (None, 0):
    logger.info("Skipping XP for abandoned timed quiz attempt id=%s", instance.pk)
    return
```

The guard is placed BEFORE the XPTransaction dedup lookup, so no row is
recorded for abandoned attempts.

Also applied the equivalent filter to the backfill task
`backfill_xp_for_existing_progress` in
`backend/apps/progress/gamification_tasks.py` — the quiz submissions
queryset now excludes `time_expired=True, score=0`.

## Test request

`backend/apps/progress/tests_quiz_attempts.py` already has
`TestXPDedupAcrossAttempts` but no case for abandonment. Please add a new
test (or extend that class) that covers:

1. Create a timed quiz (e.g. `time_limit_minutes=10`).
2. Teacher starts quiz (creates an in-progress `QuizSubmission` with
   `score=None`).
3. Simulate expiry by fast-forwarding `started_at` backwards, or directly
   invoking `start_quiz_attempt` a second time so the helper closes out
   the stale row (`time_expired=True, score=0, graded_at=now()`).
4. Assert **no `XPTransaction`** exists for that submission:

```python
from apps.progress.gamification_models import XPTransaction

assert not XPTransaction.all_objects.filter(
    reference_id=abandoned_submission.id,
    reference_type='quiz_submission',
).exists()
```

5. Bonus: assert the next attempt (submitted normally with score > 0)
   still awards XP exactly once — confirming the happy path is not
   regressed.

No backend code changes expected from your side; this is purely a test
coverage gap.
