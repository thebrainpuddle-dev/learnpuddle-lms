# QA Request: SCIM Null-Coercion Regression Tests

**From:** backend-engineer
**To:** qa-tester
**Date:** 2026-04-27
**Priority:** Non-blocking polish

**STATUS: PROCESSED 2026-04-27 by qa-tester.** Both null-coercion tests verified
present at `backend/apps/users/tests_scim.py` lines 890 and 927. Docker run
deferred (pythonjsonlogger missing from host Python 3.13 + no Docker in sandbox).
Command: `docker compose exec web pytest apps/users/tests_scim.py -v` (expect 70 pass).

---

## What was changed

Implemented reviewer suggestion #1 from `REVIEW-RESPONSE-SCIM-POLISH-APPROVED-2026-04-27.md`:
extracted `_coerce_scim_str()` helper in `backend/apps/users/scim_views.py` to fix
null-givenName producing the literal string `"None"` in the database.

## New tests to run (2 tests)

```bash
docker compose exec web pytest \
  "apps/users/tests_scim.py::TestSCIMPatchUser::test_patch_null_given_name_via_pathless_replace_stores_empty_string" \
  "apps/users/tests_scim.py::TestSCIMPatchUser::test_patch_null_given_name_via_pathed_replace_stores_empty_string" \
  -v
```

Or run the full SCIM suite to confirm no regressions:

```bash
docker compose exec web pytest apps/users/tests_scim.py -v
```

Expected: **70 tests pass** (was 68 before this session).

## What the tests cover

1. **path-less PATCH** with `{"givenName": null}` → `first_name == ""` not `"None"`
2. **pathed PATCH** with `value: null` → `first_name == ""` not `"None"`

Both test the `_coerce_scim_str()` helper via the two PATCH code paths
(`_apply_scim_replace_dict` and `_apply_scim_replace_path`).

— backend-engineer
