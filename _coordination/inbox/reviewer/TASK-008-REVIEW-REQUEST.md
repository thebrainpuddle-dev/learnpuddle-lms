# Review Request — TASK-008: Standardize Error Response Format

**Author:** backend-engineer
**Date:** 2026-04-20
**Priority:** P2 (Code Quality)
**Status:** ready-for-review

## Summary

Standardized API error response format so the frontend always receives a
consistent `{"error": "..."}` shape for DRF-generated errors.

## Changes

### 1. `utils/exception_handler.py` (NEW)

Custom DRF exception handler that renames DRF's auto-generated `"detail"` key
to `"error"` in all non-serializer-error responses. This normalizes:

```
Before: {"detail": "Authentication credentials were not provided."}
After:  {"error": "Authentication credentials were not provided."}
```

Serializer validation errors (`{"field": ["error"]}`) are intentionally
left unchanged so the frontend can continue to display per-field validation
messages in forms.

### 2. `config/settings.py` — register the handler

```python
REST_FRAMEWORK = {
    ...
    'EXCEPTION_HANDLER': 'utils.exception_handler.custom_exception_handler',
}
```

## Unchanged

- All `Response({"error": ...})` manual error responses — already in the
  correct format. `utils/responses.py` `error_response()` helper was already
  providing the canonical shape.
- Serializer field validation errors.
- Frontend error handling (TASK-012, pending frontend-engineer).

## Files Changed

| File | Change |
|------|--------|
| `backend/utils/exception_handler.py` | NEW — custom DRF exception handler |
| `backend/config/settings.py` | Register `EXCEPTION_HANDLER` |

## Acceptance Criteria

- [x] DRF auto-generated errors normalized: `{"detail":"..."}` → `{"error":"..."}`
- [x] Serializer field validation errors preserved as-is
- [x] All manual `Response({"error": ...})` calls remain valid (no change)
- [ ] Frontend error handling simplified — pending TASK-012 (frontend-engineer)

## Notes

Zero-risk change: the handler only renames a top-level `"detail"` key if
present; all other response shapes pass through unchanged.
