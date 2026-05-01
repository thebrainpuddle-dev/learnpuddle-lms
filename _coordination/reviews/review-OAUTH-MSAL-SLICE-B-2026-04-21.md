---
tags: [review, task/BE-SEC-P1-OAUTH-STATE-CSRF, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-21
---

# Review: Outlook MSAL Slice B — full-dict session_state

## Verdict: APPROVE

## Summary

Slice B correctly closes the nonce/PKCE validation gap that Slice A
left behind. `initiate_auth_code_flow` is now stored server-side and
replayed verbatim to `acquire_token_by_auth_code_flow` on the callback,
which is the canonical MSAL pattern. Backward-compat for test mocks
returning a plain `str` is preserved.

## Scope reviewed

- `backend/apps/integrations_calendar/providers/outlook.py` — `get_auth_flow`, `get_auth_url`, `exchange_code`
- `backend/apps/integrations_calendar/views.py` — `connect_calendar`, `calendar_callback`

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **(non-blocking) Defense-in-depth on `calendar_callback`.** Still no
   `@admin_only` on `calendar_callback`. Cross-role replay is already
   prevented by the `user.pk` cache-key binding, so this is defence-in-
   depth only — a TEACHER-authenticated account would still fail the
   state check because `connect_calendar` (@admin_only) never issued a
   state under their pk. Carried over from Slice A; call out again so
   it isn't forgotten.

2. **(nit) Mixed return type on `get_auth_url`.** Google returns `str`,
   Outlook now returns `dict`. Callers branch on `isinstance(_result, dict)`.
   The docstrings are clear, but if a third provider lands, the call site
   will grow another isinstance branch. Consider promoting `get_auth_flow`
   to the canonical provider contract and keeping `get_auth_url(state) -> str`
   as a thin compat shim that returns just the URL. Post-merge cleanup —
   not blocking this slice.

3. **(nit) Legacy sentinel fallback `{"state": state}`.** If
   `_cached_value == 1` for provider=outlook (only reachable via test
   mocks that stub `get_auth_url` → str), MSAL will reject the stub
   because `code_verifier`/`nonce` are absent. Acceptable for tests that
   don't exercise the full MSAL round-trip; noted so future readers
   don't mistake it for a production path.

## Positive Observations

- Full MSAL flow dict (`auth_uri`, `state`, `code_verifier`,
  `code_challenge`, `nonce`, `redirect_uri`, `scope`) stored in Redis
  under the same user-scoped, single-use key as Slice A. PKCE secret
  is never exposed to the provider redirect URL.
- `cache.delete()` before the token exchange preserves single-use
  semantics — a stolen state + MSAL dict cannot be replayed.
- `if _cached_value is None` (correctness fix from `if not cache.get(key)`)
  avoids the falsy-value edge case if legacy callers ever stored `0`/`""`.
- `msal_flow = _cached_value if isinstance(_cached_value, dict) else {"state": state}`
  is a reasonable backward-compat guard for the mocked-string test path.
- Clear, actionable docstrings on `get_auth_flow` and on the `views.py`
  branch comments. Explicitly calls out that the dict contains secrets
  that must stay server-side.

## Security properties after merge

| Property | State |
|----------|-------|
| RFC 6749 §10.12 server-side state CSRF | ✅ (Slice A) |
| MSAL PKCE `code_verifier` validation | ✅ (Slice B) |
| MSAL `nonce` replay protection | ✅ (Slice B) |
| Cross-user state theft | ✅ (user.pk in cache key) |
| Single-use state token | ✅ (`cache.delete` pre-exchange) |

## Test impact / acceptance

- `TestOAuthStateCsrfProtection` (6 tests) — unchanged; pass after
  qa-tester updates 3 legacy happy-path tests to go through
  `connect_calendar` first. QA fix-guide already filed at
  `_coordination/inbox/qa-tester/BE-SEC-P1-OAUTH-STATE-CSRF-TEST-FIXES-2026-04-21.md`.
- Docker-based pytest run blocked in all agent sandboxes (see
  BE-SEC-P0-AUDIT-TEST-RUN-SANDBOX-BLOCKED); static verification only.

## Recommendation

APPROVE. Ship view + tests in one commit. Carry the defense-in-depth
`@admin_only` observation into the next calendar-integrations PR.

— reviewer (lp-reviewer)
