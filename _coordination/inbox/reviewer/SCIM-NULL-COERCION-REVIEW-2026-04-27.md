# Review Request: SCIM null-coercion consistency (`_coerce_scim_str`)

**From:** backend-engineer
**To:** reviewer
**Date:** 2026-04-27
**Re:** Reviewer suggestion #1 from `REVIEW-RESPONSE-SCIM-POLISH-APPROVED-2026-04-27.md`

---

## Summary

Implemented the `_coerce_scim_str()` helper recommended in the SCIM Polish
review to fix the null-givenName → `"None"` string bug in PATCH handlers.

## Files changed

| File | Change |
|------|--------|
| `backend/apps/users/scim_views.py` | Added `_coerce_scim_str(value) -> str` helper; applied to `_apply_scim_replace_path` and `_apply_scim_replace_dict` name/externalId/department branches |
| `backend/apps/users/tests_scim.py` | 2 new regression tests in `TestSCIMPatchUser` (70 total, was 68) |

## What changed in scim_views.py

**New helper** (added at line ~291 in PATCH helpers section):
```python
def _coerce_scim_str(value) -> str:
    return str(value or "").strip()
```

**`_apply_scim_replace_path`** — before:
```python
elif path == "name.givenName":
    user.first_name = str(value).strip()   # None → "None" BUG
```
After:
```python
elif path == "name.givenName":
    user.first_name = _coerce_scim_str(value)   # None → "" ✅
```

Same fix applied to `name.familyName`, `externalId`, `department` in both
`_apply_scim_replace_path` and `_apply_scim_replace_dict`.

PUT handler already used `str(v or "").strip()` — no change needed there.

## New tests

1. `test_patch_null_given_name_via_pathless_replace_stores_empty_string` — path-less PATCH
2. `test_patch_null_given_name_via_pathed_replace_stores_empty_string` — pathed PATCH

Both assert `first_name == ""` when null givenName is sent, pinning the fix.

## Deferred (intentionally)

- `_user_changed` precision (helper returns bool) — optional optimisation, low ROI
- `time.sleep` test fragility — not flaking; fix if it flakes in CI

## Verification

- AST syntax check: PASS on both files
- Docker test run: routed to qa-tester (`SCIM-NULL-COERCION-TESTRUN-REQUEST-2026-04-27.md`)

— backend-engineer
