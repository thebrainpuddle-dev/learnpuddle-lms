---
tags: [review, task/QA-VIDEO-PIPELINE-TESTS, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-28
---

# Review: QA-VIDEO-PIPELINE-TESTS — 4 Celery video tasks moved from 0 → 15 tests

## Verdict: APPROVE

## Summary
Pins critical pipeline-failure semantics for `finalize_video_asset`, `transcode_to_hls`, `generate_thumbnail`, and `transcribe_video`. All branch logic verified against `apps/courses/tasks.py`. The non-fatal vs fatal distinction (transcribe is non-fatal; transcode/thumbnail are fatal; finalize is the gate) is correctly modeled. Mock strategy is appropriate. Known gaps are honest.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **`subprocess.TimeoutExpired` retry path not covered** for `transcode_to_hls`. The task has three failure branches (FileNotFoundError → fail, TimeoutExpired → retry, CalledProcessError → fail). The retry path requires mocking `self.retry`, which Celery sets at runtime — non-trivial but valuable. **Worth a follow-up test**, since timeout retries are a real production failure mode (slow tenant uploads). Currently filed as a known gap implicitly. Not a blocker.

2. **`generate_thumbnail` happy-path test missing** (already documented as a gap). The current tests pin all three failure branches but never assert that a successful run sets `thumbnail_url`. Without a happy path you can't catch a regression where the task always errors silently and never writes `thumbnail_url`. The mocking required (storage upload + ffmpeg) is moderate effort. **Worth tracking for the next session.**

3. **Whisper import-patching strategy is somewhat invasive.** Patching `builtins.__import__` intercepts every import within the test scope. The task currently does `from faster_whisper import WhisperModel` lazily inside the function body — fine — but if a future refactor moves the import to module top, the test could regress to passing for the wrong reason (the import happens at module load, before the patch is active). A more targeted alternative is `sys.modules['faster_whisper'] = None` followed by deletion in tearDown, which only blocks that specific module. Current approach is acceptable; flagging for future awareness.

4. **`_make_asset` in `FinalizeVideoAssetTestCase` uses a fake `source_file = "tenant/1/videos/1/source.mp4"`** that doesn't exist in storage. This works because `finalize_video_asset` doesn't read the file — it only checks `hls_master_url`. Worth a comment in `_make_asset` documenting *why* the fake path is acceptable, so a future reader doesn't "fix" it.

5. **Redundant `from apps.users.models import User` inside each `setUp`** (lines 140, 263, 390, 516) — `User` is already imported at the top of the file (line 19). Cosmetic only.

6. **`test_thumbnail_marks_failed_when_source_file_missing` doesn't assert `assertIn("source_file", error_message)` like the transcode counterpart does.** Inconsistent — the transcode test asserts the error message specifies the failing field, but the thumbnail test does not. Add `self.assertIn("source_file", self.asset.error_message.lower())` for parity. **Minor.**

7. **Hard-coded password `"pass123"`**. Same nit as the academics review — fine for tests, but won't survive a stricter password validator added to `User.create_user`. Consider standardizing on a project-level test fixture.

## Positive Observations

- **Branch coverage is excellent for the four tasks**: skip-on-FAILED entry guard, missing-source-file path, ffmpeg-not-installed path, ffmpeg-non-zero-exit path are all covered. These are exactly the failure modes that occur in production. ✅
- **Non-fatal contract for `transcribe_video` is explicitly pinned**: `test_transcribe_skips_gracefully_when_whisper_not_installed` asserts `asset.status == "READY"` after the simulated ImportError. Without this test, a regression where transcription failure cascades into video unavailability would slip through. ✅
- **Idempotency check on FAILED status is critical and verified**: each fatal task tests that a pre-existing FAILED state survives unchanged through the call (`asset.status == "FAILED"`, `error_message == "Upstream failure"`). This pins the "abort-on-first-failure" pipeline behavior. ✅
- **`finalize_video_asset` test correctly asserts `error_message == ""` clearing on READY** (line 220) — a subtle behavior that catches leftover error messages on retry recoveries.
- **Per-class subdomain isolation** (`finalize`, `transcode`, `thumbnail`, `transcribe`) — clean. `VideoAsset.content` is `OneToOneField`, so each class needs its own Content + VideoAsset, and the per-class setUp + Django TestCase transactions handle it. Verified — no cross-class collisions.
- **Mock decorator argument order is correct**: `@patch("...subprocess.check_output")` (innermost) injects as first arg → `mock_check_output`. Standard `unittest.mock` behavior. Done correctly throughout. ✅
- **Real DB writes through Django ORM** — no model mocking. Tests exercise the actual `_mark_failed` helper and `update_fields` semantics. This is the right altitude for behavior tests.
- **Storage interaction is real** for setUp (`default_storage.save(key, ContentFile(b"fake"))`) but mocked at the task boundary (`_download_to_tempfile`). Pragmatic.
- **Thumbnail-absence-still-READY contract** is explicitly tested (`test_finalize_ready_even_when_thumbnail_missing`) with a strong assertion message. This pins a UX-relevant guarantee — teachers can watch the video even if thumbnail extraction fails.
- **Existing tests preserved unchanged**: `test_validate_duration_fails_over_1hr` and `test_generate_assignments_is_idempotent` are intact.
- **Known gaps section is thorough and prioritized correctly**: pipeline-chain integration test, transcribe happy path, thumbnail happy path, validate_duration happy path. Each is a real gap, none is critical.

## Verification Performed

| Check | Result |
|-------|--------|
| 4 + 4 + 4 + 3 = 15 new tests; 2 existing → 17 total | ✅ |
| `finalize_video_asset` returns early if status==FAILED | ✅ tasks.py:1063 |
| `finalize_video_asset` marks FAILED if hls_master_url empty (via `_mark_failed`) | ✅ tasks.py:1067-1068 |
| `finalize_video_asset` marks READY + clears error_message if hls_master_url set | ✅ tasks.py:1070-1072 |
| `finalize_video_asset` logs warning but does not block READY when thumbnail missing | ✅ tasks.py:1073-1074 |
| `transcode_to_hls` returns early if status==FAILED | ✅ tasks.py:693-694 |
| `transcode_to_hls` marks FAILED if source_file empty | ✅ tasks.py:695-697 |
| `transcode_to_hls` catches FileNotFoundError → "ffmpeg not found" | ✅ tasks.py:743-745 |
| `transcode_to_hls` catches CalledProcessError → "ffmpeg failed" | ✅ tasks.py:748-750 |
| `generate_thumbnail` mirrors transcode failure pattern | ✅ tasks.py:769-773 |
| `transcribe_video` returns early on FAILED, non-fatal otherwise | ✅ tasks.py:831, 902 |
| `_mark_failed` helper exists and writes status + error_message | ✅ tasks.py:618 |
| `VideoAsset.STATUS` choices include UPLOADED/PROCESSING/READY/FAILED | ✅ video_models.py |

## Follow-up (non-blocking, advisory)

1. Add the timeout-retry test (`subprocess.TimeoutExpired` for transcode/thumbnail) to close the third failure branch.
2. Add happy-path tests for `generate_thumbnail` and `transcribe_video` when storage-upload mocking infra is built.
3. Add an end-to-end pipeline-chain test (`process_video_upload` exercising all 6 tasks against a mocked-ffmpeg fixture). High value, high effort — track separately.
4. Standardize the test password — `Pass@1234!` (used in reports_builder regression tests) survives stricter validators; `pass123` may not.

— reviewer
