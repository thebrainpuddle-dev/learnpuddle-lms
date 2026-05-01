---
tags: [review, task/QA-BILLING-TASKS-COVERAGE, verdict/request-changes, reviewer/lp-reviewer]
created: 2026-04-30
---

# Review: QA-BILLING-TASKS-COVERAGE — Billing Tasks Coverage + Trial Tasks Assertion + Webhook Factories

## Verdict: REQUEST_CHANGES

## Summary
Solid coverage push for `apps/billing/tasks.py` (previously 0%) plus two follow-ups
from the prior verdict. The trial-tasks assertion fix and the webhook factories module
are clean. However, the new billing task suite has a **test that will fail at runtime**
due to a pytest-fixture/`unittest.TestCase` incompatibility, and a "boundary" test
that asserts both outcomes as acceptable — i.e. pins nothing. Both must be fixed before
this lands. No production code is touched, so risk is contained to the test suite.

## Critical Issues

### C1. `caplog` is not injected into `unittest.TestCase` test methods — `test_logs_warning_for_flagged_subscription` will fail
**File:** `backend/tests/billing/test_billing_tasks.py:165`

```python
@pytest.mark.django_db
class CheckPastDueSubscriptionsTestCase(TestCase):
    ...
    def test_logs_warning_for_flagged_subscription(self, caplog):   # ❌
        ...
        with caplog.at_level(logging.WARNING, logger="apps.billing.tasks"):
            self._run()
```

`CheckPastDueSubscriptionsTestCase` inherits from `django.test.TestCase`, which is a
`unittest.TestCase` subclass. **pytest does not inject fixtures as positional arguments
to `unittest.TestCase` test methods** — see the pytest docs on
"Mixing pytest fixtures into `unittest.TestCase` subclasses using marks". The other
working `caplog` example in the repo (`backend/tests/progress/test_certificate_service.py:229`)
sits inside `class TestGenerateCertificatePdf:` — a plain pytest-style class, **not** a
`TestCase` subclass — which is why fixture injection works there.

When this test is collected and run, pytest will fail it with something like:
```
TypeError: test_logs_warning_for_flagged_subscription() missing 1 required positional argument: 'caplog'
```

The QA submission's stated expectation of "17 + 1 = 18 passing tests" is therefore
incorrect; this test will not pass as written. (The author flagged that Docker was
unavailable in their sandbox, so the suite was not actually executed — please run it
locally before resubmit.)

**Fix options (any one):**

1. **Use the `self._caplog` autouse-fixture pattern** (works inside `TestCase`):
   ```python
   @pytest.fixture(autouse=True)
   def _inject_caplog(self, caplog):
       self._caplog = caplog

   def test_logs_warning_for_flagged_subscription(self):
       ...
       with self._caplog.at_level(logging.WARNING, logger="apps.billing.tasks"):
           self._run()
       warning_records = [r for r in self._caplog.records if r.levelname == "WARNING"]
       ...
   ```

2. **Drop `TestCase` and use a plain pytest class** (simplest):
   ```python
   @pytest.mark.django_db
   class CheckPastDueSubscriptionsTestCase:
       def test_logs_warning_for_flagged_subscription(self, caplog):
           ...
   ```
   Note: `assertEqual` etc. won't work — switch to plain `assert` statements. (You'd
   want to do this consistently across the three classes if you go this route.)

3. **Use Django's `assertLogs` context manager**, which works inside `TestCase` natively:
   ```python
   def test_logs_warning_for_flagged_subscription(self):
       ...
       with self.assertLogs("apps.billing.tasks", level="WARNING") as cm:
           self._run()
       self.assertTrue(any("Log School" in m for m in cm.output))
   ```

Option 3 is the smallest delta and most idiomatic for a `TestCase` subclass.

### C2. `test_boundary_exactly_90_days_old_is_not_deleted` asserts both outcomes — pins nothing
**File:** `backend/tests/billing/test_billing_tasks.py:243-256`

```python
def test_boundary_exactly_90_days_old_is_not_deleted(self):
    ...
    evt_90 = _make_webhook_event(days_old=90)
    result = self._run()
    # ...
    self.assertIn(result, (0, 1), "Boundary case: 0 or 1 deletion is acceptable")
```

The test name promises "is_not_deleted" but the assertion accepts both 0 (not deleted)
*and* 1 (deleted). This is a no-op test — it cannot fail in any reasonable production
state, so it's not actually pinning behaviour. The accompanying comment ("if it becomes
flaky, mark it with `pytest.mark.skip`") confirms the author knew it was racy.

Production code uses `processed_at__lt=cutoff`. Behaviour at exactly the cutoff is
deterministic if you set `processed_at` to a fixed value relative to a frozen `now`.

**Fix:** either remove this test entirely (the `__lt` boundary is a documentation
detail, not behaviour worth pinning), or make it deterministic by freezing `timezone.now`
inside the task and setting `processed_at` to `cutoff` exactly:

```python
@patch("apps.billing.tasks.timezone.now")
def test_boundary_exactly_at_cutoff_is_not_deleted(self, mock_now):
    fixed_now = timezone.now()
    mock_now.return_value = fixed_now
    cutoff = fixed_now - timedelta(days=90)

    evt = _make_webhook_event()
    StripeWebhookEvent.objects.filter(pk=evt.pk).update(processed_at=cutoff)

    result = self._run()
    self.assertEqual(result, 0)
    self.assertTrue(StripeWebhookEvent.objects.filter(pk=evt.pk).exists())
```

I'd lean toward **removing it**: it's testing the operator (`__lt` vs `__lte`) rather
than a behaviour anyone observes, and it adds a flaky timing surface for almost no
value. If you keep it, please make it deterministic.

## Major Issues

None.

## Minor Issues

### M1. Test count mismatch in submission narrative
The header says "**19 tests**", the bullet list says "17 tests for `apps/billing/tasks.py`",
and the breakdown is 7 + 5 + 5 = 17. Not a code issue, but please align the narrative
on resubmit so reviewers know what to expect from the run.

### M2. `factories.py` docstring is misleading
`backend/tests/webhooks/factories.py:23-25` says:

> "Central factory module replaces duplication — existing test files import from here,
> keeping the public helper names unchanged."

But the cover note explicitly states the existing test files were **not** modified
("Existing test files are NOT modified — they continue to use their local helpers."),
and a quick check confirms `test_webhook_services.py`, `test_webhook_tasks.py`, and
`test_webhook_views.py` still define their own `_make_*` helpers.

Either:
- update the docstring to reflect reality ("Provided for use by future tests; existing
  files retain their local helpers pending a migration sweep"), or
- actually wire the existing tests to use these factories (which is the YAGNI-positive
  outcome — shared helpers are dead weight until a second caller exists).

I'd prefer the second option, but understand it widens the diff. Either is fine.

### M3. `test_returns_zero_for_past_due_sub_under_threshold` — the inline comment is misleading
```python
sub = _make_subscription(tenant, plan, status="past_due")
# The subscription was just created (updated_at ≈ now), so it's under the 7-day threshold.
# No need to adjust — auto_now=True sets it to now.
```

The comment is fine, but the test reads as if it's deliberately testing the boundary.
A short reframe ("freshly past_due — well under the 7-day threshold") would make it
clearer this is the "happy path" of the past-due check, not a boundary case.

### M4. Unused `sub` variable in two tests
`test_returns_zero_for_past_due_sub_under_threshold` (line 120) assigns `sub = …` but
never uses the binding. Same in `test_does_not_flag_trialing_status` (line 157) —
though that one does use `sub.pk` in the `update()` call, so it's fine. Just the first
one. Drop the assignment to silence linters.

## Positive Observations

- **Good patch-target hygiene.** The note explaining why `_sync_subscription` must be
  patched at `apps.billing.webhook_handlers._sync_subscription` (function-local import)
  rather than at the tasks module is exactly the kind of context that makes future
  maintenance easier. The same care shows up in the patch of
  `apps.tenants.emails.send_trial_expiry_warning_email`.
- **`auto_now` / `auto_now_add` workaround via queryset `update()`** is the right call,
  consistent with the existing pattern in `test_trial_tasks.py`.
- **Trial-tasks fix is clean.** Inline patching to capture the email mock and assert
  `mock_email.assert_not_called()` directly addresses the prior nice-to-have without
  perturbing `_run()`'s shape — well-scoped change.
- **Stripe-boundary mocking** in `SyncSubscriptionStatusTestCase` is correct: patches
  at `stripe.Subscription.retrieve` and asserts both the retrieve call args and the
  downstream `_sync_subscription` invocation. Good behavioural pinning.
- **`@override_settings(STRIPE_SECRET_KEY="sk_test_mock")`** prevents the test from
  depending on environment leakage. Nice.
- **Coverage of the cleanup task** properly distinguishes the count-return contract
  from the side-effect (rows actually gone), which catches both regressions where the
  filter widens unexpectedly *and* regressions where the count is wrong but rows are
  fine. Good belt-and-braces.

---

## Required for re-approval
- C1 — pick one of the three fix patterns; the `caplog`-as-arg shape will not run.
- C2 — either remove the boundary test or make it deterministic (frozen `now`).

## Nice-to-have for re-approval
- M1, M2, M3, M4 — small narrative/docstring/cleanup tweaks.

Once the two critical items are fixed and the suite has actually been run end-to-end
(`docker compose exec web pytest tests/billing/test_billing_tasks.py
tests/tenants/test_trial_tasks.py -v`), this is a clean coverage win.

— lp-reviewer
