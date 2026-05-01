---
tags: [review, qa, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-30
---

# Review: QA Video Pipeline Test Tightening (`test_video_tasks.py`)

## Verdict: APPROVE

## Summary
Closes the non-blocking N1/N2 follow-ups from the 2026-04-29 batch review.
Two happy-path tests in `TestGenerateThumbnail` and `TestTranscribeVideo`
now assert DB persistence — not just task return values — which is exactly
the right hardening. Production code untouched.

## Verification performed
- `backend/tests/courses/test_video_tasks.py`

  **`test_happy_path_sets_thumbnail_url` (lines 223–253)**
  - After `generate_thumbnail(...)` runs, the test now calls
    `video_asset.refresh_from_db()` (line 246) and asserts
    `video_asset.thumbnail_url == "https://cdn.example.com/thumb.jpg"`
    (line 247) with a descriptive failure message.
  - Mock chain is sound: `mock_storage.url.return_value` is set before the
    call, and `_safe_storage_url` delegates through the patched
    `default_storage`. The DB assertion verifies the full round-trip:
    storage URL → assigned to attribute → persisted via
    `save(update_fields=[...])`.
  - This will catch any regression that drops the `save()` call or the
    `thumbnail_url` from `update_fields` — exactly the seam called out in
    `apps/courses/tasks.py` ~L767.

  **`test_happy_path_creates_transcript` (lines 342–394)**
  - After `transcribe_video(...)` runs, the test asserts:
    - `VideoTranscript.objects.filter(video_asset=video_asset).exists()` (line 384) — row created
    - `transcript.full_text == "Hello world"` (line 388) — segment-text accumulation/strip logic
    - `transcript.vtt_url == "https://cdn.example.com/captions.vtt"` (line 391) — VTT upload + URL persistence
    - `transcript.language == "en"` (line 394) — language detection plumbing
  - `VideoTranscript` is imported lazily inside the test method (line 347),
    consistent with the file's existing lazy-import pattern in other
    transcribe tests — good.
  - Mock-chain assertions target genuine production seams
    (`get_or_create`, `full_text` accumulation, VTT URL storage, `language`),
    not implementation internals. Each assertion has a meaningful failure
    message.

- All other tests in the file are unchanged (spot-checked
  `TestValidateDuration`, `TestGenerateAssignments`, and the FAILED/skip
  branches of `TestGenerateThumbnail`/`TestTranscribeVideo`).
- No production files modified — request states this and `git status` is
  consistent (no diff in `apps/courses/tasks.py` from this change).

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
None.

## Positive Observations
- Each new assertion comes with a descriptive failure string — when these
  fire in CI, the message alone tells the on-call what regressed.
- The tightening targets behaviour at the persistence boundary rather than
  internal call counts, which is exactly the right level of coupling.
- Lazy `VideoTranscript` import keeps the file consistent with the
  surrounding pattern instead of pulling the model into module scope just
  for one test.

## Action
- Mark the related QA follow-up note as **done**.
- No further work required on this file.

— lp-reviewer
