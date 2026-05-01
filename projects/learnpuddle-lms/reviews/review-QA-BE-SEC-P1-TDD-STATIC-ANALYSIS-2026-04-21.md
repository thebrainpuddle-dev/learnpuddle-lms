---
tags: [review, task/BE-SEC-P1-OAUTH-STATE-CSRF, verdict/approve, reviewer/lp-reviewer, area/security, area/oauth]
created: 2026-04-21
---

# Review: QA — BE-SEC-P1 OAuth CSRF tests, static-analysis confirmation + docstring cleanup

## Verdict: APPROVE (static verification accepted; live pytest run still owed before commit)

## Summary
Follow-up to `review-QA-BE-SEC-P1-TDD-2026-04-21.md`, which asked for a
live pytest run against the landed `views.py` fix. QA confirms the same
sandbox blocker backend-security hit (`docker` not on PATH, backend
`.venv` not a permitted execution target). In lieu of a live run, QA
provided a line-by-line static trace of all 6 `TestOAuthStateCsrfProtection`
tests against the current view. Their table maps each assertion to the
exact line in `views.py:118–197` that produces the expected outcome — I
re-walked the same trace and concur with every row. Docstring TDD-red
language ("Currently FAILS — will PASS after…") has been removed;
replaced with a stable "Fixed by BE-SEC-P1-OAUTH-STATE-CSRF" narrative.

## Critical Issues
None.

## Major Issues
None. The static analysis is reasonable given the sandbox constraint,
and the view implementation genuinely does match what the tests demand.
The only outstanding item is the same one I flagged in the prior review:
a real pytest invocation still has to happen before the commit lands,
by someone with Docker (devops) or a human operator with shell access
to the compose stack.

## Minor Issues

### m1 (carried from prior review) — provider mock return contract unverified
QA did not confirm `providers.google.get_auth_url` / `providers.outlook.get_auth_url`
return plain strings in production as the mocks assume. If either ever
returns a `(url, extra)` tuple or a dict (e.g. MSAL's
`initiate_auth_code_flow` shape), the bare-string mock would mask a
regression. **Non-blocking** — still low risk, still worth a one-line
grep on the next touch of those provider modules.

### m3 (carried from prior review) — Outlook docstring partially reworked
The "passes" sentence is still present at lines 616–618 but now followed
by a clear positive-invariant paragraph ("Fixed by BE-SEC-P1…: server-side
state validation happens BEFORE the MSAL exchange_code call"). Good
enough — the confusion was the docstring implying the test existed *only*
because of the stub quirk. The new paragraph fixes that. **Non-blocking.**

## Positive Observations

### Static trace is rigorous

| Test | QA's traced line | Re-verified against `views.py` |
|------|------------------|------------------------------|
| 1. `state_mismatch_rejected_google` | forged state ≠ key → `cache.get()` None → 400 | ✅ matches `:182–194` |
| 2. `missing_state_rejected_google` | `if not state:` → 400 | ✅ matches `:170–180` |
| 3. `state_single_use_google` | first hit → `cache.delete()`; second hit → `cache.get()` None → 400 | ✅ matches `:197` + `:182–194` |
| 4. `state_mismatch_rejected_outlook` | provider-agnostic check → 400 before MSAL | ✅ same code path as 1 |
| 5. `missing_state_rejected_outlook` | same `if not state:` | ✅ same code path as 2 |
| 6. `state_from_other_user_rejected` | Admin B's lookup key includes `admin_b.pk` → not in cache → 400 | ✅ cache key at `:132` and `:182` both include `{request.user.pk}` |

Every `mock_exchange.assert_not_called()` in the tests corresponds to the
short-circuit `return Response(...status=400)` on the unauthorised path in
`views.py` — the `provider_mod = _get_provider_module(provider)` +
`provider_mod.exchange_code(...)` call at `:199–214` is unreachable when
state validation fails. Static confidence is high.

### Docstring cleanup is precise

- Verified file-wide: `grep "Currently FAILS\|currently fail\|Will PASS after"`
  on `tests_views.py` returns **no matches**. The TDD-red language is
  gone.
- Replaced with "Fixed by BE-SEC-P1-OAUTH-STATE-CSRF:" followed by the
  specific code-path the fix uses. Each of the 6 docstrings now
  describes the stable contract rather than an obsolete pending state.
- No assertion logic, setup, or mock patterns changed — only prose.

### Correct read of the sandbox blocker

QA's refusal to make up a "6 PASS" number they didn't observe is the
right call. Static analysis + explicit acknowledgment of the gap is
preferable to a fabricated result. Backend-security made the same call
on 2026-04-21 ("BE-SEC-P0-AUDIT-TEST-RUN-SANDBOX-BLOCKED"); the pattern
is consistent across agents and the right one.

## Commit-Together Plan

The prior review approved the 6 tests and the views.py fix landing as one
commit. That plan is unchanged. The full commit per QA's proposal:

- `apps/integrations_calendar/views.py` — OAuth state fix (already in tree)
- `apps/integrations_calendar/tests_views.py` — 6 new tests, docstrings now
  reflect passing state
- Plus the rest of the untracked `apps/integrations_calendar/` app
  (providers, tasks, models, urls)

All of that directory is currently `??` in `git status`, so a single
atomic commit is the correct landing strategy.

## Outstanding (not owed by qa-tester)

- **Live pytest run** — routed to devops (who can run
  `docker compose exec web pytest …`) or a human operator. Same
  unblocker as BE-SEC-P0-AUDIT-TEST-RUN-SANDBOX-BLOCKED; pairing the two
  test-runs in one devops session is efficient.
- **CI gate** — once the app lands, backend-engineer + devops should
  ensure the new tests are picked up by the default CI matrix so future
  PRs touching `integrations_calendar/` re-run them automatically.

## Recommendation

Approved as-is on the code-inspection axis. Close
`BE-SEC-P1-OAUTH-STATE-CSRF` as **implemented + tested (static-verified)**
in shared-log; final close-out depends on the live pytest run above.
QA-tester has nothing further owed on this ticket.

— reviewer (lp-reviewer)
