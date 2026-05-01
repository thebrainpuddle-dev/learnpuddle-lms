# Security Advisory — P1 OAuth State CSRF in Calendar Connect Flow

**From**: backend-security
**To**: backend-engineer
**CC**: reviewer
**Date**: 2026-04-20
**Severity**: P1 (High — account-takeover-adjacent)
**Scope**: `backend/apps/integrations_calendar/`
**Status**: NOT fixed — handing off because calendar views are outside
backend-security's hard file ownership, but this is squarely security work.

---

## TL;DR

The `state` parameter returned by `POST /api/v1/admin/calendar/{provider}/connect/`
is **never stored server-side** and **never validated** on the OAuth callback.
An attacker who can make an authenticated victim-admin's browser hit
`GET /api/v1/calendar/{provider}/callback/?code=<attacker_code>&state=anything`
can bind the **attacker's** Google/Outlook account to the **victim's**
`CalendarConnection` row. After the bind, LearnPuddle pushes the victim's
course deadlines / events to the attacker's calendar — leaking tenant data —
and the attacker controls the refresh token.

This is the canonical OAuth CSRF pattern (RFC 6749 §10.12). The fix is
mandatory server-side state storage + verification.

---

## Evidence

### 1. `state` is generated and returned but never stored

`backend/apps/integrations_calendar/views.py:117-131`:

```python
@admin_only
def connect_calendar(request, provider: str):
    ...
    state = secrets.token_urlsafe(32)
    try:
        auth_url = provider_mod.get_auth_url(state=state)
    ...
    return Response({
        "auth_url": auth_url,
        "state": state,
        "provider": provider,
    })
```

`state` is generated with `secrets.token_urlsafe(32)` (good), passed to the
provider for inclusion in the authorisation URL (good), and echoed to the
frontend in the response body. **It is never written to `request.session`,
cache, or the `CalendarConnection` row.** There is nothing on the server
for the callback handler to compare against.

### 2. Callback does not validate `state`

`backend/apps/integrations_calendar/views.py:139-169` — `calendar_callback`:

```python
code = request.query_params.get("code", "")
state = request.query_params.get("state", "")
...
if provider == "google":
    token_data = provider_mod.exchange_code(code=code, state=state)
else:  # outlook
    session_state = {"state": state}
    token_data = provider_mod.exchange_code(code=code, state=state,
                                            session_state=session_state)
```

No check like `if state != request.session.pop("oauth_state_{provider}"):`
appears before `exchange_code`. The comment above the Outlook branch is
explicit about the gap:

> `# Outlook needs a session_state dict; for Slice A we pass a minimal stub.`
> `# Slice B will wire up proper session-backed flow state.`

This is Slice B. It did not land.

### 3. Provider modules do not validate state either

#### Google (`providers/google.py:66-92`)

```python
def exchange_code(code: str, state: str) -> dict:
    ...
    flow = Flow.from_client_config(client_config, scopes=SCOPES, state=state)
    flow.redirect_uri = _redirect_uri()
    flow.fetch_token(code=code)
```

`google-auth-oauthlib` only validates state when you call
`flow.fetch_token(authorization_response=<full_callback_url>)`. Calling
`flow.fetch_token(code=code)` short-circuits the state check entirely — the
library uses the `code` to POST to the token endpoint and returns
credentials without ever comparing the state on the Flow object to anything.
Moreover, the Flow object here is constructed fresh with
`state=<state_from_URL>`, so even a hypothetical comparison would be
comparing the attacker-supplied state to itself.

#### Outlook (`providers/outlook.py:70-97`)

```python
def exchange_code(code: str, state: str, session_state: dict) -> dict:
    ...
    auth_response = {"code": code, "state": state}
    result = app.acquire_token_by_auth_code_flow(
        auth_code_flow=session_state,
        auth_response=auth_response,
    )
```

MSAL's `acquire_token_by_auth_code_flow` validates `auth_response["state"]`
against `auth_code_flow["state"]`. But the view passes
`session_state = {"state": state}` where `state` is the **URL query param**.
Both sides of the comparison are the attacker-controlled value. MSAL may
also error on missing `code_verifier`, `nonce`, or `claims_challenge` — the
stub dict is not what `initiate_auth_code_flow` returns — but the state
check itself is bypassed by construction.

### 4. Callback is protected by `IsAuthenticated` but not by flow ownership

`calendar_callback` requires authentication. That's necessary but not
sufficient: the CSRF attack forces a **victim** who is already authenticated
to complete a flow they never initiated, with the **attacker's** code. The
authentication decorator does nothing to detect that mismatch.

### 5. Impact after successful CSRF

`backend/apps/integrations_calendar/views.py:174-196`:

```python
connection, created = CalendarConnection.objects.get_or_create(
    user=request.user,
    provider=provider,
    defaults={"tenant": tenant},
)
connection.tenant = tenant
connection.status = CalendarConnection.STATUS_ACTIVE
connection.provider_user_id = token_data.get("provider_user_id", "")
...
connection.set_access_token(token_data.get("access_token", ""))
connection.set_refresh_token(token_data.get("refresh_token", ""))
```

`get_or_create` on `(user, provider)` silently overwrites a pre-existing
legitimate connection with the attacker's tokens. The victim's admin now
has a CalendarConnection that points at an external Google/Outlook account
the attacker owns. Every subsequent `sync_calendar_connection` run pushes
the tenant's course data (titles, descriptions, times) to the attacker's
calendar. The attacker's refresh token survives password rotation until
the connection is manually revoked.

### 6. Tests confirm the gap is not covered

`backend/apps/integrations_calendar/tests_views.py:268-285`
(`test_callback_with_bad_state_rejected_by_provider`) asserts only that
when `exchange_code` raises a ValueError, the view returns a 4xx/5xx. It
does **not** assert that a mismatched state actually causes `exchange_code`
to raise — because it mocks `exchange_code` to raise unconditionally. This
test passes with the current vulnerable code.

---

## Recommended fix (TDD-style plan)

### Failing tests to write first

1. **Google — state mismatch rejected**
   - `test_callback_state_mismatch_rejected_google`: call `connect_calendar`,
     then call `calendar_callback` with `state="attacker-forged-value"` and
     a mocked `exchange_code` that would otherwise succeed. Expect 400 with
     error code `OAUTH_STATE_MISMATCH`, and assert no `CalendarConnection`
     row was created.

2. **Google — missing state rejected**
   - `test_callback_missing_state_rejected_google`: call callback with
     `?code=abc` (no `state`). Expect 400, no DB write.

3. **Google — state cannot be replayed**
   - `test_callback_state_single_use_google`: call `connect_calendar` to
     get `s`, complete a callback with `state=s` successfully, then call
     callback again with `state=s`. Expect 400 on the second call.

4. **Outlook — mirror the three tests above.**

5. **Cross-user state rejected**
   - `test_callback_state_from_other_user_rejected`: user A calls
     `connect_calendar` and gets state `s_a`. User B hits the callback with
     `state=s_a`. Expect 400 (state belongs to a different session).

### Minimal fix shape

1. On `connect_calendar`, store state server-side keyed to the user and
   provider, with a short TTL:

   ```python
   cache_key = f"oauth_state:{provider}:{request.user.pk}:{state}"
   cache.set(cache_key, {"provider": provider, "user_id": str(request.user.pk)},
             timeout=600)  # 10 minutes
   ```

   Or use `request.session[f"oauth_state_{provider}"] = state` if the
   auth flow is same-session (it is — callback runs under the user's JWT).

2. On `calendar_callback`, validate and consume:

   ```python
   state = request.query_params.get("state", "")
   if not state:
       return Response({"error": "OAUTH_STATE_MISMATCH",
                        "detail": "Missing state."}, status=400)
   cache_key = f"oauth_state:{provider}:{request.user.pk}:{state}"
   stored = cache.get(cache_key)
   if stored is None:
       return Response({"error": "OAUTH_STATE_MISMATCH",
                        "detail": "Unknown or expired state."}, status=400)
   cache.delete(cache_key)  # single-use
   ```

3. For Outlook specifically: persist the **full** dict returned by
   `initiate_auth_code_flow` (it contains `code_verifier`, `nonce`, scopes,
   redirect_uri) in the cache, keyed by state. Pass that back into
   `acquire_token_by_auth_code_flow` so MSAL's own state/nonce/PKCE
   verification actually runs. The current `{"state": state}` stub is not a
   fix — MSAL needs the original flow dict.

4. Audit log the rejection path (`action="OAUTH_STATE_MISMATCH"`) so
   operators can detect CSRF attempts.

### Non-goals / out of scope

- Do not change the redirect URI scheme.
- Do not tighten `IsAuthenticated` further — it's already required.
- Do not revoke existing connections; the fix is forward-looking. The
  retro remediation is operator guidance: rotate any CalendarConnection
  where `provider_user_id` does not match the admin's expected account.

---

## Coordination

- I am **not** writing this fix — `backend/apps/integrations_calendar/`
  is outside my hard ownership list and the fix touches Outlook's full
  MSAL flow dict which is backend-engineer territory.
- I've appended a finding entry to `_coordination/shared-log.md`.
- Please ack in `_coordination/inbox/backend-security/` when you've
  picked this up, and request review from reviewer when the fix is ready.
- Suggest tagging this `BE-SEC-P1-OAUTH-STATE-CSRF` for tracking.

— backend-security
