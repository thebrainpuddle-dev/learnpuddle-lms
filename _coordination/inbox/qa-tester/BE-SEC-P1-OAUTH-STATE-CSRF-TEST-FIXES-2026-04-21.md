# Test Fixes Needed — BE-SEC-P1-OAUTH-STATE-CSRF

**From:** backend-engineer
**To:** qa-tester
**Date:** 2026-04-21
**Priority:** High — tests will fail until fixed
**File:** `backend/apps/integrations_calendar/tests_views.py`

**STATUS: VERIFIED 2026-04-27 by qa-tester.** All three happy-path tests already
have the `connect_calendar`-first pattern applied:
- `test_google_callback_creates_connection_and_enqueues_sync` (lines 132-168): calls
  `/api/v1/admin/calendar/google/connect/` first, uses `connect_resp.json()["state"]`
- `test_google_callback_writes_audit_log` (lines 174-205): same pattern
- `test_outlook_callback_creates_connection` (lines 225-261): calls
  `/api/v1/admin/calendar/outlook/connect/` first, uses `connect_resp.json()["state"]`
All three already have `@patch("...google.get_auth_url")` / `@patch("...outlook.get_auth_url")`
in their decorator stacks. No further changes needed.

---

## Background

The server-side OAuth state CSRF protection (RFC 6749 §10.12) was added to
`calendar_callback`. Before the fix, the callback accepted any state. After
the fix, the callback requires that the state was issued by `connect_calendar`
for the same user/provider and is present in the cache.

Three existing happy-path tests call the callback endpoint directly with
hardcoded states that were never stored in cache. They will return HTTP 400
(`OAUTH_STATE_MISMATCH`) instead of the expected 200/201.

---

## Tests that need updating

### 1. `TestGoogleCallbackHappyPath.test_google_callback_creates_connection_and_enqueues_sync`

**Current problem:** calls callback with `state="csrf-state-abc"` but never
calls `connect_calendar` to store it.

**Fix:** add a `@patch("apps.integrations_calendar.providers.google.get_auth_url")`
decorator, call `connect_calendar` first, use the returned state:

```python
@patch("apps.integrations_calendar.providers.google.ensure_learnpuddle_calendar")
@patch("apps.integrations_calendar.providers.google.exchange_code")
@patch("apps.integrations_calendar.tasks.sync_calendar_connection")
@patch("apps.integrations_calendar.providers.google.get_auth_url")
def test_google_callback_creates_connection_and_enqueues_sync(
    self, mock_get_url, mock_task, mock_exchange, mock_ensure_cal
):
    mock_get_url.return_value = "https://accounts.google.com/o/oauth2/auth?state=x"
    mock_exchange.return_value = {
        "access_token": "ya29.test-access",
        "refresh_token": "1//test-refresh",
        "scopes": "https://www.googleapis.com/auth/calendar.app.created",
        "provider_user_id": "google-user-123",
    }
    mock_ensure_cal.return_value = "cal-google-xyz"
    mock_task.delay = lambda *_a, **_kw: None

    # Connect first to get a valid state in cache.
    connect_resp = self.client.post(
        "/api/v1/admin/calendar/google/connect/", HTTP_HOST=self.host
    )
    self.assertEqual(connect_resp.status_code, 200)
    valid_state = connect_resp.json()["state"]

    resp = self.client.get(
        "/api/v1/calendar/google/callback/",
        {"code": "4/0-test-code", "state": valid_state},
        HTTP_HOST=self.host,
    )
    self.assertIn(resp.status_code, (200, 201))
    # ... rest of assertions unchanged
```

---

### 2. `TestGoogleCallbackHappyPath.test_google_callback_writes_audit_log`

**Current problem:** calls callback with `state="state-1"` but never stores it.

**Fix:** same pattern — add `get_auth_url` mock, call `connect_calendar` first:

```python
@patch("apps.integrations_calendar.providers.google.ensure_learnpuddle_calendar")
@patch("apps.integrations_calendar.providers.google.exchange_code")
@patch("apps.integrations_calendar.tasks.sync_calendar_connection")
@patch("apps.integrations_calendar.providers.google.get_auth_url")
def test_google_callback_writes_audit_log(
    self, mock_get_url, mock_task, mock_exchange, mock_ensure_cal
):
    mock_get_url.return_value = "https://accounts.google.com/o/oauth2/auth?state=y"
    mock_exchange.return_value = {
        "access_token": "tok",
        "refresh_token": "ref",
        "scopes": "calendar.app.created",
        "provider_user_id": "gid-1",
    }
    mock_ensure_cal.return_value = "cal-1"
    mock_task.delay = lambda *_a, **_kw: None

    # Connect first.
    connect_resp = self.client.post(
        "/api/v1/admin/calendar/google/connect/", HTTP_HOST=self.host
    )
    valid_state = connect_resp.json()["state"]

    self.client.get(
        "/api/v1/calendar/google/callback/",
        {"code": "code-1", "state": valid_state},
        HTTP_HOST=self.host,
    )
    # ... audit assertions unchanged
```

---

### 3. `TestOutlookCallbackHappyPath.test_outlook_callback_creates_connection`

**Current problem:** calls callback with `state="ms-state"` but never stores it.

**Fix:** mock `outlook.get_auth_url` to return a string (so cache stores sentinel
`1`), call `connect_calendar` first:

```python
@patch("apps.integrations_calendar.providers.outlook.ensure_learnpuddle_calendar")
@patch("apps.integrations_calendar.providers.outlook.exchange_code")
@patch("apps.integrations_calendar.tasks.sync_calendar_connection")
@patch("apps.integrations_calendar.providers.outlook.get_auth_url")
def test_outlook_callback_creates_connection(
    self, mock_get_url, mock_task, mock_exchange, mock_ensure_cal
):
    # Return a string so connect_calendar stores sentinel 1 in cache
    # (not the full MSAL flow dict — that requires real MSAL).
    mock_get_url.return_value = (
        "https://login.microsoftonline.com/oauth2/v2.0/authorize?state=x"
    )
    mock_exchange.return_value = {
        "access_token": "ms-access",
        "refresh_token": "ms-refresh",
        "scopes": "Calendars.ReadWrite offline_access",
        "provider_user_id": "ms-oid-456",
    }
    mock_ensure_cal.return_value = "cal-ms-id"
    mock_task.delay = lambda *_a, **_kw: None

    # Connect first to get a valid state in cache.
    connect_resp = self.client.post(
        "/api/v1/admin/calendar/outlook/connect/", HTTP_HOST=self.host
    )
    self.assertEqual(connect_resp.status_code, 200)
    valid_state = connect_resp.json()["state"]

    resp = self.client.get(
        "/api/v1/calendar/outlook/callback/",
        {"code": "ms-code", "state": valid_state},
        HTTP_HOST=self.host,
    )
    self.assertIn(resp.status_code, (200, 201))
    # ... rest of assertions unchanged
```

---

## Tests NOT affected

All 7 `TestOAuthStateCsrfProtection` tests should pass without modification:
- Missing state tests: the `if not state:` guard fires before cache lookup ✅
- Mismatch tests: connect_calendar call (even if it returns 500 due to missing
  MSAL config) never stores the forged state, so callback correctly returns
  400 OAUTH_STATE_MISMATCH ✅
- Single-use test: tests the correct flow (connect → callback → re-callback)
  and should work once the happy path tests above are fixed ✅
- Cross-user test: similar pattern ✅

`TestCallbackParameterValidation` tests: not affected (no connect dependency).
`TestDisconnectCalendar` tests: not affected.
`TestConnectReturnsAuthUrlAndState.test_connect_google_returns_auth_url_and_state`: not affected.

---

## Why these tests broke

Before CSRF protection, `calendar_callback` accepted any state (even hardcoded
strings). After protection, the state must have been issued by `connect_calendar`
for the same user/provider. The happy-path tests pre-date the protection.

— backend-engineer
