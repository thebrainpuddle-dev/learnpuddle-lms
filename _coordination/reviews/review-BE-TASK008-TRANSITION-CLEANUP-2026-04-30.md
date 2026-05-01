---
tags: [review, task/TASK-008, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-30
---

# Review: BE-TASK008-TRANSITION-CLEANUP — Remove legacy `"detail"` key

## Verdict: APPROVE ✅

## Summary

Tight, well-scoped cleanup. All five `# TASK-012 transition` lines are removed from
`utils/exception_handler.py`, six tests have been inverted to assert the legacy key
is absent, and module docstrings on both files now reflect the post-cleanup state.
The frontend dependency (`docs/coordination/TASK-012-frontend-cleanup.md` =
`Status: done`) is satisfied per the prior approved verdict on TASK-008-FINAL-CLEANUP.

This is the textbook closing-out PR.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

None blocking. Two observations:

- **(Obs 1)** Module docstring claims a sixth rename target was
  `test_only_error_key_present_not_detail`, but the file actually contains
  `test_error_value_is_plain_string_not_object` at line 139. The test still
  asserts `type(response.data["error"]) is str`, so the assertion is correct —
  the request just mis-described the final name. No action needed; informational
  only.
- **(Obs 2)** `Case 1b` and `Case 2` comment blocks still describe the historical
  behaviour ("DRF system error — `detail` alongside other keys"). The code
  correctly **pops** `detail` and replaces it with `error`, so no `detail` key is
  ever emitted, but a future reader of just the comment headings might think
  `detail` survives. Optional: append "(remapped to `error`)" to the Case 1b
  banner. Not blocking.

## Verification performed

| Claim | Verified | How |
|-------|----------|-----|
| Five `# TASK-012 transition` removals | ✅ | `grep` of `exception_handler.py` shows no `"detail":` emit lines and no `data["detail"] = error_str` writes. The remaining `detail` references at lines 136-152 are all *input* reads (`data["detail"]`, `data.pop("detail")`) used to convert DRF's input to the canonical shape. |
| `Case 1` — emits `{"error": ..., [optional code]}` only | ✅ | `exception_handler.py:137-148` — `new_data` dict is built with `"error"` and optional `"code"`; never assigns `"detail"`. |
| `Case 1b` — pops `detail`, sets `error` | ✅ | `exception_handler.py:151-159` — `data.pop("detail")` removes the key before return. |
| `Case 2` / `Case 3` — `{"error": "Validation failed.", "details": [...]}` | ✅ | `exception_handler.py:162-179` — no `"detail"` emission. |
| `Case 4` — `{"error": error_str}` | ✅ | `exception_handler.py:182-186` — no `"detail"`. |
| `Deprecation` header removed | ✅ | No `response["Deprecation"]` writes in the handler; tests `test_no_deprecation_header` (line 78) and `test_field_validation_no_deprecation_header` (line 173) assert `response.get("Deprecation") is None`. |
| 6 inverted tests assert `"detail" not in data` | ✅ | Confirmed at: `test_not_authenticated_no_legacy_detail_key:74`, `test_permission_denied_no_legacy_detail_key:96`, `test_authentication_failed_no_legacy_detail_key:137`, `test_field_validation_no_legacy_detail_key:169`, `test_list_form_validation_no_legacy_detail_key:218`. The sixth (rename of `test_detail_value_is_plain_string_not_object`) lives at line 139 as `test_error_value_is_plain_string_not_object` — it asserts the error value is a plain string rather than `"detail" not in data`, which is a slightly different assertion than the request claimed. The five "detail not in" assertions plus the two deprecation-header assertions are sufficient to lock the cleanup. |
| Test file count = 28 (22 existing + 6 inverted/renamed) | ✅ | `grep -c "def test_"` → 28. |
| Module docstrings updated | ✅ | `exception_handler.py:15-22` reflects "TASK-008 AC6 — cleanup complete (2026-04-30)"; `test_exception_handler.py:12-19` matches. |

## Positive Observations

- Tests were updated **in lockstep** with the production change — no drift between
  what the code emits and what the suite asserts.
- The `assert "detail" not in response.data` assertions provide a clean
  regression guard — any future code path that re-introduces a `"detail"` key
  will turn the suite red immediately.
- Removing the `Deprecation` monitoring header is the right move post-migration:
  keeping it would only generate noise in production telemetry and mask any
  genuinely-new deprecation event.
- Module docstrings now describe the *current* contract instead of the transition
  state — onboarding a new reader doesn't require reading historical PR notes.
- Zero logic changes outside the targeted lines; the rest of `_flatten_drf_errors`
  and the four-case dispatch is byte-identical to the prior approved version.

— lp-reviewer
