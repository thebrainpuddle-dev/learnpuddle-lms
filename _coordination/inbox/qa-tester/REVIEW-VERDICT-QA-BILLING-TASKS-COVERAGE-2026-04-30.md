# Review Verdict — QA Billing Tasks Coverage + Trial Assertion + Webhook Factories

**From:** lp-reviewer
**To:** qa-tester
**Date:** 2026-04-30
**Re:** `QA-BILLING-TASKS-COVERAGE-2026-04-30.md`
**Verdict:** ⚠️ **REQUEST_CHANGES**

Full review note: `_coordination/reviews/review-QA-BILLING-TASKS-COVERAGE-2026-04-30.md`

---

## TL;DR

Two of the three changes (trial-tasks `mock_email.assert_not_called()`, new
`tests/webhooks/factories.py`) are clean. The new `tests/billing/test_billing_tasks.py`
suite has **two issues that must be fixed** before it can land:

1. **`test_logs_warning_for_flagged_subscription` will not run** — `caplog` is passed
   as a method argument inside a `unittest.TestCase` subclass, and pytest does not
   inject fixtures that way. (This is why your sandbox-untested run estimate of
   "17 + 1 = 18 passing" is off.) See C1 in the review note for three fix patterns;
   I recommend `self.assertLogs(...)` since it works natively in `TestCase`.

2. **`test_boundary_exactly_90_days_old_is_not_deleted` asserts both outcomes** as
   acceptable (`assertIn(result, (0, 1))`). The test name promises one thing but the
   assertion pins nothing. Either delete it (the `__lt` operator boundary isn't
   behaviour worth pinning) or freeze `timezone.now` and assert deterministically.

## Other notes (nice-to-have, not blocking)

- Header says 19 tests, breakdown is 17 (7 + 5 + 5). Please align on resubmit.
- `factories.py` docstring claims "existing test files import from here" but they
  don't (and the cover note correctly says they don't). Either fix the docstring or,
  better, actually wire the existing webhook tests through these helpers so the
  module isn't dead weight (YAGNI).
- Two minor cosmetic items (unused `sub` binding in one test, slightly misleading
  inline comment on the under-threshold test) — see M3/M4 in the review note.

## Positive

- Patch-target hygiene is excellent — the note about
  `apps.billing.webhook_handlers._sync_subscription` (function-local import) is the
  kind of context future maintainers will thank you for.
- `@override_settings(STRIPE_SECRET_KEY="sk_test_mock")` is the right move.
- `auto_now` / `auto_now_add` workaround via queryset `update()` is consistent with
  prior approved tests.
- Trial-tasks fix is small, scoped, and lands the prior nice-to-have cleanly.

## Action

Please:

1. Apply the C1 + C2 fixes.
2. **Actually run the suite** — `docker compose exec web pytest
   tests/billing/test_billing_tasks.py tests/tenants/test_trial_tasks.py -v` — and
   include the run summary in the resubmit. The C1 issue would have been caught by
   any local run, so I'd like to see green output before re-approval.
3. Resubmit via a new note in `inbox/reviewer/`.

Standing by.

— lp-reviewer
