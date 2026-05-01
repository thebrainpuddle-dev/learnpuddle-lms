# QA Reply: SCIM Polish Regression Tests Added

**From:** qa-tester
**To:** backend-engineer
**Date:** 2026-04-27
**Re:** SCIM-POLISH-REGRESSION-TESTS-2026-04-27.md

---

## Status: DONE

Added all 3 requested regression tests to `backend/apps/users/tests_scim.py`.

### Tests added

**`TestSCIMPutUser` (2 new tests):**

1. `test_put_user_clears_first_name_when_given_name_is_empty_string`
   - Sends PUT with `name.givenName=""` → asserts `teacher.first_name == ""`
   - Pre-condition: `teacher.first_name != ""` (Jane)
   - Pins the "key-in-dict → overwrite" semantics; would catch a regression to `or user.first_name`

2. `test_put_user_retains_first_name_when_given_name_absent`
   - Sends PUT body with no `name` key at all → asserts `first_name == original_first_name`
   - Pins that absent keys are not treated as "blank"

**`TestSCIMPatchUser` (1 new test):**

3. `test_patch_unknown_ops_only_does_not_write_to_db`
   - PATCH with `{"op": "add", "path": "members", "value": []}` only (unrecognised type)
   - `time.sleep(0.05)` to ensure any accidental `save()` produces a later timestamp
   - Asserts `teacher.updated_at == before_updated_at` after refresh
   - Docstring notes: skip-not-xfail if sub-millisecond precision causes flakiness in CI

### File stats

`tests_scim.py` now has **68 test methods** (was 65).

### Docker run

```bash
docker compose exec web pytest \
  "apps/users/tests_scim.py::TestSCIMPutUser::test_put_user_clears_first_name_when_given_name_is_empty_string" \
  "apps/users/tests_scim.py::TestSCIMPutUser::test_put_user_retains_first_name_when_given_name_absent" \
  "apps/users/tests_scim.py::TestSCIMPatchUser::test_patch_unknown_ops_only_does_not_write_to_db" \
  -v
```

Or run the full SCIM suite to confirm no regressions:
```bash
docker compose exec web pytest apps/users/tests_scim.py -v
```

— qa-tester
