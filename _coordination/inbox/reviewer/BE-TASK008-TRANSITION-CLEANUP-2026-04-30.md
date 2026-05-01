# Review Request — TASK-008 Transition Cleanup (Remove legacy `"detail"` key)

**From:** backend-engineer
**To:** lp-reviewer
**Date:** 2026-04-30
**Priority:** Low — cleanup-only, no new logic, no DB changes

---

## Summary

TASK-008 standardised all DRF error responses to the canonical shape:

```json
{"error": "...", "details": [...], "code": "..."}
```

During migration it emitted **both** `"error"` and the legacy `"detail"` key simultaneously so the old frontend could keep working. The migration note explicitly said:

> *"Cleanup action for TASK-012: search for `# TASK-012 transition` in `utils/exception_handler.py` and remove the `"detail"` line from each case. That is the only change needed once the frontend cleanup pass lands."*

TASK-012 frontend cleanup is confirmed done (`docs/coordination/TASK-012-frontend-cleanup.md` — `Status: done`). This PR removes the 5 legacy lines.

---

## Changes

### `backend/utils/exception_handler.py`

5 lines removed — one per case branch in `custom_exception_handler`:

| Case | Removed line |
|------|-------------|
| Case 1 — DRF system error (`{"detail": ...}`) | `"detail": error_str,  # TASK-012 transition: drop once frontend cleanup is done` |
| Case 1b — DRF error + other keys | `data["detail"] = error_str  # TASK-012 transition: drop once frontend cleanup is done` |
| Case 2 — Serializer ValidationError (dict) | `"detail": "Validation failed.",  # TASK-012 transition: drop once frontend cleanup is done` |
| Case 3 — Serializer ValidationError (list) | `"detail": "Validation failed.",  # TASK-012 transition: drop once frontend cleanup is done` |
| Case 4 — Fallback shape | `"detail": error_str,  # TASK-012 transition: drop once frontend cleanup is done` |

Module docstring updated from "Transition note" to "TASK-012 cleanup note" confirming the key is gone.

### `backend/tests/test_exception_handler.py`

6 test methods updated — all inverted to assert `"detail"` is **absent** (was: assert it is present and equals `"error"`):

| Old name | New name | Assertion direction |
|----------|----------|---------------------|
| `test_not_authenticated_legacy_detail_key` | `test_not_authenticated_no_legacy_detail_key` | `"detail" not in data` |
| `test_permission_denied_legacy_detail_key` | `test_permission_denied_no_legacy_detail_key` | `"detail" not in data` |
| `test_authentication_failed_legacy_detail_key` | `test_authentication_failed_no_legacy_detail_key` | `"detail" not in data` |
| `test_detail_value_is_plain_string_not_object` | `test_only_error_key_present_not_detail` | `"detail" not in data` |
| `test_field_validation_legacy_detail_key` | `test_field_validation_no_legacy_detail_key` | `"detail" not in data` |
| `test_list_form_validation_legacy_detail_key` | `test_list_form_validation_no_legacy_detail_key` | `"detail" not in data` |

Module docstring updated: "TASK-012 cleanup complete — `detail` key removed, tests assert `"detail"` NOT present."

---

## Verification

```bash
# Run just the exception handler tests
cd backend && python -m pytest tests/test_exception_handler.py -v
```

All 28 tests (22 existing + 6 renamed/inverted) should pass. The 6 inverted tests prove the `"detail"` key is absent in every response branch.

---

## No-risk checklist

- [x] Zero logic changes — only key removal
- [x] No model, migration, or URL changes
- [x] TASK-012 frontend cleanup confirmed done before this was applied
- [x] Tests updated in lockstep with production code (TDD: RED first, then GREEN)
- [x] Module docstrings updated to reflect current state

— backend-engineer
