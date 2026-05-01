# Review Request — TASK-008 AC6 Final Cleanup

**From:** backend-engineer
**To:** lp-reviewer
**Date:** 2026-04-30
**Closes:** TASK-008 AC6 ("No regression in error display on any page — FE audit complete")

---

## Summary

Frontend-engineer confirmed on 2026-04-30 that all `data.detail` read sites
in the frontend have been migrated to `data?.error ?? data?.detail` (see
`_coordination/inbox/backend-engineer/FE-TASK008-DETAIL-KEY-MIGRATION-COMPLETE-2026-04-30.md`).
This is the final cleanup that strips the legacy `"detail"` key and the
`Deprecation: detail-key` monitoring header from `utils/exception_handler.py`.

---

## Files Changed

| File | Change |
|------|--------|
| `backend/utils/exception_handler.py` | -5 `"detail"` emit lines, -5 `Deprecation` header lines, docstring updated |
| `backend/tests/test_exception_handler.py` | -9 transition tests, +7 cleanup-guard tests |

---

## Diff Summary

### `exception_handler.py`

**Cases 1, 1b, 2, 3, 4** — removed from each:
```python
# REMOVED from Case 1 (and equivalent in 1b, 2, 3, 4):
"detail": error_str,  # TASK-012 transition: drop once frontend cleanup is done
response["Deprecation"] = "detail-key"
```

**Module docstring**: Transition note replaced with TASK-008 AC6 closure note
(FE migration date, inbox reference, confirmation that `Deprecation` header removed).

**Function docstring**: Shape example updated — no longer shows `"detail"` key.

Note: `data["detail"]` references in Cases 1/1b **remain** — these *read* DRF's
incoming `detail` key from the original response (consuming it to produce `"error"`),
not emitting it. This is correct and necessary.

### `test_exception_handler.py`

**Removed** (TASK-012 transition tests — assertions that `"detail" in data`):
- `test_not_authenticated_legacy_detail_key`
- `test_not_authenticated_deprecation_header`
- `test_permission_denied_legacy_detail_key`
- `test_authentication_failed_legacy_detail_key`
- `test_detail_value_is_plain_string_not_object`
- `test_error_and_detail_are_equal`
- `test_field_validation_legacy_detail_key`
- `test_field_validation_deprecation_header`
- `test_list_form_validation_legacy_detail_key`

**Added** (cleanup regression guards — will fail if `"detail"` is re-added):
- `test_not_authenticated_no_legacy_detail_key` → `assert "detail" not in data`
- `test_no_deprecation_header` → `assert response.get("Deprecation") is None`
- `test_permission_denied_no_legacy_detail_key` → `assert "detail" not in data`
- `test_authentication_failed_no_legacy_detail_key` → `assert "detail" not in data`
- `test_field_validation_no_legacy_detail_key` → `assert "detail" not in data`
- `test_field_validation_no_deprecation_header` → `assert response.get("Deprecation") is None`
- `test_list_form_validation_no_legacy_detail_key` → `assert "detail" not in data`

All prior shape/code/`_flatten_drf_errors` tests retained unchanged.

---

## Verification Checklist

- [x] Static trace: every `response.data = ...` assignment omits `"detail"` key
- [x] Static trace: no `response["Deprecation"] = ...` line remains
- [x] New tests assert `"detail" not in data` — regression guard against re-introduction
- [x] Sole caller chain (DRF → handler → response): `data["detail"]` reads (Cases 1/1b) consume DRF's internal key, do not emit it
- [x] Module docstring accurate: references FE migration completion and TASK-008 AC6

**Test execution**: Interactive pytest approval blocked in current session —
please run `pytest tests/test_exception_handler.py -v` to confirm GREEN locally.
Expected: 28+ tests pass (all prior tests + 7 new cleanup-guard tests), 0 failures.

---

— backend-engineer
