---
tags: [review, task/TASK-008, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-30
---

# Review: TASK-008 AC6 — Final Cleanup (Drop legacy `detail` key + `Deprecation` header)

## Verdict: APPROVE

## Summary
Surgical, well-justified cleanup that completes TASK-008 AC6 now that the
frontend migration has been confirmed. The legacy `detail` emit lines and the
`Deprecation: detail-key` monitoring header are gone, and the test suite has
been re-shaped from "transition assertions" into "regression guards" that
will fail loudly if anyone re-adds the legacy key.

## Verification performed
Inspected files directly (no git writes):

- `backend/utils/exception_handler.py`
  - Cases 1, 1b, 2, 3, 4: every `response.data = {...}` assignment now omits
    the `"detail"` key. Confirmed by reading lines 134–186.
  - No `response["Deprecation"] = ...` line remains anywhere in the module.
  - Docstring (lines 15–21) accurately documents the cleanup, references the
    FE migration confirmation note, and notes the header removal.
  - `data["detail"]` *reads* in Cases 1 (line 138) and 1b (line 152) are
    correctly retained — these consume DRF's incoming key to produce the
    canonical `error`. As the request notes, this is the right boundary.

- `backend/tests/test_exception_handler.py`
  - All 9 transition tests asserting presence of `"detail"` are gone.
  - 7 new cleanup-guard tests are present and assert the absence of the
    legacy key and header, e.g.:
    - `test_not_authenticated_no_legacy_detail_key` (line 70) — `assert "detail" not in response.data`
    - `test_no_deprecation_header` (line 78) — `assert response.get("Deprecation") is None`
    - `test_permission_denied_no_legacy_detail_key` (line 92)
    - `test_authentication_failed_no_legacy_detail_key` (line 133)
    - `test_field_validation_no_legacy_detail_key` (line 165)
    - `test_field_validation_no_deprecation_header` (line 173)
    - `test_list_form_validation_no_legacy_detail_key` (line 214)
  - All other shape/code/`_flatten_drf_errors` tests retained unchanged.
  - Module docstring (lines 12–18) explains the cleanup state.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
None blocking. One nice-to-have for a future pass:

- m1 (optional): Consider also asserting `assert response.data["error"]` is
  populated alongside the negative-guard tests (i.e. positive + negative in
  one test) so a future regression that drops *both* keys still fails loudly.
  The existing `test_not_authenticated_shape` already covers the positive
  side, so this is purely tightening — non-blocking.

## Positive Observations
- Test rename is semantically correct: "no_legacy_detail_key" makes the
  intent of each guard test obvious in failure output.
- Module + test docstrings both reference the FE-confirmation note path,
  which leaves a clear audit trail for future readers.
- The distinction between *reading* DRF's internal `detail` key (kept) and
  *emitting* it (removed) is called out explicitly in the request and is
  correct in the code.
- No production behaviour changes for non-error paths — purely a response
  shape simplification on the error path.

## Action
- TASK-008 AC6 → **status/done**.
- No follow-ups required.

— lp-reviewer
