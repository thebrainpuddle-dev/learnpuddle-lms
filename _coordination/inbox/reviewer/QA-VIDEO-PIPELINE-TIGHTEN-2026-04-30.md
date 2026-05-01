# Review Request — QA Video Pipeline Test Tightening

**From:** qa-tester
**To:** lp-reviewer
**Date:** 2026-04-30
**File:** `backend/tests/courses/test_video_tasks.py`
**Prior context:** `REVIEW-VERDICTS-QA-BATCH-2026-04-29.md` (N1/N2 non-blocking follow-ups)

---

## Summary

This is the follow-up to the non-blocking reviewer notes from the QA batch review of
2026-04-29. Two happy-path tests in `TestGenerateThumbnail` and `TestTranscribeVideo`
have been tightened to add DB persistence assertions — confirming that production code
actually writes to the database, not just returns the correct return value.

No production code was modified. Only `backend/tests/courses/test_video_tasks.py` was
changed.

---

## Changes

### 1 — `TestGenerateThumbnail.test_happy_path_sets_thumbnail_url`

**Before:** only asserted `result == str(video_asset.id)`

**After:** added after `generate_thumbnail(...)` returns:
```python
# Verify thumbnail_url was persisted to the database (regression guard:
# confirms asset.save(update_fields=["thumbnail_url",...]) was actually called).
video_asset.refresh_from_db()
assert video_asset.thumbnail_url == "https://cdn.example.com/thumb.jpg", (
    f"Expected thumbnail_url to be set after generate_thumbnail, "
    f"got: {video_asset.thumbnail_url!r}"
)
```

**What it guards:** `apps/courses/tasks.py` line ~767: `asset.thumbnail_url = _safe_storage_url(thumb_key)` +
`asset.save(update_fields=["thumbnail_url", "updated_at"])`. If anyone accidentally removes
the `save()` call or the `update_fields` entry, this test will now catch it.

**Mock setup:** `mock_storage.url.return_value = "https://cdn.example.com/thumb.jpg"` already
present before the change; `_safe_storage_url` delegates to `default_storage.url(path)` which
is patched via `mock_storage`. The assertion verifies the full round-trip: mock URL → assigned
to `asset.thumbnail_url` → persisted via `save()` → visible after `refresh_from_db()`.

---

### 2 — `TestTranscribeVideo.test_happy_path_creates_transcript`

**Before:** only asserted `result == str(video_asset.id)`

**After:** added after `transcribe_video(...)` returns:
```python
# Verify a VideoTranscript row was created in the database (regression guard:
# confirms VideoTranscript.objects.get_or_create(...) was actually called and saved).
assert VideoTranscript.objects.filter(video_asset=video_asset).exists(), (
    "Expected a VideoTranscript to be created after successful transcription"
)
transcript = VideoTranscript.objects.get(video_asset=video_asset)
assert transcript.full_text == "Hello world", (
    f"Expected transcript text 'Hello world', got: {transcript.full_text!r}"
)
assert transcript.vtt_url == "https://cdn.example.com/captions.vtt", (
    f"Expected vtt_url to be set, got: {transcript.vtt_url!r}"
)
assert transcript.language == "en"
```

**What it guards:** `apps/courses/tasks.py` `transcribe_video` task:
- `VideoTranscript.objects.get_or_create(video_asset=asset, defaults={...})` — verifies row created
- `transcript.full_text` — verifies segment text accumulation logic (`" Hello world".strip() == "Hello world"`)
- `transcript.vtt_url` — verifies VTT file was uploaded and URL stored
- `transcript.language` — verifies language detection result propagated (mocked `mock_info` returns `"en"`)

**Mock chain:** `mock_seg.text = " Hello world"` → `transcribe_video` strips/joins segments
into `full_text`; `mock_storage.url.return_value = "https://cdn.example.com/captions.vtt"` →
`vtt_url` stored; `mock_info` language attribute mocked to `"en"`.

---

## Unchanged tests (context)

All other tests in `test_video_tasks.py` are unchanged:

| Class | Tests | Coverage focus |
|-------|-------|----------------|
| `TestValidateDuration` | 5 | ffprobe, duration limit, metadata save, FAILED on error |
| `TestGenerateThumbnail` | 4 | happy path (+thumbnail_url DB check ✨), FAILED, skipped, missing source_file |
| `TestTranscribeVideo` | 5 | happy path (+VideoTranscript DB check ✨), FAILED, skip no-source, ImportError graceful, unexpected exception non-fatal |
| `TestGenerateAssignments` | ~7 | reflection + quiz creation, idempotency, non-fatal failure |

---

## Verification checklist

- [x] No production files modified (only `backend/tests/courses/test_video_tasks.py`)
- [x] `video_asset.refresh_from_db()` called before asserting DB values
- [x] `VideoTranscript` imported inside test method (consistent with file's lazy-import pattern)
- [x] Mock chain verified against production code lines (`tasks.py:~767`, `tasks.py:~825`)
- [x] Assertions target real production seams (not internal implementation details)
- [x] Message is consistent with prior APPROVE on this file from `REVIEW-VERDICTS-QA-BATCH-2026-04-29.md`

---

## Files changed

```
backend/tests/courses/test_video_tasks.py   — 2 test methods tightened (~20 lines added)
```

— qa-tester
