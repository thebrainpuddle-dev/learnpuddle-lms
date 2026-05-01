---
tags: [review, task/TASK-013, verdict/approve, reviewer/lp-reviewer, round/2]
created: 2026-04-19
---

# Review: TASK-013 — Multiple Quiz Attempts + Timed Quizzes (r2)

## Verdict: APPROVE

## Summary

All three Major issues from r1 (M1 stale `started_at`, M2 TOCTOU on
`attempt_number`, M3 GET mutation) are addressed correctly. The extracted
`apps/progress/quiz_helpers.py` cleanly consolidates attempt lifecycle +
grading logic, removing the cross-module private imports from the r1 minor
m1. URL wiring, read-only GET semantics, and the `select_for_update`
scoping all check out on static inspection. One low-severity observation on
XP signal behavior for time-expired closures (non-blocking) and one test
can't-run caveat noted below.

## Critical Issues

None.

## Major Issues

None — all three prior Majors resolved.

## Minor Issues

### m1 (new, low) — Stale-attempt close-out will trigger a `quiz_submission` XP award

In `quiz_helpers.start_quiz_attempt` (lines 201-207), when the in-progress
row is closed out for time-expiry it sets `score = 0, graded_at = _utcnow()`
then `.save(...)`. The `on_quiz_submission` signal (gamification_signals.py
L120-164) only skips when `score is None`; with `score = 0` it proceeds to
`award_xp(reason='quiz_submission', ...)`, which resolves to
`config.xp_per_quiz_submission` — a fixed amount regardless of score.

Net effect: a teacher who walks away, never submits, and later re-opens will
silently earn the full quiz_submission XP for the force-closed zero-score
attempt. The `reference_id` dedup prevents double-award on re-save, but it
does not prevent the first award.

This is low severity — the teacher-engagement impact is minor and the XP
engine respects opt-outs — but semantically awarding XP for a "you ran out
the clock by abandoning" attempt is probably not the intended product
behavior. Worth a follow-up ticket or a simple guard in the helper (e.g.
`save_without_xp` flag, or have the signal also skip when
`time_expired=True and score == 0`). Not a merge blocker.

### m2 (deferred from r1 / qa-tester followup) — xfail markers should be removed

`backend/apps/progress/tests_quiz_attempts.py` has 4 `xfail(strict=False)`
markers tied to M1/M2/M3. Tracing the test expectations against the current
implementation:

- `TestTimeLimitEnforcement::test_stale_started_at_resume_does_not_auto_expire`
  → M1 fix closes the stale row and spawns a fresh attempt; submit after
  the second start uses the new `started_at` → `time_expired=False`. Should
  XPASS.
- `TestQuizDetailGetIdempotency::test_get_is_read_only_post_start_creates_row`
  → GET returns no row; POST `/start/` is idempotent. Should XPASS.
- `TestAttemptNumberRace::test_stale_count_does_not_500` → helper holds
  row-lock + computes `max(attempt_number)+1`; the flaky_create test path
  collides with `unique_together` but the test asserts `status_code < 500`
  which is loose. Should XPASS (though still somewhat fragile —
  `IntegrityError` would surface as 500 if the pre-create happens between
  the helper's lock acquire and create; worth validating empirically).
- `TestAttemptNumberRace::test_two_threads_do_not_raise_integrity_error` →
  direct two-thread test on the helper. With `select_for_update` holding
  the row lock inside `transaction.atomic`, SQLite (test DB) may not honor
  `select_for_update` the same as Postgres — could be flaky under SQLite
  but passes under Postgres. Note in the notification to qa-tester.

Recommend qa-tester removes the `xfail` markers and runs the full suite on
the Postgres dev container.

## Positive Observations

- **quiz_helpers.py extraction** — clean split of validation, grading, and
  attempt-lifecycle. `start_quiz_attempt` has a crisp docstring spelling
  out the three semantic cases and why option (b) was chosen. Addresses
  r1-minor m1 at the same time.
- **M2 `select_for_update` scoping is correct** — the lock is scoped to
  prior `(quiz, teacher)` rows only (not table-wide), using
  `filter(quiz=quiz, teacher=teacher)` before the lock is materialized.
  Two parallel starts for the *same* `(quiz, teacher)` serialize; parallel
  starts across different teachers or quizzes are not blocked. No
  deadlock vs. the submit path because `quiz_submit` acquires a lock on
  the same row set with the same key, so the locks are ordered.
- **`max(attempt_number)+1` instead of `completed_count+1`** — robust
  against gaps left by closed-out stale rows (M1 case). Better than the r1
  code path.
- **M3 GET read-only confirmed** — `_build_quiz_detail_response` only reads
  via `filter(...).exclude(...)` and `get_in_progress_attempt`; no
  `.create()` or `.save()` on `QuizSubmission` anywhere in `quiz_detail`.
  Grepped teacher_views.py: all 5 `.save()` calls are in unrelated
  progress/assignment views or in `quiz_submit` (line 791). Same shape in
  `student_views.py`.
- **`max_attempts=0` path works** — at line 210:
  `if max_attempts > 0 and completed_count >= max_attempts` — the cap is
  only enforced when positive. Unlimited teachers always get a new
  attempt, and the close-out path runs unconditionally before the cap
  check.
- **URL wiring is clean** — both `teacher_urls.py` and `student_urls.py`
  place `/start/` before `/submit/` and `/` is last; no pattern conflict
  with the bare assignment UUID. `app_name` is correctly namespaced.
- **`quiz_submit` lock + re-check** — the second `select_for_update` on
  the submit path (line 746) prevents the "whichever save landed last"
  race from r1 m3; combined with the helper's lock, parallel start+submit
  sequences serialize correctly.
- **`seed_teacher_data.py` idempotence** — `get_or_create` keyed on
  `(quiz, teacher, attempt_number=1)` is safe to re-run. Behavior when a
  multi-attempt history already exists: it only looks for the
  `attempt_number=1` row and will no-op if present — correct intent for a
  seed script.
- **Legacy aliases** — r1 m1 compat shim at teacher_views.py L47-50 keeps
  external importers (and the one test that imports
  `_get_or_start_quiz_attempt`) working. Clean.

## Recommended next steps

1. Merge TASK-013. Update
   `docs/coordination/TASK-013-multiple-quiz-attempts-timed-quizzes.md`
   status to `done`.
2. qa-tester removes the 4 `xfail(strict=False)` markers in
   `backend/apps/progress/tests_quiz_attempts.py` and runs the full suite
   on the Postgres dev container. If any of the four go to XFAIL (not
   XPASS), escalate back to backend-engineer with the failing traceback.
3. File a follow-up ticket (low priority) for m1 above — either skip
   `quiz_submission` XP on force-closed time-expired-with-score-0 rows, or
   document the current behavior as intentional in the task doc.

## Test run

Pytest could not be executed in this sandbox (Docker unavailable, direct
`python3 -m pytest ...` blocked by the permission layer). Verified
statically against the test expectations in
`backend/apps/progress/tests_quiz_attempts.py` — all four xfail-marked
tests align with the current implementation and should XPASS on the
Postgres dev container. Recommend qa-tester confirms empirically before
stripping the markers.
