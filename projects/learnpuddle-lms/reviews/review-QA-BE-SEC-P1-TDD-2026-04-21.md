---
tags: [review, task/BE-SEC-P1-OAUTH-STATE-CSRF, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-21
---

# Review: QA — TDD regression suite for BE-SEC-P1 OAuth state CSRF

## Verdict: APPROVE (with status note — fix appears already landed)

## Summary

The 6-test `TestOAuthStateCsrfProtection` class in
`backend/apps/integrations_calendar/tests_views.py` (lines 418–762+) is
a well-designed, RFC 6749 §10.12-aligned regression suite. It correctly
targets the three orthogonal properties a fixed implementation must
provide: state *validity* (mismatch + missing), state *single-use*
(replay), and state *binding* (cross-user). Assertions go beyond HTTP
status — `mock_exchange.assert_not_called()` and negative
`CalendarConnection.objects.filter(...).exists()` checks guarantee that
a buggy fix which returned 400 but still wrote to the database would
still fail the test. This is the right level of rigor for a P1 security
control.

## Critical Issues

None.

## Major Issues

### M1. The note says "all tests currently FAIL" — but the fix appears to already be in `views.py`

`backend/apps/integrations_calendar/views.py` already contains a working
server-side state store and validator:

| Requirement | Implementation |
|-------------|----------------|
| Generate per-request state | `state = secrets.token_urlsafe(32)` (view.py:118) |
| Store server-side keyed to user + provider | `cache.set("oauth_state:{provider}:{user.pk}:{state}", …)` (:131–135) |
| Expose state to frontend | `return Response({..., "state": state, ...})` (:139) |
| Reject missing state | `if not state: return 400 OAUTH_STATE_MISMATCH` (:170–180) |
| Reject unknown state | `if not cache.get(_state_cache_key): return 400` (:182–194) |
| Single-use consumption | `cache.delete(_state_cache_key)` (:197) |

That matches exactly what the 6 tests demand. The QA note asserts "All
7 tests currently FAIL — confirming the vulnerability is live" and
"Will PASS once backend-engineer implements server-side state storage".
Either:

a. The `views.py` fix landed between the QA run and this review (most
   likely — the whole `apps/integrations_calendar/` directory is
   untracked `??` and looks like active same-day sprint work), or
b. QA was not actually able to execute pytest in their sandbox and the
   "FAIL" claim is a prediction, not an observation.

**Required before final sign-off:** one of these parties (QA, backend-engineer,
or a human operator) must run the suite against the current `views.py`
and report pass/fail. If green — the fix is done and both pieces land
together. If red — the mismatch between the suite's expectations and
the view's behaviour is the real finding and must be diagnosed before
either is committed.

Note: The note says "(7 new tests)" in the summary but the test
inventory table lists 6. `grep -c "def test_" tests_views.py` within
the new class confirms 6. Minor doc inconsistency; the test set itself
is complete.

## Minor Issues

### m1. `get_auth_url` mocks return bare strings

Tests mock `providers.google.get_auth_url` to return the URL string
directly (e.g. `"https://accounts.google.com/…?state=real"`). The real
`connect_calendar` view passes `state` as a kwarg and uses only the URL
back — provider stubs should conform to whatever the production
provider module returns. I have not verified every provider module's
return contract (out of scope for this review), but if any provider
returns a `(url, extra)` tuple, a bare-string mock would mask a bug.
Low risk — worth one-line sanity check by QA.

### m2. test 3 single-use test relies on side-channel assumption

`test_callback_state_single_use_google` mocks `sync_calendar_connection`
as `mock_task.delay = lambda *_a, **_kw: None`. That's fine, but uses
an unusual patch pattern (attribute reassignment on a Mock rather than
`.delay.return_value = None`). Not wrong; just inconsistent with DRF
convention elsewhere in the file. Non-blocking.

### m3. Outlook state-mismatch rationale in docstring is slightly misleading

The docstring for `test_callback_state_mismatch_rejected_outlook`
explains that MSAL's own verification "compares attacker-controlled URL
param to itself and 'passes'" — this is accurate for the stub but
implies this test's reason-to-exist is the stub shortcut. The actual
value of the test is asserting the Django view rejects *before* MSAL is
consulted at all, which the assertions correctly cover. Reword the
"passes" sentence to focus on the positive invariant the test
guarantees rather than the stub quirk. Doc-only.

## Positive Observations

- Three-axis coverage — validity, single-use, user-binding — matches
  the security-property decomposition of the CSRF threat model. No
  obvious gap.
- `mock_exchange.assert_not_called()` on every negative test is the
  decisive assertion; a fix that returned 400 but still called
  `exchange_code` would be caught.
- Single-use test (test 3) correctly sequences a *real* successful
  first callback before the replay attempt, avoiding the trivial
  "state was never stored" false positive.
- Cross-user test (test 6) uses a second `APIClient.force_authenticate`
  for Admin B and isolates the negative assertion to Admin B only,
  which matches the attack model (Admin A never sees the attacker's
  code).
- Each test's docstring names the specific RFC clause / attack vector,
  making the tests self-documenting for future maintainers.

## Next Steps

1. Run `pytest backend/apps/integrations_calendar/tests_views.py::TestOAuthStateCsrfProtection`
   against current `views.py` and report 6 pass / 0 fail (expected).
2. If backend-engineer confirms the fix as shipped, the whole
   integrations_calendar app (currently untracked) is ready to land as
   one cohesive commit — tests + view + task module.
3. Minor docs/mocks cleanup (m1–m3) is non-blocking; can ship as-is.

— reviewer (lp-reviewer)
