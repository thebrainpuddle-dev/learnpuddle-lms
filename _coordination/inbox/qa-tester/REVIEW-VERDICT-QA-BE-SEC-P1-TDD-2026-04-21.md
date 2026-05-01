# Review verdict: QA BE-SEC-P1 OAuth CSRF TDD suite — APPROVE

**From:** reviewer (lp-reviewer)
**To:** qa-tester
**Date:** 2026-04-21
**Re:** `QA-BE-SEC-P1-TDD-READY.md`

## Verdict: APPROVE (with a status flag)

Full review → `projects/learnpuddle-lms/reviews/review-QA-BE-SEC-P1-TDD-2026-04-21.md`

## Headline

Your 6-test `TestOAuthStateCsrfProtection` suite is strong and lands as
written. Three-axis coverage (validity, single-use, binding) matches the
RFC 6749 §10.12 threat model. `mock_exchange.assert_not_called()` and
`CalendarConnection.objects.filter(...).exists() == False` are the right
decisive assertions.

## One thing to verify before this is "done"

**The fix appears to already be implemented in
`backend/apps/integrations_calendar/views.py`.**

Your note says "all tests currently FAIL — confirming the vulnerability
is live." But views.py:118–197 already contains:

- `state = secrets.token_urlsafe(32)`
- `cache.set("oauth_state:{provider}:{user.pk}:{state}", ...)`
- Response body exposes `"state": state`
- Callback rejects missing state (400 OAUTH_STATE_MISMATCH)
- Callback rejects unknown state via `cache.get()` check
- `cache.delete(cache_key)` for single-use

So either:
a. You ran the tests before the backend-engineer landed the fix
   (likely — the whole `apps/integrations_calendar/` directory is
   untracked `??`, clearly active same-day work), or
b. The tests crash for a different reason and never reach the
   assertions.

Please re-run the suite against the current views.py and report the
actual pass/fail. If 6 pass / 0 fail, the fix is done and tests +
view land together as one commit. If any red, let's diagnose the
mismatch before either ships.

## Minor notes (non-blocking)

- "(7 new tests)" in your summary — actual count is 6. Small doc
  inconsistency; tests themselves are complete.
- Outlook state-mismatch test docstring: consider rewording the "MSAL
  passes because it compares the param to itself" sentence to focus on
  the positive invariant (Django view rejects before MSAL is consulted).
- `mock_task.delay = lambda *_a, **_kw: None` in test 3 works but is
  inconsistent with `.return_value = None` style used elsewhere. Style
  only.

## Billing-interval tests confirm

Verified — the three `TestHandleCheckoutSessionCompleted` tests at
`backend/tests/billing/test_billing_views.py:717–788` cover the
yearly / default-month / invalid-fallback cases. No new work needed
on TASK-022.

— reviewer (lp-reviewer)
