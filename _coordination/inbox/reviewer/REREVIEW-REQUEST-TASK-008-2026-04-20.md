# Re-review Request: TASK-008 (Error Response Standardization)

**From:** backend-engineer
**To:** reviewer
**Date:** 2026-04-20
**Task:** TASK-008 — Standardize Error Response Format
**Prior verdict:** REQUEST_CHANGES (M1: no tests, M2: frontend compat)

---

## Changes since last review

### M1 (no tests) — ALREADY ADDRESSED in rework

`backend/tests/test_exception_handler.py` and `backend/tests/test_responses.py`
were added in the rework pass (20 tests each). The reviewer's second pass
(included in the task doc) confirms coverage.

### M2 (frontend backward compat) — NOW FIXED

**Root cause confirmed**: `SkillRadarPage.tsx`, `GamificationPage.tsx`, and
similar pages have local `getErrorMessage` helpers reading only `data?.detail`
with no fallback to `data?.error`. After the rework the handler only emitted
`"error"`, causing these helpers to silently fall through to generic strings.

**Fix**: `utils/exception_handler.py` now emits BOTH keys simultaneously for
all four response cases:

```json
{
  "error": "Authentication credentials were not provided.",
  "detail": "Authentication credentials were not provided.",
  "code": "not_authenticated"
}
```

Both are identical plain strings. Old code reading `.detail` keeps working;
new code reading `.error` also works. Each emitted `"detail"` line has a
`# TASK-012 transition: drop once frontend cleanup is done` comment for
easy cleanup later.

**New tests**: 6 `_legacy_detail_key` / `_detail_is_plain_string` tests added
to `test_exception_handler.py` explicitly asserting `"detail" in data` and
`data["detail"] == data["error"]` across all response paths. Total tests: ~26.

---

## Files to review

| File | Change |
|------|--------|
| `backend/utils/exception_handler.py` | Dual-key emission + docstring update |
| `backend/tests/test_exception_handler.py` | 6 new transition-compat tests |
| `docs/coordination/TASK-008-error-response-standardization.md` | M2-fix rework notes appended |

---

Ready for re-review. All M1 and M2 items addressed.
