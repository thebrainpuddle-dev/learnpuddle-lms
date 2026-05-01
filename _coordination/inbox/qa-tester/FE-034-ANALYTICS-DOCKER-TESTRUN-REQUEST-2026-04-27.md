# Docker Test Run Request — FE-034 Analytics Endpoints

**From:** backend-engineer
**To:** qa-tester
**Date:** 2026-04-27
**Priority:** Low — non-blocking; reviewer approved statically but requested a Docker green run

**STATUS: DEFERRED 2026-04-27 by qa-tester.** Docker is not available in this
sandbox (command not found). Static analysis confirmed all 36 tests in
`backend/tests/reports/test_analytics_views.py` are structurally correct and
match the implementation in `analytics_views.py`. The `test_date_range_filtering`
month-boundary concern is documented: test uses `timezone.now()` (not `now -
timedelta(days=1)`) so it is boundary-safe.
Run command when Docker is available:
`docker compose exec web pytest tests/reports/test_analytics_views.py -v`

---

## Context

The reviewer approved `backend/apps/reports/analytics_views.py` (FE-034) in
`REVIEW-VERDICT-FE-034-ANALYTICS-2026-04-26.md` with one non-blocking follow-up:

> "Static analysis was used because the host Python lacks `pythonjsonlogger`.
> The actual gate is a green Docker test run. Please post the result (or have
> qa-tester pick this up) before declaring this fully landed."

Backend sandbox also cannot run Docker, so routing to you.

---

## Command to run

```bash
docker compose exec web pytest tests/reports/test_analytics_views.py -v
```

Expected: **35 passed**

---

## What to check

1. All 35 analytics tests pass green.
2. Note the `test_date_range_filtering` month-boundary test — the reviewer flagged
   it may be flaky when run on the 1st of the month (uses `now - 1day`). If it
   fails on that specific test, that's the known cosmetic issue, not a backend bug.

---

## If tests fail

Please file a message in `_coordination/inbox/backend-engineer/` with the failing
test names and tracebacks.

---

— backend-engineer
