---
tags: [review, qa/video-tasks, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: QA Coverage — `transcode_to_hls` + `finalize_video_asset`

## Verdict: APPROVE

## Summary
Clean, well-mocked tests that exercise the two remaining uncovered video
pipeline tasks without shelling out to real ffmpeg or touching storage.
Failure paths assert the correct status transitions; the timeout path
properly asserts `self.retry()` is called rather than letting the
exception propagate; retry machinery does not re-enter the task. No
production code was modified.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **`test_retries_on_subprocess_timeout` patches `retry` to `return_value=None`.**
   The real `self.retry()` raises `Retry` to abort the current task run. The
   test stubs it out so execution continues past the `except` block — the
   assertion is merely `mock_retry.called`. This is fine for "we invoked
   retry" but does not guard against a future refactor where someone removes
   the `return` after `self.retry(...)`. Consider `side_effect=Retry("test")`
   to model the real control flow. Non-blocking.

2. **`test_unexpected_exception_sets_status_failed_and_reraises`** asserts
   `status == "FAILED"` after `_upload_dir` raises. The task currently uses
   `VideoAsset.objects.filter(id=video_asset_id).update(status='FAILED')`
   inside a bare-`except` inner block, which swallows update errors silently
   — the test doesn't catch that subtlety. Again, non-blocking; this is the
   shape of the production code.

3. **`test_marks_failed_when_hls_missing`** sets `hls_master_url = ""`.
   Cross-check against production: `if not asset.hls_master_url:` treats
   empty string as missing, correct. If the column semantics ever change to
   nullable-only, the test still passes because `"" → None → not None` both
   fall through. Good.

## Positive Observations

- **No real subprocess invocation.** Every `subprocess.check_output` call
  is patched via `@patch("apps.courses.tasks.subprocess.check_output", ...)`.
  Tests do not require ffmpeg to be installed on the test runner.
- **Status-transition coverage is comprehensive:**
  - Happy path → `status` unchanged (transcode) / `READY` (finalize).
  - `FileNotFoundError` (ffmpeg missing) → `FAILED` + "ffmpeg" in error.
  - `CalledProcessError` → `FAILED` + "ffmpeg failed" in error.
  - `TimeoutExpired` → `retry()` called, `FAILED` NOT set.
  - Generic `RuntimeError` from storage → `FAILED` set AND exception
    re-raised so Celery's retry machinery can pick it up.
- **`test_retries_on_subprocess_timeout`** asserts `video_asset.status != "FAILED"`
  explicitly, catching regressions where someone "helpfully" marks the
  asset failed on timeout (which would prevent the retry from working).
- **`test_does_not_change_ready_asset_to_failed_when_thumbnail_missing`**
  is a well-placed regression guard that codifies the "thumbnail is
  nice-to-have, HLS is critical" gate.
- **`test_logs_warning_when_ready_without_thumbnail`** uses `caplog` with
  the correct logger name (`apps.courses.tasks`) — not `WARNING` globally,
  which would catch unrelated warnings and false-positive.
- **Fixture reuse**: `video_asset` and `video_asset_failed` fixtures derive
  cleanly from the existing `tenant`/`course`/`module`/`video_content`
  fixtures in `backend/conftest.py`, so nothing about this file risks
  drifting from the rest of the suite.
- **ffmpeg command-line assertion** (`test_happy_path_invokes_ffmpeg_with_hls_args`)
  checks for `-hls_time`, `-hls_playlist_type`, `vod`, and `.m3u8` output
  — i.e. the things that matter for HLS correctness — without over-specifying
  the exact argv.
- **Upload-dict fallback test** (`test_falls_back_to_default_master_key_when_not_in_upload_map`)
  covers the `master_key = uploaded.get("master.m3u8") or f"{hls_prefix}/master.m3u8"`
  branch in the production code. Good corner.

## Scope & Coverage Delta

The author correctly notes this doesn't reach the 60% backend-coverage
target on its own, but it chips away at `apps/courses/tasks.py` (the
largest single task module) and explicitly calls out follow-ups
(`_download_to_tempfile`, `_upload_dir`, `_safe_storage_url`,
`process_video_upload` orchestration). Out-of-scope list is honest.

## Decision

APPROVE. Minor nits can be addressed opportunistically.
