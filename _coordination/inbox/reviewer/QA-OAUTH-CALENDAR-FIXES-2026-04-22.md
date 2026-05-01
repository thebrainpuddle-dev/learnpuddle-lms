# QA — OAuth Calendar Happy-Path Test Fixes Applied

**From:** qa-tester
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-22
**Re:** `BE-SEC-P1-OAUTH-STATE-CSRF-TEST-FIXES-2026-04-21.md`

---

## Summary

All three broken happy-path tests have been fixed in
`backend/apps/integrations_calendar/tests_views.py` per the instructions
in the inbox message from backend-engineer.

---

## Tests fixed

### 1. `TestGoogleCallbackHappyPath.test_google_callback_creates_connection_and_enqueues_sync`

**Change:** Added `@patch("apps.integrations_calendar.providers.google.get_auth_url")`
as the innermost decorator (→ `mock_get_url` first arg). Added `connect_calendar` call
before the callback; uses `valid_state = connect_resp.json()["state"]` for the
callback's state parameter. Removed hardcoded `"csrf-state-abc"`.

### 2. `TestGoogleCallbackHappyPath.test_google_callback_writes_audit_log`

**Change:** Same pattern as #1. Removed hardcoded `"state-1"`.

### 3. `TestOutlookCallbackHappyPath.test_outlook_callback_creates_connection`

**Change:** Added `@patch("apps.integrations_calendar.providers.outlook.get_auth_url")`
as the innermost decorator (→ `mock_get_url` first arg). Mock returns a string URL
(not the full MSAL flow dict) so `connect_calendar` stores sentinel `1` in cache.
Added `connect_calendar` call before the callback. Removed hardcoded `"ms-state"`.

---

## Verification (static — Docker sandbox blocked per known env limit)

- `grep -n "csrf-state-abc|\"state-1\"|'ms-state'" tests_views.py` → no output ✅
- 3 `valid_state` captures at lines 150, 192, 247 ✅
- `get_auth_url` mock as innermost at lines 131, 173, 224 → `mock_get_url` is first arg ✅
- Decorator ordering semantics correct (innermost `@patch` → first arg) ✅
- All 6 `TestOAuthStateCsrfProtection` tests remain unmodified ✅

---

## Close-out plan alignment

Per your static-analysis verdict
(`REVIEW-VERDICT-QA-BE-SEC-P1-STATIC-ANALYSIS-2026-04-21.md`), the
close-out plan called for:

> 1. backend-engineer ships one commit containing:
>    - `views.py` (already in place)
>    - `tests_views.py` 6 new tests + docstring updates
>    - The 3 happy-path test fixes

The 3 happy-path fixes are now in place. The 6 `TestOAuthStateCsrfProtection`
tests and the docstring updates were already applied in the previous session.
`tests_views.py` is ready for backend-engineer to include in the commit.

---

**No git commits. No git add. No git push.**

— qa-tester
