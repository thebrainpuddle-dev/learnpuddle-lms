# Review Request — QA Video Pipeline: TimeoutExpired Retry Tests (+2)

**From:** qa-tester
**To:** reviewer
**Date:** 2026-04-29
**Priority:** Low — closes reviewer-flagged gap from QA-VIDEO-PIPELINE-TESTS verdict (2026-04-28)

---

## Summary

Added 2 tests to `backend/apps/courses/tests_video_pipeline_extended.py` to close the
`subprocess.TimeoutExpired` retry-path gap identified in the 2026-04-28 review verdict:

> "Add `subprocess.TimeoutExpired` retry-path test for transcode (the 3rd failure
> branch is currently untested)."

Both `transcode_to_hls` and `generate_thumbnail` have an identical TimeoutExpired handler
(`self.retry(exc=exc, countdown=120)`) so I added one test per task for symmetry.

---

## File changed

`backend/apps/courses/tests_video_pipeline_extended.py`

---

## New tests (2)

### `TranscodeToHlsTestCase.test_retries_instead_of_failing_when_ffmpeg_times_out`

```python
def test_retries_instead_of_failing_when_ffmpeg_times_out(self, mock_dl):
    """
    subprocess.TimeoutExpired → task calls self.retry(), NOT _mark_failed().

    This is the 3rd subprocess failure branch. A timed-out transcode is
    transient — Celery will re-queue the task up to max_retries=3 times.
    The key invariant: TimeoutExpired must NOT flip the asset to FAILED status.
    """
```

### `GenerateThumbnailTestCase.test_retries_instead_of_failing_when_ffmpeg_times_out`

```python
def test_retries_instead_of_failing_when_ffmpeg_times_out(self, mock_dl):
    """
    subprocess.TimeoutExpired → task calls self.retry(), NOT _mark_failed().

    Thumbnail generation timing out is transient (slow disk I/O, big source
    video). The asset must NOT be marked FAILED so the retry can try again.
    """
```

---

## Behavioral contract tested

`subprocess.TimeoutExpired` is a **transient** failure:
- Worker was too slow (large video, disk I/O spike, memory pressure)
- Celery retries the task up to `max_retries=3` with a `countdown=120` delay
- The asset stays in `UPLOADED` state — NOT `FAILED` — so the retry can succeed

This is different from `CalledProcessError` (ffmpeg codec error — deterministic, mark FAILED)
and `FileNotFoundError` (ffmpeg not installed — permanent, mark FAILED).

---

## Static verification

- `apps/courses/tasks.py:746` — `transcode_to_hls`: `except subprocess.TimeoutExpired as exc: self.retry(exc=exc, countdown=120)` ✅
- `apps/courses/tasks.py:804` — `generate_thumbnail`: same pattern ✅
- Neither TimeoutExpired branch calls `_mark_failed()` ✅
- Existing `test_marks_failed_when_ffmpeg_binary_not_found` + `test_marks_failed_when_ffmpeg_exits_nonzero` unchanged ✅
- Test pattern matches existing failure-path tests (mock `_download_to_tempfile`, mock `subprocess.check_output`) ✅

---

## Docker run

```bash
docker compose exec web pytest \
  apps/courses/tests_video_pipeline_extended.py \
  -k "timeout" -v
# Expected: 2 passed

# Or full suite:
docker compose exec web pytest apps/courses/tests_video_pipeline_extended.py -v
# Expected: 19 passed (was 17 before this session)
```

---

## Context

- Source gap: reviewer comment in QA-VIDEO-PIPELINE-TESTS verdict (2026-04-28 inbox)
- Related tests: `TranscodeToHlsTestCase` (5→6 tests), `GenerateThumbnailTestCase` (5→6 tests)
- All other reviewer suggestions from QA-VIDEO-PIPELINE-TESTS verdict verified already done:
  - `test_thumbnail_marks_failed_when_source_file_missing` has `assertIn("Missing source_file", ...)` ✅
  - Happy-path tests for `generate_thumbnail` (thumbnail_url set) and `transcribe_video` (VideoTranscript created) ✅

— qa-tester
