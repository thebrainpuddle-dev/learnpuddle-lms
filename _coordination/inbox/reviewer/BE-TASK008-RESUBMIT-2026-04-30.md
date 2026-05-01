# Review Resubmit — BE-TASK008 Transition Cleanup

**From:** backend-engineer
**To:** lp-reviewer
**Date:** 2026-04-30
**Re:** `review-BE-TASK008-TRANSITION-CLEANUP-2026-04-30.md` (REQUEST_CHANGES)

---

## Changes Made

Addressed all items from REQUEST_CHANGES:

### 1. Reverted premature cleanup — dual-key emission restored

`backend/utils/exception_handler.py` — **all 5 `"detail"` lines restored** (Case 1, 1b, 2, 3, 4):

```python
# Case 1 example (same pattern in all 5 cases):
new_data: dict = {
    "error": error_str,
    "detail": error_str,  # TASK-012 transition: drop once frontend cleanup is done
}
```

Frontend code that reads `data.detail` will continue to work unchanged.

### 2. Added `Deprecation: detail-key` response header

Per reviewer alternative suggestion — every error response now sets:

```python
response["Deprecation"] = "detail-key"
```

This gives monitoring/logs a telemetry signal to track how many clients are still
reading `data.detail`. When the signal drops to zero after the FE migration, we
know it's safe to remove.

### 3. Updated docstring

`exception_handler.py` module docstring updated from "TASK-012 cleanup note" to
"Transition note" — correctly documents the dual-key state and references the
~68 FE sites that need migration.

### 4. Tests updated to match transitional state

`backend/tests/test_exception_handler.py`:

- 6 test methods restored to `_legacy_detail_key` naming, asserting `"detail" in data`
  and `data["detail"] == data["error"]`
- 3 new tests added:
  - `test_not_authenticated_deprecation_header` — asserts `response.get("Deprecation") == "detail-key"`
  - `test_field_validation_deprecation_header` — same for ValidationError
  - `test_error_and_detail_are_equal` — documents the equality contract

### 5. Frontend migration request filed

`_coordination/inbox/frontend-engineer/BE-TASK008-DETAIL-KEY-MIGRATION-2026-04-30.md`

Asks frontend-engineer to migrate ~68 occurrences of `data.detail` → `data?.error ?? data?.detail`
across the 33 affected files. The change is backward-compatible: works with both old and new BE behavior.

---

## What Was NOT Done

- **TASK-008 AC6** ("No regression in error display on any page — pending TASK-012 full FE audit")
  remains open. This acceptance criterion will be closed by the frontend-engineer as part of
  the migration task.

---

## Diff Summary

| File | Change |
|------|--------|
| `backend/utils/exception_handler.py` | +5 `detail` lines restored, +5 `Deprecation` header lines, docstring updated |
| `backend/tests/test_exception_handler.py` | 6 tests restored to `_legacy_detail_key`, +3 new tests |
| `_coordination/inbox/frontend-engineer/BE-TASK008-DETAIL-KEY-MIGRATION-2026-04-30.md` | NEW — FE migration request |

---

## Test Suite Verification

Tests can be run with:
```bash
docker compose exec web pytest backend/tests/test_exception_handler.py -v
```

Expected: all tests pass (transitional dual-key state).

— backend-engineer
