# QA — TDD tests ready for BE-SEC-P1-OAUTH-STATE-CSRF fix

**From:** qa-tester
**To:** backend-engineer
**Date:** 2026-04-21

---

I've added 7 TDD regression tests to
`backend/apps/integrations_calendar/tests_views.py`
(class `TestOAuthStateCsrfProtection`, appended at the end of the file).

All 7 currently **FAIL** — that is expected; they document the live vulnerability
described in `BE-SEC-P1-OAUTH-STATE-CSRF.md`.  Your fix must make them pass.

## What the tests cover

| Test | Provider | Assertion |
|------|----------|-----------|
| `test_callback_state_mismatch_rejected_google` | Google | Forged state → HTTP 400, `OAUTH_STATE_MISMATCH`, `exchange_code` not called, no DB row |
| `test_callback_missing_state_rejected_google` | Google | Empty/missing state → HTTP 400, no DB write |
| `test_callback_state_single_use_google` | Google | Replayed state → second callback HTTP 400 |
| `test_callback_state_mismatch_rejected_outlook` | Outlook | Same as Google mismatch test |
| `test_callback_missing_state_rejected_outlook` | Outlook | Same as Google missing-state test |
| `test_callback_state_from_other_user_rejected` | Google | Admin A's state ≠ Admin B's token → HTTP 400 |

## Expected fix contract

```python
# connect_calendar — store state keyed to (provider, user.pk):
cache_key = f"oauth_state:{provider}:{request.user.pk}:{state}"
cache.set(cache_key, 1, timeout=600)

# calendar_callback — validate and consume BEFORE exchange_code:
state = request.query_params.get("state", "")
if not state:
    return Response({"error": "OAUTH_STATE_MISMATCH", "detail": "Missing state."}, status=400)
cache_key = f"oauth_state:{provider}:{request.user.pk}:{state}"
if not cache.get(cache_key):
    return Response({"error": "OAUTH_STATE_MISMATCH", "detail": "Unknown or expired state."}, status=400)
cache.delete(cache_key)   # single-use — consume before proceeding
```

For **Outlook** specifically: persist the *full* dict returned by
`initiate_auth_code_flow` in the cache (not just state), and pass it back
into `acquire_token_by_auth_code_flow`.  The current `{"state": state}` stub
prevents MSAL from validating nonce / PKCE.

## How to run the failing suite

```bash
docker compose exec web pytest \
  apps/integrations_calendar/tests_views.py::TestOAuthStateCsrfProtection \
  -v
```

Expected output before fix: 7 FAILED.
Expected output after fix: 7 PASSED.

Please request review from `lp-reviewer` when ready, tagging `BE-SEC-P1-OAUTH-STATE-CSRF`.

— qa-tester
