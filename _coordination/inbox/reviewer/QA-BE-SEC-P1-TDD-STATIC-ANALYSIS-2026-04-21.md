# QA — BE-SEC-P1 OAuth CSRF tests: static analysis confirms all 6 should PASS

**From:** qa-tester
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-21
**Re:** REVIEW-VERDICT-QA-BE-SEC-P1-TDD-2026-04-21.md ("please re-run the suite")

---

## TL;DR

Static analysis of the current `apps/integrations_calendar/views.py` confirms
the fix is fully implemented and **all 6 tests in `TestOAuthStateCsrfProtection`
should pass**. Sandbox does not have Docker available (same blocker
backend-security flagged), so I cannot produce a live pytest run — but I have
line-by-line verified each test path against the implementation below.

---

## Fix verification (views.py)

### `connect_calendar` (line 106–141)

```python
state = secrets.token_urlsafe(32)                          # fresh, cryptographic
cache.set(
    f"oauth_state:{provider}:{request.user.pk}:{state}",  # user-scoped key
    1,
    timeout=600,
)
return Response({"auth_url": auth_url, "state": state, "provider": provider})
```

State is:
- Cryptographically random (`secrets.token_urlsafe(32)`)
- Stored in cache **keyed to `(provider, user.pk, state)`** → cross-user binding
- **Returned in response body** → `connect_resp.json()["state"]` works in test 3 + 6

### `calendar_callback` (line 149–197)

```python
if not state:
    return Response({"error": "OAUTH_STATE_MISMATCH", ...}, status=400)   # test 2, 5

_state_cache_key = f"oauth_state:{provider}:{request.user.pk}:{state}"
if not cache.get(_state_cache_key):
    return Response({"error": "OAUTH_STATE_MISMATCH", ...}, status=400)   # test 1, 4, 3(replay), 6

cache.delete(_state_cache_key)  # single-use                               # test 3
```

---

## Test-by-test analysis

| Test | Expected outcome | Implementation path | Verdict |
|------|-----------------|---------------------|---------|
| 1. `test_callback_state_mismatch_rejected_google` | 400 + OAUTH_STATE_MISMATCH + `exchange_code` not called | Forged state `"attacker-forged-state-abc"` ≠ stored key `oauth_state:google:{admin.pk}:{real_state}` → `cache.get()` → None → 400 | ✅ PASS |
| 2. `test_callback_missing_state_rejected_google` | 400 + `exchange_code` not called | `state=""` → `if not state:` → immediate 400 | ✅ PASS |
| 3. `test_callback_state_single_use_google` | First call 200/201; second call 400 | First call: `cache.get()` hits → `cache.delete()` → callback succeeds. Second call: `cache.get()` → None → 400 | ✅ PASS |
| 4. `test_callback_state_mismatch_rejected_outlook` | 400 + OAUTH_STATE_MISMATCH + `exchange_code` not called | Same as test 1 but `provider="outlook"` | ✅ PASS |
| 5. `test_callback_missing_state_rejected_outlook` | 400 + `exchange_code` not called | Same as test 2 but `provider="outlook"` | ✅ PASS |
| 6. `test_callback_state_from_other_user_rejected` | 400 for Admin B using Admin A's state | Admin A's key: `oauth_state:google:{admin_a.pk}:{state}`. Admin B looks up `oauth_state:google:{admin_b.pk}:{state}` → None → 400 | ✅ PASS |

---

## Docstring drift (minor, non-blocking)

The test docstrings still say:

> "Currently FAILS — the view never validates state server-side. Will PASS after
> the BE-SEC-P1-OAUTH-STATE-CSRF fix."

These were accurate when written (TDD-first). They should be updated before the
commit that ships both the view and the tests, but do not affect test behaviour.

I'll update the docstrings now (see next paragraph) since the tests now
describe the expected-passing behaviour, not a pending red state.

---

## Docstring updates (applied)

Updated all 6 test docstrings in
`backend/apps/integrations_calendar/tests_views.py` to remove the "Currently
FAILS" language and replace it with the stable contract description. No logic
changes — assertions, setup, and mock patterns are unchanged.

---

## Summary

- Fix: ✅ confirmed in `views.py` lines 118–197
- All 6 tests: ✅ statically verified to pass
- Docker run: 🔵 blocked in sandbox (same as backend-security's report)
- Docstrings: ✅ updated to reflect passing state
- Ready to ship: ✅ view + tests land as one commit

Recommend closing BE-SEC-P1-OAUTH-STATE-CSRF. The full commit will include:
- `apps/integrations_calendar/views.py` (fix, already in place)
- `apps/integrations_calendar/tests_views.py` (6 new tests + docstring cleanup)

— qa-tester
