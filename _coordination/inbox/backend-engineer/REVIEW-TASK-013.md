# Review Outcome: TASK-013 — REQUEST_CHANGES

**From:** reviewer
**To:** backend-engineer
**Date:** 2026-04-19
**Full review:** `_coordination/reviews/review-TASK-013-quiz-attempts.md`

## Must-fix before re-review

### M1 — Stale `started_at` on resumed in-progress attempt
`_get_or_start_quiz_attempt` returns the existing in-progress row unchanged
when the teacher re-opens the quiz. If they opened it days ago and never
submitted, `started_at` is stale and every submit will immediately trigger
`time_expired=True`, locking the attempt.

Fix: on resume, either (a) auto-close the stale attempt and start a fresh
one, or (b) reset `started_at` when re-opening past a grace window.
Document the semantics in the task doc.

### M2 — `attempt_number` race on parallel starts
`completed_count + 1` then `create(attempt_number=...)` is a TOCTOU.
Parallel clicks / two tabs can both compute the same number and the second
`create()` bubbles an `IntegrityError` as a 500.

Fix: wrap in `transaction.atomic()` + `select_for_update()` on
`QuizSubmission` for (quiz, teacher), or catch `IntegrityError` and retry
with a refreshed count. Apply same pattern to the secondary path in
`quiz_submit`.

### M3 — GET `quiz_detail` mutates (creates row)
A GET that creates a `QuizSubmission` is a REST anti-pattern and has
operational consequences (prefetchers, bots, bookmark reloads burn attempt
slots). Combined with M1 it also blocks the "open then come back later"
user flow.

Fix: add a dedicated `POST .../quizzes/<id>/start/` to mint the
in-progress row; keep `quiz_detail` read-only. If you'd rather scope this
to a follow-up, please file a ticket and link it here.

## Should-fix in the same PR

- **m1** — Move `_validate_answers_payload`, `_grade_quiz_answers`,
  `_get_or_start_quiz_attempt`, `_serialize_attempt`, `_utcnow` into
  `apps/progress/quiz_helpers.py`. student_views importing private helpers
  from teacher_views is a smell.
- **m4** — `seed_teacher_data.py:218` `QuizSubmission.objects.create(...)`
  will collide with the new unique constraint on re-run. Add
  `attempt_number=1` explicitly or use `get_or_create`.
- **m5** — `quiz_detail` response has both `attempt_history` and legacy
  `submission`. The legacy field returns the **latest** attempt, while the
  serializers' `_quiz_submission()` returns **best**. Align or remove.

## For qa-tester (handoff note)

Flagged six missing view-level tests in the full review (m6). Please coordinate
with qa-tester to land them after M1/M2/M3 are fixed:

1. POST `quiz_submit` returns 400 when max_attempts exhausted
2. Time limit flips `time_expired=True` after `time_limit_minutes` (mock clock)
3. `attempts_remaining` decrements correctly across attempts
4. `_quiz_submission()` returns **best** (e.g. 60 → 90 → 75 returns 90)
5. XP awarded per attempt but deduped on re-save (XPTransaction dedup key)
6. `quiz_detail` GET is idempotent for an already-started attempt

## Positive signals (for context)

- Migration 0013 is safe, defaults populate existing rows, and the parallel
  `0013_assessment` branch merges cleanly at `0014_rubrics` — not a conflict.
- `score IS NULL` exclusion is applied in **every** consumer I grepped,
  including `gamification.*`, `tenants.services`, `reports.views`,
  `gamification_tasks.backfill_xp`, and both `_quiz_submission()`
  serializers. Good coverage.
- XP signal correctly skips in-progress rows and dedupes on `instance.id`
  so admin re-grades don't double-award.

Ping me when ready for re-review.
