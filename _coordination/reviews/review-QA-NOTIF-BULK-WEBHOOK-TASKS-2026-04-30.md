---
tags: [review, qa, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-30
---

# Review: QA-NOTIF-BULK + QA-WEBHOOK-TASKS + QA-TENANT-TRIAL-TASKS Coverage Batch

## Verdict: APPROVE

## Summary
Three coverage gaps closed in one batch (notification bulk-mark-read polish,
webhook tasks 0%→full, trial tasks 0%→full). Tests are behaviour-focused,
trace cleanly to production seams, and use the correct patch targets for
Celery tasks that perform function-local imports. No production code touched.

## Verification performed

### 1. `tests/notifications/test_notification_views.py` — bulk mark-read polish
- **m1 docstring fix** (line 624): now reads
  `"Cross-teacher isolation (same tenant): ..."` — accurate for what the
  test actually exercises.
- **`test_bulk_mark_read_is_idempotent`** (line 641): asserts
  `marked_read == 1` on first call, `0` on second; final
  `notif1.refresh_from_db(); is_read == True`. Mirrors the existing
  archive-idempotent test — symmetric coverage.
- **`test_bulk_mark_read_does_not_affect_other_tenant_notifications`**
  (line 671): creates Tenant B + teacher B + notification B, submits both
  IDs to Tenant A's endpoint; asserts `marked_read == 1` and Tenant B's
  notification stays `is_read=False`. Genuine cross-tenant isolation
  guard, not just same-tenant cross-teacher.

### 2. `tests/webhooks/test_webhook_tasks.py` — NEW (425 lines, 20 tests)
- Module docstring (lines 10–27) explains *why* `execute_delivery` must
  be patched at `apps.webhooks.services.execute_delivery` rather than
  `apps.webhooks.tasks.execute_delivery` (function-local import in
  `tasks.py:28`). Verified against production code — correct, and the
  comment is exactly the kind of regression guard that prevents future
  "fix the patch target" PRs that would silently break the tests.
- `DeliverWebhookTaskTestCase` (7 tests) covers all branches in
  `tasks.py:21-51`: missing delivery, already-success short-circuit,
  inactive endpoint → `failed` + `"disabled"` message, active call,
  no-retry-on-success, retrying triggers `raise self.retry(...)`
  (asserted strictly via `pytest.raises(Retry)` — no swallow-everything
  catch that would mask production bugs), correct delivery passed.
- `RetryFailedWebhooksTaskTestCase` (6 tests) covers `tasks.py:55-77`:
  empty queue, past `next_retry_at` re-queues with count, future
  `next_retry_at` skipped, inactive endpoint skipped, success/failed
  statuses never re-queued.
- `CleanupOldDeliveriesTaskTestCase` (7 tests) covers `tasks.py:81-97`:
  cutoff math, success/failed deletion, retrying/pending preservation,
  default 30-day window, deletion count.

### 3. `tests/tenants/test_trial_tasks.py` — NEW (336 lines, 18 tests)
- Patches `apps.tenants.tasks.timezone.now` (correct — `timezone` is
  imported at module top, line 10, so this is the right target).
- Patches `apps.tenants.emails.send_trial_expiry_warning_email` at the
  *source* module with an explanatory comment — correct because
  `tasks.py:60` does a function-local `from apps.tenants.emails import ...`.
- `CheckTrialExpirationsDeactivationTestCase` (7 tests): boundary test
  for `__lt` vs `__lte` is included (`test_tenant_within_grace_period_stays_active`)
  — confirms the production filter `trial_end_date__lt=deactivation_cutoff`
  treats the boundary day as still in grace. I traced the math:
  today=2026-04-30, cutoff = today − 3 = 2026-04-27; tenant with
  `trial_end_date=2026-04-27` is *not* deactivated; tenant with
  `trial_end_date=2026-04-20` *is* deactivated. Test expectations
  match.
- `CheckTrialExpirationsWarningEmailTestCase` (5 tests): 7-day and
  3-day windows, 15-day silence, email-failure non-fatal, paid
  tenants excluded.
- `NotifySuperAdminDeactivationsTestCase` (6 tests): empty list
  short-circuit, `SUPER_ADMIN_EMAIL` configured/missing, body content,
  `fail_silently=True` semantics.

### Production code untouched
Spot-checked: `apps/webhooks/tasks.py` and `apps/tenants/tasks.py` are
unchanged from their last-reviewed state.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
None blocking. Two non-blocking observations:

- m1 (optional): `test_already_inactive_trial_tenant_stays_inactive`
  asserts the tenant remains `is_active=False`, but doesn't assert the
  warning-email branch was *not* called for it (the production filter
  already handles this via `is_active=True`). Adding a `mock_email.assert_not_called()`
  assertion would close a tiny gap. Nice-to-have only.

- m2 (optional): The webhook test docstring mentions the function-local
  import twice (module docstring + retry-test docstring). Could be
  consolidated to the module docstring alone. Pure aesthetics.

## Positive Observations
- The "patch at source module" comments in both new test files are exactly
  the kind of inline guard that prevents a future "fix" from silently
  breaking the suite. Excellent defensive documentation.
- `test_retrying_status_triggers_self_retry` deliberately avoids
  `except Exception` and uses `pytest.raises(Retry)` — refuses to mask
  production bugs behind a fake-pass. This is the right level of strictness.
- Cross-tenant test creates a real second tenant + teacher + notification,
  not just a mocked tenant — exercises the actual `tenant=request.tenant`
  filter in the queryset.
- Boundary-day test for `__lt` filter is the kind of detail that would
  catch a future "convert to `__lte`" mistake.

## Action
- Mark related QA notes (`QA-NOTIF-BULK-FIXUP`, `QA-WEBHOOK-TASKS-COVERAGE`,
  `QA-TENANT-TRIAL-TASKS-COVERAGE`) → **status/done**.
- No follow-ups required.

— lp-reviewer
