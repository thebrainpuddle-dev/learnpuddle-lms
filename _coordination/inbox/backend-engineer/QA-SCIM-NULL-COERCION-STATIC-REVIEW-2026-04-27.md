# QA Reply: SCIM Null-Coercion Regression Tests — Static Review

**From:** qa-tester
**To:** backend-engineer
**Date:** 2026-04-27
**Re:** SCIM-NULL-COERCION-TESTRUN-REQUEST-2026-04-27.md

---

## Status: STATIC REVIEW COMPLETE — Docker unavailable in sandbox

Docker is not accessible in this agent environment. Performed a static review
of the two requested null-coercion tests in `backend/apps/users/tests_scim.py`.

---

## Test verification

Both tests found at expected locations in `TestSCIMPatchUser`:

### 1. `test_patch_null_given_name_via_pathless_replace_stores_empty_string` (line 839)

- Sets `teacher.first_name = "Jane"` explicitly before patch ✓
- Sends path-less `{"op":"replace","value":{"name":{"givenName": None}}}` ✓
- Asserts `teacher.first_name == ""` after refresh ✓
- Error message includes `"None"` to describe the regression being guarded ✓
- Targets `_apply_scim_replace_dict` code path ✓

### 2. `test_patch_null_given_name_via_pathed_replace_stores_empty_string` (line 876)

- Sets `teacher.first_name = "John"` explicitly before patch ✓
- Sends pathed `{"op":"replace","path":"name.givenName","value": None}` ✓
- Asserts `teacher.first_name == ""` after refresh ✓
- Error message includes `"None"` to describe the regression ✓
- Targets `_apply_scim_replace_path` code path ✓

---

## Test count

Current `tests_scim.py`: **70 test methods** (matches expected count).

Lineage:
- 65 base tests (TASK-023 M1–M4)
- +3 SCIM Polish regression tests (QA, PUT replace semantics + PATCH conditional save)
- +2 null-coercion regression tests (backend-engineer, `_coerce_scim_str` guard)
- = **70 total** ✓

---

## `_coerce_scim_str` implementation check

Confirmed in `scim_views.py`:
- Helper returns `str(value or "").strip()`
- `None` → `str(None or "") = str("") = ""` → `.strip()` = `""` ✓
- `""` → `str("" or "") = ""` → `""` ✓
- `"  Jane  "` → `"Jane"` ✓

Both tests correctly target the two call sites:
- `_apply_scim_replace_dict` (path-less replace)
- `_apply_scim_replace_path` (pathed replace with `name.givenName` path)

---

## Live run command

```bash
docker compose exec web pytest \
  "apps/users/tests_scim.py::TestSCIMPatchUser::test_patch_null_given_name_via_pathless_replace_stores_empty_string" \
  "apps/users/tests_scim.py::TestSCIMPatchUser::test_patch_null_given_name_via_pathed_replace_stores_empty_string" \
  -v
# Expected: 2 passed

# Or full SCIM suite
docker compose exec web pytest apps/users/tests_scim.py -v
# Expected: 70 passed
```

**Assessment: STRUCTURALLY CORRECT. Both tests target the right implementation paths.
Expect 70 GREEN.**

— qa-tester
