# QA Coverage Report — Video Pipeline Tasks (transcode_to_hls + finalize_video_asset)

**Date:** 2026-04-20
**Agent:** qa-tester
**Target app:** `apps/courses/tasks.py` (video pipeline Celery tasks)
**Branch:** `maic-sprint-1-presence-rhythm`

---

## Summary

Added tests covering the final two previously-untested video pipeline Celery
tasks: `transcode_to_hls` and `finalize_video_asset`.

After a startup audit, both **discussions** and **media** apps turned out to
already have comprehensive test suites landed (in `apps/<app>/tests.py` and
mirrored/expanded under `backend/tests/<app>/test_*_views.py`). The remaining
zero-coverage surface from the earlier handoff was the HLS transcode task and
the finalize task; these are now covered.

---

## Deliverable

**New file:** `backend/tests/courses/test_video_tasks_hls_finalize.py`

**Test count:** 16 tests across 2 classes

### `TestTranscodeToHls` (9 tests)

| Test | Scenario |
|------|----------|
| `test_happy_path_sets_hls_master_url` | ffmpeg+upload succeed → `hls_master_url` set on asset AND mirrored to `Content.file_url` |
| `test_happy_path_invokes_ffmpeg_with_hls_args` | Verifies ffmpeg cmdline contains `-hls_time`, `-hls_playlist_type`, `vod`, and output `.m3u8` |
| `test_falls_back_to_default_master_key_when_not_in_upload_map` | Upload dict without `master.m3u8` key → synthesises `{hls_prefix}/master.m3u8` |
| `test_skips_already_failed_asset` | FAILED → no subprocess, no download; returns asset_id |
| `test_marks_failed_when_no_source_file` | Empty `source_file` → `status=FAILED`, message "missing source_file" |
| `test_marks_failed_when_ffmpeg_not_found` | `FileNotFoundError` from subprocess → FAILED with ffmpeg message |
| `test_marks_failed_on_ffmpeg_nonzero_exit` | `CalledProcessError` → FAILED, error_message includes "ffmpeg failed" |
| `test_retries_on_subprocess_timeout` | `TimeoutExpired` → `self.retry()` called, status NOT set to FAILED |
| `test_unexpected_exception_sets_status_failed_and_reraises` | Storage/unknown exception → asset marked FAILED and exception re-raised (Celery retry machinery) |

### `TestFinalizeVideoAsset` (7 tests)

| Test | Scenario |
|------|----------|
| `test_skips_already_failed_asset` | FAILED → early-return, status unchanged |
| `test_marks_failed_when_hls_missing` | No `hls_master_url` → FAILED with "HLS" in error message |
| `test_sets_ready_when_hls_present` | HLS + thumbnail → `status=READY`, `error_message` cleared |
| `test_ready_even_without_thumbnail` | HLS present, thumbnail missing → still READY (thumbnail is nice-to-have) |
| `test_logs_warning_when_ready_without_thumbnail` | When going READY without thumbnail, a WARNING-level log is emitted |
| `test_does_not_change_ready_asset_to_failed_when_thumbnail_missing` | Regression guard — thumbnail-less READY must never flip to FAILED |
| `test_raises_when_asset_does_not_exist` | Unknown `video_asset_id` → `VideoAsset.DoesNotExist` |

---

## Edge Cases Covered

- **Happy path:** successful ffmpeg run, storage upload, URL persistence, Content mirroring
- **Early-exit guards:** FAILED asset, missing source_file
- **External tool failures:** ffmpeg not installed, ffmpeg nonzero exit, ffmpeg timeout (→ retry)
- **Storage failures:** upload exception → asset FAILED and re-raised for Celery to track
- **Finalization gates:** HLS required (critical), thumbnail optional (warn only)
- **Invalid input:** non-existent asset id → DoesNotExist

## Still Untested / Out of Scope

- `_download_to_tempfile`, `_upload_dir`, `_safe_storage_url` — storage helpers;
  they're currently exercised indirectly via mocks. Could be covered with
  `FileSystemStorage`-backed tmpdir fixtures in a follow-up.
- Full orchestration `process_video_upload` chord/chain wiring — integration
  concern, likely needs Celery eager mode fixture.
- `_upload_dir` recursive vs non-recursive behavior — not tested.
- `generate_course_from_outline_async` (LLM orchestration) — separate task,
  not in the original 4-of-6 scope.

## Expected Coverage Delta

`apps/courses/tasks.py` is ~1160 LOC. `transcode_to_hls` (~75 LOC) and
`finalize_video_asset` (~15 LOC) represent ~90 previously-untouched lines plus
error branches. Estimated module delta: **+4–6 percentage points on
`apps/courses/tasks.py`**. Overall backend coverage delta: approximately
**+0.3 to +0.6 pp** (small because tasks.py is one module among many, and the
baseline is 43.7%). This does NOT on its own reach the 60% target — it chips
away at the tasks module gap; remaining gains come from views/services/signals.

---

## Verification Notes

- **Not run locally:** `pytest` is **pending Docker execution**. The test
  file follows the exact fixture + mock patterns of the sibling file
  `backend/tests/courses/test_video_tasks.py` (which was validated in earlier
  handoffs). All mocks target the same symbols in `apps.courses.tasks`.
- **Suggested command for reviewer:**

  ```bash
  docker compose exec web pytest backend/tests/courses/test_video_tasks_hls_finalize.py -v
  ```

- **No production code modified.** Only a new test file was added.
- **No git commands were run** (agent rule).
