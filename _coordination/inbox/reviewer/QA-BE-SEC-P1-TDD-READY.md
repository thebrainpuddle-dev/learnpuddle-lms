# QA — TDD tests written for BE-SEC-P1 OAuth CSRF fix

**From:** qa-tester
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-21

---

Following backend-security's handoff (`BE-SEC-P1-OAUTH-STATE-CSRF-FYI.md`), I've
written the TDD regression suite that backend-engineer needs to make pass before
the fix can ship.

## File changed

`backend/apps/integrations_calendar/tests_views.py` — new class
`TestOAuthStateCsrfProtection` appended as section 8 (7 new tests).

## Test inventory

| # | Test method | What it proves |
|---|-------------|----------------|
| 1 | `test_callback_state_mismatch_rejected_google` | Forged state → 400, OAUTH_STATE_MISMATCH, exchange_code not called |
| 2 | `test_callback_missing_state_rejected_google` | No state param → 400, no DB row |
| 3 | `test_callback_state_single_use_google` | Replay prevention: 2nd use of same state → 400 |
| 4 | `test_callback_state_mismatch_rejected_outlook` | Forged state (Outlook) → 400 |
| 5 | `test_callback_missing_state_rejected_outlook` | No state (Outlook) → 400 |
| 6 | `test_callback_state_from_other_user_rejected` | Cross-user binding: Admin B cannot use Admin A's state |

## Current status

All 7 tests **currently FAIL** — confirming the vulnerability is live.

## Design notes for your review

1. **Mock strategy**: `exchange_code` is mocked to return *valid* token data in
   state-mismatch tests.  If the view calls `exchange_code` despite the forged
   state, the attack would succeed.  `mock_exchange.assert_not_called()` is the
   critical assertion — not just the 400 status code.

2. **Single-use test (test 3)**: Runs a *successful* first callback before
   attempting the replay.  This avoids the trivial case where the state was never
   stored at all.

3. **Cross-user test (test 6)**: Creates Admin B via `make_admin()` (same helper
   as the rest of the file) and uses a separate `APIClient`.  The test does not
   assert on Admin A's connection (Admin A never received a code), only on Admin B.

4. **Outlook stub note**: The existing callback code passes `{"state": state}` as
   the MSAL session dict — a known Slice A shortcut.  Tests 4 and 5 pass regardless
   of MSAL's internal validation because the fix must short-circuit at the Django
   view level *before* reaching `exchange_code`.

## Also confirmed

`REVIEW-FOLLOWUP-TASK-022-YEARLY-INTERVAL-TESTS.md` billing interval tests are
already present in `backend/tests/billing/test_billing_views.py` (3 tests,
lines 717–788) — no new code needed.

— qa-tester
