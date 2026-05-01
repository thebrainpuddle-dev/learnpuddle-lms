---
tags: [review, task/TASK-013, verdict/request-changes, reviewer/lp-reviewer]
created: 2026-04-19
---

# Review: TASK-013 — Multiple Quiz Attempts + Timed Quizzes

## Verdict: REQUEST_CHANGES

## Summary

The core design is sound: the model/migration shape is correct, the
in-progress-attempt pattern (score IS NULL) is applied consistently across
all known consumers, and the XP signal is properly guarded against in-progress
rows and re-saves. However there are two **Major** issues that must be fixed
before merge — a server-trust gap in time-limit enforcement, a concurrency gap
around `attempt_number` allocation — plus a handful of **Minor** code-quality
and test-coverage gaps. No Critical / blocking issues.

## Critical Issues

None.

## Major Issues

### M1 — `started_at` is trusted from a row the client can indirectly "reset"

In `teacher_views._get_or_start_quiz_attempt` (and the student clone) the
in-progress row is created with `started_at=_utcnow()`. That's correct.
But `quiz_submit` enforces the time limit only against `in_progress.started_at`
without ever verifying the row was created by this teacher's session or that
it is the same attempt the client is submitting. The client cannot forge
`started_at` directly (good), but there is a subtler issue:

- If a teacher fetches `quiz_detail` (starting attempt N), never submits, then
  returns weeks later and fetches `quiz_detail` again, `_get_or_start_quiz_attempt`
  **returns the existing in-progress row unchanged** — so `started_at` is now
  weeks in the past and the very next submit will always fire `time_expired=True`,
  saving whatever partial answers were posted and locking that attempt as "failed".
  The teacher cannot re-open with a fresh clock.

Fix: either (a) auto-expire and auto-close the stale in-progress attempt and
spin up a new one on re-open (preferred), or (b) have `quiz_detail` reset
`started_at` when the attempt is resumed after a grace window. Document the
chosen semantics in the task doc.

### M2 — Race condition on `attempt_number` allocation

`_get_or_start_quiz_attempt` does:

```python
completed_count = QuizSubmission.all_objects.filter(...).exclude(score__isnull=True).count()
...
attempt_number = completed_count + 1
submission = QuizSubmission.all_objects.create(..., attempt_number=attempt_number, ...)
```

This is a classic TOCTOU. Two parallel requests (e.g. double-clicking "Start
Quiz", or a tab + mobile open) can both read `completed_count = N` and both
attempt `create(attempt_number=N+1)`. One wins; the other raises
`IntegrityError` because of `unique_together = ("quiz", "teacher",
"attempt_number")` — and that bubbles up as a 500.

Fix: either wrap the read+create in `transaction.atomic()` with
`select_for_update()` on the `QuizSubmission` rows for (quiz, teacher), or
catch `IntegrityError` and retry once with the refreshed count. The same
applies in `quiz_submit`'s secondary "no in-progress attempt" path.

### M3 — `quiz_detail` creates side-effect rows on a GET

`quiz_detail` (GET) calls `_get_or_start_quiz_attempt` which **creates** a
QuizSubmission row on first view. This turns a GET into a side-effecting
endpoint. Consequences:

- Prefetching, bots, CSRF-less tools or bookmark loads can silently burn an
  attempt-slot row (it remains in-progress, but it occupies the
  `unique_together` slot until submitted or cleared).
- Violates REST semantics and makes caching impossible.
- Combined with M1, returning to the page days later does not get a fresh
  clock.

Recommend a dedicated `POST /api/teacher/quizzes/{assignment_id}/start/`
endpoint that mints the in-progress row; keep GET `quiz_detail` read-only
(return `current_attempt = null` until the teacher explicitly starts). This
is a schema change, so consider scoping it here vs. a follow-up ticket, but
at minimum add an idempotency comment + reviewer-visible note on why GET
mutates state.

## Minor Issues

### m1 — Helper import pattern couples `student_views` → `teacher_views`

`student_views.py` imports four private helpers (`_validate_answers_payload`,
`_grade_quiz_answers`, `_get_or_start_quiz_attempt`, `_serialize_attempt`,
`_utcnow`) from `teacher_views`. Private-with-underscore names imported
across modules is a smell. Extract these into `apps/progress/quiz_helpers.py`
(or similar) and import from both view modules.

### m2 — `time_limit_minutes` check trusts wall clock but no grace buffer

`elapsed_seconds > quiz.time_limit_minutes * 60` — submit latency (network RTT,
form serialization) can flip this from just-in-time to time_expired. Consider
a small server-side grace (e.g. 5 s) or compute the deadline at attempt start.
Low severity; document the chosen behavior.

### m3 — `quiz_submit` swallows IntegrityError implicitly

If two parallel submits arrive for the same in-progress row, the second save
overwrites whatever the first wrote (no row-lock on the UPDATE). Not a data
integrity disaster since both are for the same attempt, but can cause
"whichever arrived last" scoring. Add a `select_for_update()` around the
`.first()` fetch + `.save()` block.

### m4 — `seed_teacher_data.py` still creates `QuizSubmission` with no `attempt_number`

`backend/apps/courses/management/commands/seed_teacher_data.py:218` calls
`QuizSubmission.objects.create(... tenant, quiz, teacher, answers, score ...)`
— relies on `attempt_number=1` default, which is fine, but if the script is
re-run it will hit the new unique constraint and crash with IntegrityError
instead of the previous (quiz, teacher) collision. Add `attempt_number=1` or
a `get_or_create` guard to make the intent explicit.

### m5 — Legacy `submission` field in `quiz_detail` returns *latest* not *best*

`quiz_detail` returns both `attempt_history` and a top-level `submission`
field. The `submission` field is populated from `completed_submissions[-1]`
(latest by `attempt_number`), while `_quiz_submission()` in serializers
correctly returns **best**. These two "best-vs-latest" semantics in the same
API surface will confuse consumers and may have already broken the frontend
cert-unlock / gamification display if they consume this field. Either
remove `submission` (breaking) or align it with best-score semantics.

### m6 — Test coverage gap

Model-level tests exist (unique_together, multi-attempt, time_expired default).
**View-level tests are missing** for:

- (a) POST `quiz_submit` returns 400 when `max_attempts` is exhausted
- (b) Time limit flips `time_expired=True` after `time_limit_minutes`
  (can be mocked with `freezegun` or `django.utils.timezone`)
- (c) `attempts_remaining` decrements correctly across attempts
- (d) Best-score is returned by `_quiz_submission()` across three attempts
      (e.g. 60, 90, 75 → should return the 90)
- (e) XP awarded only once across multiple attempts (reference_id dedup on
  XPTransaction is per-submission-id, so XP *is* awarded per attempt — that
  is the correct behavior but should be asserted)
- (f) `quiz_detail` GET is idempotent for an already-started attempt (does
  not create a second in-progress row)

Flag all six to qa-tester.

### m7 — `updated_at = auto_now` means any re-save on an in-progress row churns the row

Low impact but worth noting — `updated_at` triggers on any field touch;
combined with M3 (GET mutates), `updated_at` is unreliable as an activity
proxy.

## Positive Observations

- Migration `0013_quiz_attempts_and_time_limit` is safe: all new columns have
  defaults, `AlterUniqueTogether` replaces the old constraint atomically in
  Django, and existing rows retain `attempt_number=1`. Dependency on
  `0012_...` is correct, and the parallel `0013_assessment` branch is merged
  cleanly by `0014_rubrics` listing both as dependencies — **not** a
  migration conflict.
- `score IS NULL` as the "in-progress" marker is applied consistently in
  every downstream consumer I grepped: `teacher_views`, `student_views`,
  `teacher_serializers._quiz_submission`, `student_serializers._quiz_submission`,
  `gamification._collect_activity_days`, `gamification.build_teacher_gamification_summary`,
  `gamification_tasks.backfill_xp`, `gamification_signals.on_quiz_submission`,
  `tenants.services.student_quiz_subs`, `reports.views.quiz_subs_map`.
  `reports/manager_views.py` imports QuizSubmission but does not query it in
  the reviewed diff — no gap there.
- `on_quiz_submission` signal correctly (a) skips `score IS NULL`, and (b)
  dedupes by `reference_id=instance.id` so re-saves of the same attempt
  (e.g. admin manual grade for short-answer) do not double-award XP.
- `_quiz_submission()` in both serializers correctly orders by `-score,
  -attempt_number` to return the best attempt — best-score semantics
  preserved for the public-facing assignment list. Same pattern in
  `reports.views.quiz_subs_map`.
- Helpers `_validate_answers_payload` and `_grade_quiz_answers` are clean
  extractions; the MCQ multi-select / TRUE_FALSE / SHORT_ANSWER branches are
  all covered.
- Tenant isolation preserved — all new queries use either the default
  `TenantManager` (`QuizSubmission.objects`) or `all_objects` with explicit
  `quiz=` / `teacher=` filters (teacher is tenant-scoped upstream).
- Indexes: new `(quiz, teacher, attempt_number)` composite index is a good
  fit for the "find in-progress / best attempt" access pattern.

## Recommended next steps

1. backend-engineer addresses M1, M2, M3 (or formally scopes M3 to a
   follow-up ticket with owner + timeline).
2. Minor items m1, m4, m5 fixed in the same PR.
3. qa-tester lands the six missing view-level tests (m6).
4. Re-review after fixes.
