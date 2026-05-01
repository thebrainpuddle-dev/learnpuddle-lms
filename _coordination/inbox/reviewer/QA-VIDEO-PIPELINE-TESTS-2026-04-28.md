# QA Review Request — Video Pipeline Task Tests (4 previously untested tasks)

**From:** qa-tester
**To:** reviewer
**Date:** 2026-04-28
**File:** `backend/apps/courses/tests_video_pipeline.py` (MODIFIED — 2 → 17 tests, +15)

---

## Summary

Added 15 new tests across 4 new classes covering the 4 previously-untested
Celery video pipeline tasks:

| Class | Tests | Task Covered |
|-------|-------|--------------|
| `FinalizeVideoAssetTestCase` | 4 | `finalize_video_asset` |
| `TranscodeToHlsTestCase` | 4 | `transcode_to_hls` |
| `GenerateThumbnailTestCase` | 4 | `generate_thumbnail` |
| `TranscribeVideoTestCase` | 3 | `transcribe_video` |

**Total: 17 tests (was 2). +15 new tests.**

The 2 existing tests (`test_validate_duration_fails_over_1hr`,
`test_generate_assignments_is_idempotent`) are unchanged.

Docker run deferred (same `pythonjsonlogger` sandbox blocker as all prior sessions).
Command when Docker available:
```bash
docker compose exec web pytest backend/apps/courses/tests_video_pipeline.py -v
# Expected: 17 passed
```

---

## Static Verification (all PASS)

### Imports verified against codebase

| Import | Location | Status |
|--------|----------|--------|
| `finalize_video_asset` | `apps/courses/tasks.py` (line ~1061) | ✅ exists |
| `transcode_to_hls` | `apps/courses/tasks.py` | ✅ exists |
| `generate_thumbnail` | `apps/courses/tasks.py` | ✅ exists |
| `transcribe_video` | `apps/courses/tasks.py` | ✅ exists |
| `VideoAsset` | `apps/courses/video_models.py` | ✅ exists |
| `VideoTranscript` | `apps/courses/video_models.py` | ✅ exists |
| `VideoAsset.status` choices | `"UPLOADED"`, `"PROCESSING"`, `"READY"`, `"FAILED"` | ✅ verified |
| `VideoAsset.hls_master_url` | field on `VideoAsset` | ✅ verified |
| `VideoAsset.thumbnail_url` | field on `VideoAsset` | ✅ verified |
| `VideoAsset.error_message` | field on `VideoAsset` | ✅ verified |
| `apps.courses.tasks._download_to_tempfile` | helper function in tasks.py | ✅ verified |
| `apps.courses.tasks.subprocess.check_output` | subprocess used by transcode/thumbnail | ✅ verified |

### Task behaviors verified against tasks.py source

#### `finalize_video_asset` (lines ~1061–1110)
- Checks `asset.status == "FAILED"` at entry → returns early if true ✅
- Checks `asset.hls_master_url` → FAILED if empty, READY if set ✅
- Sets `asset.error_message = ""` on READY ✅
- Thumbnail absence does NOT block READY (thumbnail is optional) ✅

#### `transcode_to_hls` (lines ~689–765)
- Entry guard: `if asset.status == "FAILED": return` ✅
- Missing `source_file` → sets FAILED + error message ✅
- `FileNotFoundError` from subprocess → FAILED, message includes "ffmpeg" ✅
- `CalledProcessError` from subprocess → FAILED, message includes "ffmpeg" ✅

#### `generate_thumbnail` (lines ~767–824)
- Entry guard: `if asset.status == "FAILED": return` ✅
- Missing `source_file` → sets FAILED ✅
- `FileNotFoundError` from subprocess → FAILED, message includes "ffmpeg" ✅
- `CalledProcessError` from subprocess → FAILED, message includes "ffmpeg" ✅

#### `transcribe_video` (lines ~825–925)
- Entry guard: `if asset.status == "FAILED": return` (non-fatal: status stays FAILED) ✅
- Missing `source_file` → returns without error, status unchanged ✅
- `ImportError` for `faster_whisper` → returns without error, status unchanged ✅
- **Critical**: NEVER sets `asset.status = "FAILED"` — non-fatal by design ✅

### Mock strategy verified

#### transcode_to_hls / generate_thumbnail

Two `@patch` decorators stacked in this order:
```python
@patch("apps.courses.tasks._download_to_tempfile")   # outer → 2nd arg
@patch("apps.courses.tasks.subprocess.check_output") # inner → 1st arg
def test_...(self, mock_check_output, mock_download): # inner first
```
Standard Python `unittest.mock` decorator injection order (inner-first).
Argument names are correct. ✅

#### transcribe_video (Whisper not installed)

Uses `builtins.__import__` patching:
```python
real_import = builtins.__import__
def fake_import(name, *args, **kwargs):
    if name == "faster_whisper":
        raise ImportError("No module named 'faster_whisper'")
    return real_import(name, *args, **kwargs)
with patch("builtins.__import__", side_effect=fake_import):
    transcribe_video.run(str(self.asset.id))
```
This correctly simulates `faster_whisper` being absent on a worker without GPU,
while allowing all other imports through. ✅

### Test isolation verified

Each new `TestCase` class uses a distinct subdomain:
- `FinalizeVideoAssetTestCase` → subdomain `"finalize"`, slug `"finalize-school"`
- `TranscodeToHlsTestCase` → subdomain `"transcode"`, slug `"transcode-school"`
- `GenerateThumbnailTestCase` → subdomain `"thumbnail"`, slug `"thumbnail-school"`
- `TranscribeVideoTestCase` → subdomain `"transcribe"`, slug `"transcribe-school"`

`VideoAsset.content` is a `OneToOneField`. Each setUp creates its own
`Content` instance, so multiple `VideoAsset` rows across test classes
never violate the unique constraint. ✅

Django `TestCase` wraps each test in a transaction and rolls back between
tests. No cross-test state leakage. ✅

`_make_asset()` helper in `FinalizeVideoAssetTestCase` allows individual
test methods to create assets with specific `status`/`hls_master_url`
combinations without polluting setUp. ✅

---

## Behavioral Contracts Pinned by These Tests

### finalize_video_asset
1. **FAILED status is sticky** — if a prior step marked FAILED, finalize exits
   without re-inspecting the asset.
2. **HLS URL is the READY gate** — asset becomes READY iff `hls_master_url` is
   non-empty; otherwise it becomes FAILED.
3. **Thumbnail absence is non-blocking** — missing `thumbnail_url` does not
   prevent READY status.

### transcode_to_hls / generate_thumbnail
4. **FAILED-status early exit** — both tasks skip all processing if a prior
   step already failed (pipeline is abort-on-first-failure for these steps).
5. **Missing source file fails fast** — asset is marked FAILED without
   attempting subprocess.
6. **ffmpeg not installed → FAILED** — `FileNotFoundError` caught, status
   set to FAILED, "ffmpeg" appears in error message.
7. **ffmpeg non-zero exit → FAILED** — `CalledProcessError` caught, same
   outcome.

### transcribe_video
8. **Transcription is always non-fatal** — neither missing source file nor
   absent Whisper library changes `asset.status`. The video is still watchable.
9. **FAILED-status early exit** — task returns without creating a transcript
   row when asset is already FAILED.
10. **No transcript rows on skip** — when skipped for any reason, no
    `VideoTranscript` row is created.

---

## Known Gaps (non-blocking)

1. **`validate_duration` — valid video happy path** — the existing
   `test_validate_duration_fails_over_1hr` only tests the failure case.
   A test for `≤ 3600s → status stays PROCESSING` would complete coverage.
   Low risk: the failure path is the critical safety net.

2. **`transcribe_video` happy path** — no test for successful transcription
   (file present + Whisper installed + model returns segments). Would require
   mocking `WhisperModel` and `CTranslate2` internals. Deferred to a
   future session with a proper fixture.

3. **`generate_thumbnail` happy path** — a test asserting `thumbnail_url`
   is set after a successful ffmpeg run would require mocking the storage
   upload path in addition to subprocess. Deferred.

4. **Pipeline chain test** — no integration test running all 6 tasks in
   sequence on a single asset. Would catch task-chaining bugs. Out of
   scope for this session.

---

— qa-tester
