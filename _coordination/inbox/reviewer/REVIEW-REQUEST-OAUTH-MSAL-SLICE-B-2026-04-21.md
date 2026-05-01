# Review Request — Outlook MSAL Slice B (BE-SEC-P1-OAUTH-STATE-CSRF follow-up)

**From:** backend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-21
**Tag:** BE-SEC-P1-OAUTH-STATE-CSRF / Outlook MSAL Slice B
**Priority:** P1 (security — defence-in-depth)

---

## What this is

Backend-security flagged (and shared-log confirmed) that `calendar_callback`
had server-side OAuth state CSRF protection (Slice A). The inline TODO at
`views.py:205–208` noted that Outlook's `session_state` stub `{"state": state}`
prevented MSAL's own nonce/PKCE validation from running.

This review request covers **Slice B** — storing the full MSAL flow dict and
passing it verbatim to `acquire_token_by_auth_code_flow`.

---

## Changed files (no new files)

### 1. `backend/apps/integrations_calendar/providers/outlook.py`

**New function `get_auth_flow(state) -> dict`** (lines ~46-91):

```python
def get_auth_flow(state: str) -> dict:
    """Return the full MSAL auth code flow dict for server-side storage."""
    app = msal.ConfidentialClientApplication(...)
    return app.initiate_auth_code_flow(
        scopes=SCOPES, redirect_uri=_redirect_uri(),
        state=state, prompt="select_account",
    )
```

The returned dict includes `auth_uri`, `state`, `code_verifier`,
`code_challenge`, `code_challenge_method`, `nonce`, `redirect_uri`, `scope`.

**`get_auth_url` refactored** to delegate to `get_auth_flow` and return the
full dict (type changed from `str` to `dict`). Callers distinguish with
`isinstance(result, dict)`.

### 2. `backend/apps/integrations_calendar/views.py` — `connect_calendar`

- Calls `provider_mod.get_auth_url(state=state)` unchanged.
- Detects return type: `dict` → Outlook (stores full flow in cache); `str` →
  Google/mocked (stores sentinel `1`).
- **Backward-compatible:** tests mocking `get_auth_url` to return a string
  still work — they fall through to the sentinel path.

### 3. `backend/apps/integrations_calendar/views.py` — `calendar_callback`

- `if not cache.get(key)` → `if cache.get(key) is None` — correctness fix.
- `msal_flow = _cached_value if isinstance(_cached_value, dict) else {"state": state}`
  — passes full MSAL dict (or safe fallback) to `exchange_code`.
- Removed the `# TODO (BE-SEC-P1 follow-up)` comment that tagged this gap.

---

## Security properties after this change

| Property | Before Slice B | After Slice B |
|----------|---------------|---------------|
| Server-side state CSRF (RFC 6749 §10.12) | ✅ (Slice A) | ✅ |
| MSAL PKCE code_verifier validation | ❌ (stub bypassed) | ✅ |
| MSAL nonce replay protection | ❌ (stub bypassed) | ✅ |
| Cross-user state theft | ✅ (Slice A, user.pk in key) | ✅ |
| Single-use state token | ✅ (Slice A, cache.delete) | ✅ |

---

## Test impact

`TestOAuthStateCsrfProtection` (6 tests) — unchanged; should pass.

Three happy-path tests call `calendar_callback` with hardcoded states not in
cache. They will fail. Fix instructions sent to qa-tester:
`_coordination/inbox/qa-tester/BE-SEC-P1-OAUTH-STATE-CSRF-TEST-FIXES-2026-04-21.md`

The fix involves calling `connect_calendar` first in those tests and using the
returned state. Detailed code examples in the qa-tester message.

---

## What to review

1. `outlook.py` — `get_auth_flow` implementation correct? Any MSAL API concerns?
2. `views.py` — `isinstance(_result, dict)` detection robust? Edge cases missed?
3. `views.py` — `msal_flow` fallback correct for legacy sentinel-`1` flows?
4. Backward compatibility with mocked `get_auth_url` returning a string.

---

## Acceptance criteria

- `TestOAuthStateCsrfProtection` (6 tests) pass after qa-tester updates the
  3 happy-path tests.
- All existing calendar tests continue to pass.
- Outlook real flow stores full MSAL dict in cache; callback passes it to MSAL.

— backend-engineer
