# TASK-013 — Review fixes ready for re-review

**From:** backend-engineer
**To:** reviewer
**Date:** 2026-04-19
**Original review:** `_coordination/reviews/review-TASK-013-quiz-attempts.md`
**Ticket:** `_coordination/inbox/backend-engineer/REVIEW-TASK-013.md`

All three majors and two of the three "should-fix" minors addressed.
Please re-review.

## M1 — Stale `started_at` on resume

Went with **option (b)** from the review. `start_quiz_attempt()` (in the
new `apps/progress/quiz_helpers.py`) now detects an in-progress row whose
`time_limit_minutes` has elapsed, closes it out
(`time_expired=True, score=0, graded_at=now`), and starts a fresh attempt
if `max_attempts` still permits. Rationale captured in the helper
docstring and in a task-doc comment:

> Option (b) honours the time-limit guarantee. Option (a) would let a
> teacher silently reset the clock just by walking away and coming back,
> which erodes the very invariant a time limit is meant to enforce.

The closed-out stale attempt counts against `max_attempts` — the teacher
gets one more attempt iff they have slots remaining.

## M2 — TOCTOU on `attempt_number`

`start_quiz_attempt()` wraps the whole check-and-create in
`transaction.atomic()` with `select_for_update()` on every prior
`(quiz, teacher)` submission:

```python
with transaction.atomic():
    prior_locked = list(
        QuizSubmission.all_objects.select_for_update()
        .filter(quiz=quiz, teacher=teacher)
        .order_by("attempt_number")
    )
    # ... derive next_attempt from max(attempt_number)+1 ...
    QuizSubmission.all_objects.create(attempt_number=next_attempt, ...)
```

Two parallel starts now serialise through the row lock; neither races the
`unique_together` constraint. I used `max(attempt_number) + 1` instead of
`completed_count + 1` so the allocation is robust against gaps left by
the M1 closed-out stale rows.

Also tightened `quiz_submit` / `student_quiz_submit` with the same
`select_for_update` idiom so two parallel submits on the same in-progress
row serialise (addresses minor m3 — "whichever arrived last" scoring).

## M3 — GET mutates

New endpoints:

- `POST /api/teacher/quizzes/<assignment_id>/start/` → `quiz_start`
- `POST /api/student/quizzes/<assignment_id>/start/` → `student_quiz_start`

Both mint (or resume) the in-progress attempt and return the same payload
shape as `quiz_detail`. GET is now strictly read-only — `current_attempt`
is populated only when an in-progress row already exists, and no row is
ever created on GET. Prefetchers, bookmarks and background fetches can no
longer burn attempt slots.

## Minors fixed in the same PR

- **m1** — helpers extracted to `apps/progress/quiz_helpers.py`.
  `student_views` imports `quiz_helpers` directly; legacy
  `_validate_answers_payload` etc. are re-exported from `teacher_views`
  as aliases for backwards compatibility (one test in
  `tests_quiz_attempts.py` imports `_get_or_start_quiz_attempt`
  directly).
- **m4** — `seed_teacher_data.py:218` now uses
  `QuizSubmission.objects.get_or_create(... attempt_number=1)` so
  repeated seed runs no longer collide with the new unique constraint.
- **m5** — legacy `submission` field in `quiz_detail` /
  `student_quiz_detail` now returns the **best-scoring** attempt, aligned
  with `_quiz_submission()` serializer semantics. Not strictly asked for,
  but you flagged it as a consumer-confusion risk — cheaper to fix in
  place than to chase it down from the frontend.

## Deferred minors (explicitly noted)

- **m2** — time-limit grace buffer. Low severity, no action.
- **m6** — six missing view-level tests. The existing
  `apps/progress/tests_quiz_attempts.py` already covers all six scenarios
  but several are `xfail(strict=False)` pending M1/M2/M3. Post-fix they
  should XPASS and the markers can be dropped by qa-tester. Flagging for
  qa-tester coordination.
- **m7** — `updated_at` as activity proxy. No longer an issue now that
  GET is read-only; no action.

## Files changed

See `docs/coordination/shared-log.md` entry under `## 2026-04-19`
"[backend-engineer] FIXED — TASK-013 REQUEST_CHANGES" for the full list.
Key additions:

- `backend/apps/progress/quiz_helpers.py` (new)
- `backend/apps/progress/teacher_views.py`
  - Added `quiz_start` view
  - `quiz_detail` now read-only
  - `quiz_submit` wrapped in `transaction.atomic()` + `select_for_update`
- `backend/apps/progress/student_views.py` — same shape as teacher
- `backend/apps/progress/teacher_urls.py` /
  `backend/apps/progress/student_urls.py` — new `/start/` route
- `backend/apps/courses/management/commands/seed_teacher_data.py`
- `docs/coordination/TASK-013-multiple-quiz-attempts-timed-quizzes.md`
- `backend/apps/progress/tests_quiz_attempts.py` /
  `backend/apps/progress/tests_quiz_api.py` — updated to use POST
  `/start/`

## Test run

Docker is unavailable in this sandbox (`docker` command not found) and
direct `python3` invocation is blocked, so I could not execute
`docker compose exec web pytest apps/progress/`. All modified files pass
a manual static review (imports, indentation, URL wiring, helper
signatures). Please flag if your re-review uncovers anything, and
qa-tester should run the full suite — specifically:

- `apps/progress/tests_quiz_attempts.py` (the xfail markers for M1/M2/M3
  should now XPASS)
- `apps/progress/tests_quiz_api.py::test_quiz_detail_and_submit`
- `apps/progress/tests_teacher_views.py::QuizTests` (read-only GET + 404
  paths)

Ready for re-review — thanks!

## Processed 2026-04-19

Already reviewed earlier today — **APPROVED** in
`_coordination/reviews/review-TASK-013-r2.md` (2026-04-19 05:09). No
further action needed; closing out of queue.
