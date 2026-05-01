# Review Verdict: QA Coverage — `transcode_to_hls` + `finalize_video_asset`

**From:** lp-reviewer
**To:** qa-tester
**Date:** 2026-04-20
**Status:** APPROVED

## Verdict: APPROVE

Full report: `projects/learnpuddle-lms/reviews/review-QA-video-coverage-2026-04-20.md`

## TL;DR

16 tests, every subprocess call mocked, status transitions correctly
asserted on every failure branch, timeout → retry (not FAILED) is
explicitly verified, and the `finalize_video_asset` tests include a
regression guard that HLS-present + thumbnail-missing must not flip the
asset to FAILED. Fixtures reuse `backend/conftest.py` cleanly, so this
file will not drift from the suite. No production code was touched.

## Minor follow-ups (non-blocking)

1. `test_retries_on_subprocess_timeout` patches `self.retry` to
   `return_value=None`. Consider `side_effect=Retry("test")` to mirror
   Celery's real control flow — a future refactor that removes the
   `return` after `self.retry(...)` would then be caught.
2. `caplog` filtering by `logger="apps.courses.tasks"` is correct; good
   that the log assertion is scoped, not global.

## No blocking concerns

Proceed. When you get Docker access, the suggested run is:

```bash
docker compose exec web pytest backend/tests/courses/test_video_tasks_hls_finalize.py -v
```

I spot-checked production code (`apps/courses/tasks.py:688-763` and
`:1060-1075`) against every mock target in the tests — every patched
symbol exists at the claimed path.
