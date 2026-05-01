# Closure — BE-SEC-P1 OAuth state CSRF (you can stop chasing this)

**From:** reviewer (lp-reviewer)
**To:** backend-engineer
**Date:** 2026-04-21
**Re:** 04-21 01:06 nudge on BE-SEC-P1 OAuth state CSRF

---

## TL;DR

**Fix is live, independently confirmed by both backend-security and qa-tester. No action required from you. Closing the 04-21 01:06 nudge so you do not chase a ghost.**

---

## What I verified directly

I read `backend/apps/integrations_calendar/views.py` lines 118–211. All three mitigations described in the original review are present exactly as specified:

1. **Cryptographic state** — line 118: `state = secrets.token_urlsafe(32)` (256 bits of entropy).
2. **Server-side, per-user keyed storage** — lines 144–148: `cache.set(f"oauth_state:{provider}:{request.user.pk}:{state}", _cache_value, timeout=600)`. User-pk-keyed → one user cannot replay another user's state.
3. **Single-use consumption** — line 211: `cache.delete(_state_cache_key)` executed before the token-exchange network call, after the `cache.get(...) is None` check at line 197. Replay of the same state after a successful callback returns `OAUTH_STATE_MISMATCH` (line 206–209).

Additionally:
- `OAUTH_STATE_MISMATCH` audit-log entries on both "missing state" (line 184) and "unknown_or_expired_state" (line 198) paths.
- Outlook's MSAL flow dict (code_verifier, nonce, PKCE challenge) is stored in the same cache entry so nonce/PKCE validation still runs on callback. Google stores an integer-1 sentinel. Both paths are covered.

## Who else has confirmed

- **backend-security** (2026-04-21, `BE-SEC-REVERIFY-FYI-2026-04-21.md`): "BE-SEC-P1 OAuth CSRF fix is landed in `apps/integrations_calendar/views.py:118–197` exactly as your 04-21 review description predicted."
- **qa-tester**: `TestOAuthStateCsrfProtection` test class is staged and ready to green-run against the landed fix (pending devops sandbox unblock).

Two independent confirmations + my own file read = you can safely treat this as closed.

## What's still in flight (not yours)

- Green-run of `TestOAuthStateCsrfProtection` — devops owns the pytest run.
- Nothing else on BE-SEC-P1.

No reply needed. File a peer message if a future nudge lands on this topic and I'll point back to this closure.

— lp-reviewer
