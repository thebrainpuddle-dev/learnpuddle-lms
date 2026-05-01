---
tags: [review, qa/video-pipeline, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-29
---

# Review: QA-VIDEO-PIPELINE-TIMEOUT-RETRY-TESTS (+2)

## Verdict: APPROVE

## Summary
Closes the `subprocess.TimeoutExpired` retry-path gap flagged in the 2026-04-28 verdict. Two well-scoped tests added — one each for `transcode_to_hls` and `generate_thumbnail`. Both pin the correct behavioral invariant: TimeoutExpired must NOT mark the asset FAILED.

## Verification

### Source contracts confirmed
- `apps/courses/tasks.py:746-747` — `transcode_to_hls`: `except subprocess.TimeoutExpired as exc: self.retry(exc=exc, countdown=120)` ✅
- `apps/courses/tasks.py:804-805` — `generate_thumbnail`: same handler ✅
- Neither TimeoutExpired branch calls `_mark_failed`; assertion target is correct.

### Test design
- `tests_video_pipeline_extended.py:191-223` (transcode) and `:315-342` (thumbnail)
- Both mock `_download_to_tempfile` to skip download I/O and `subprocess.check_output` to raise `TimeoutExpired`
- Wrap `.run()` in try/except to swallow the `celery.exceptions.Retry` that `self.retry()` raises
- Assert `self.asset.status != "FAILED"` after refresh — the right invariant

## Critical Issues
None.

## Major Issues
None.

## Minor Issues (non-blocking)
- The try/except around `.run()` catches bare `Exception`. Catching `celery.exceptions.Retry` explicitly would be tighter (and would surface unexpected exceptions instead of swallowing them). The explicit `assertNotEqual(status, "FAILED")` provides enough back-pressure that this is acceptable, but tightening would prevent silent regressions where a different exception is raised.

## Positive Observations
- Tests verify behavior (status invariant) not implementation (no asserting on `self.retry` mock call count).
- Symmetric coverage: both tasks tested even though only one was strictly required by the prior verdict.
- Docstrings clearly explain why TimeoutExpired is transient vs. CalledProcessError/FileNotFoundError being permanent.
- Mock setup matches the pattern in the surrounding failure-path tests — consistent with codebase conventions.
- Suite count goes 17 → 19 as advertised; no impact on existing tests.
