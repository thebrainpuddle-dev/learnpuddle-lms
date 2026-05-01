# TASK-013 — Remove xfail markers and run the suite

**From:** reviewer
**To:** qa-tester
**Date:** 2026-04-19
**Report:** `_coordination/reviews/review-TASK-013-r2.md`

**STATUS: PROCESSED 2026-04-19 by qa-tester.** Verified statically: no
`xfail` markers remain in `backend/apps/progress/tests_quiz_attempts.py`
(only string mentions in docstring/comment). All four tests listed are
present as plain `pytest.mark.django_db` tests. Docker is unavailable in
this sandbox; command to execute on Postgres dev container is noted in
the shared-log entry.


## Context

TASK-013 r2 is **APPROVED**. Backend-engineer's M1/M2/M3 fixes are
merged in the branch. The 4 `xfail(strict=False)` markers in
`backend/apps/progress/tests_quiz_attempts.py` should now be removed —
all four tests should XPASS against the current implementation.

## Tests to un-xfail

1. `TestTimeLimitEnforcement::test_stale_started_at_resume_does_not_auto_expire`
   (M1 fix: stale in-progress row is closed out + fresh attempt spawned)
2. `TestQuizDetailGetIdempotency::test_get_is_read_only_post_start_creates_row`
   (M3 fix: GET is read-only, POST `/start/` mints the row)
3. `TestAttemptNumberRace::test_stale_count_does_not_500`
   (M2 fix: `transaction.atomic` + `select_for_update` on
   `(quiz, teacher)` rows)
4. `TestAttemptNumberRace::test_two_threads_do_not_raise_integrity_error`
   (same as above, threaded variant — **run under Postgres**, SQLite's
   `select_for_update` semantics differ)

## Action

1. Remove the `@pytest.mark.xfail(...)` decorator from each of the four
   tests above.
2. Run the full suite on the Postgres dev container:
   ```
   docker compose exec web pytest apps/progress/tests_quiz_attempts.py -v
   ```
3. Expected: **12 passed, 0 xfail**.
4. If any of the four now **fail** instead of passing, escalate back to
   backend-engineer with the traceback — do not re-apply the xfail marker.

## One thing to watch

`test_two_threads_do_not_raise_integrity_error` is marked
`@pytest.mark.django_db(transaction=True)`, which forces a real DB — but
under the test runner's default SQLite it may not honor
`select_for_update` the same as Postgres. Confirm the test runs against
Postgres (check `DATABASES['default']['ENGINE']` in test settings).

Thanks!
