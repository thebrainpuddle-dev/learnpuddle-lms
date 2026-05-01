# SCIM Test Run Results — 2026-04-23

**Runner:** Claude Agent (claude-sonnet-4-6)
**Branch:** maic-sprint-1-presence-rhythm
**Django version:** 5.2.11 (venv: Python 3.13.3, pytest 7.4.4)

---

## Suite A — `apps/users/tests_scim_groups.py`

**Result: 37 passed / 0 failed / 0 errors**

All 37 tests passed in 253s.

Classes covered:
- TestSCIMGroupAuthentication (5 tests)
- TestSCIMListGroups (6 tests)
- TestSCIMCreateGroup (6 tests)
- TestSCIMGetGroup (4 tests)
- TestSCIMPutGroup (4 tests)
- TestSCIMPatchGroup (6 tests)
- TestSCIMDeleteGroup (3 tests)
- TestSCIMServiceProviderConfigGroups (3 tests)

---

## Suite B — `apps/users/tests_scim_cross_tenant.py`

**Result: 37 passed / 0 failed / 0 errors** (after test-file fix; initial run had 2 failures)

All 37 tests passed in 225s.

---

## Production Bugs Discovered

None. Both failures were test-file bugs.

---

## Test-File Fixes Applied

### Fix 1 — Both files: `@override_settings` class decorator incompatible with Django 5.x

**Files:**
- `backend/apps/users/tests_scim_groups.py`
- `backend/apps/users/tests_scim_cross_tenant.py`

**Root cause:** In Django 5.x, `@override_settings` can only be used as a class decorator on subclasses of `django.test.SimpleTestCase`. These test files used plain Python classes with `pytestmark = pytest.mark.django_db`. This caused `ValueError: Only subclasses of Django SimpleTestCase can be decorated with override_settings` at collection time (1 collection error per file, 0 tests run).

**Fix:** Removed all `@override_settings(**ALLOWED_HOST_SETTINGS)` class-level decorators from both files (8 in Suite A, 13 in Suite B). The `ALLOWED_HOSTS=["*"]` and `PLATFORM_DOMAIN` settings are already provided globally by the `override_allowed_hosts` autouse fixture in `backend/conftest.py` (sets `PLATFORM_DOMAIN = "lms.com"`), making the per-class `@override_settings` redundant.

Also removed the now-unused `ALLOWED_HOST_SETTINGS` dict definition and `from django.test import ... override_settings` import from both files.

### Fix 2 — Suite B: hardcoded `lms.test` domain in `TestAdminTokenListCrossTenantIsolation._make_jwt_client`

**File:** `backend/apps/users/tests_scim_cross_tenant.py`, line 643

**Root cause:** The `_make_jwt_client` helper constructed `HTTP_HOST: {subdomain}.lms.test`. After removing the class-level `@override_settings(PLATFORM_DOMAIN="lms.test")`, the active `PLATFORM_DOMAIN` became `"lms.com"` (from conftest). TenantMiddleware couldn't resolve the tenant from `{subdomain}.lms.test` against `PLATFORM_DOMAIN="lms.com"`, returning 403.

**Diff:**
```
-            "HTTP_HOST": f"{tenant.subdomain}.lms.test",
+            "HTTP_HOST": f"{tenant.subdomain}.lms.com",
```

**Affected tests (initially FAILED):**
- `TestAdminTokenListCrossTenantIsolation::test_admin_a_cannot_see_tenant_b_tokens_in_list` — got 403, expected 200
- `TestAdminTokenListCrossTenantIsolation::test_admin_a_list_only_contains_own_tokens` — got 403, KeyError on `"results"` key

Both passed after the fix.
