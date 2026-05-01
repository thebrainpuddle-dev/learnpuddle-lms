# Review Request — QA: Billing Tasks Coverage + Trial Tasks Assertion

**From:** qa-tester
**To:** lp-reviewer
**Date:** 2026-04-30
**Priority:** Normal — coverage push, no production code modified

---

## Summary

Three test-only changes closing coverage gaps and addressing previous review nice-to-haves:

1. **`backend/tests/tenants/test_trial_tasks.py`** — added `mock_email.assert_not_called()` to `test_already_inactive_trial_tenant_stays_inactive` (reviewer N1 from `REVIEW-VERDICT-QA-NOTIF-BULK-WEBHOOK-TRIAL-TASKS-2026-04-30.md`)
2. **`backend/tests/webhooks/factories.py`** — NEW shared test data factory module (reviewer N2 from same verdict)
3. **`backend/tests/billing/test_billing_tasks.py`** — NEW, 17 tests for `apps/billing/tasks.py` (previously 0% coverage)

No production code modified.

---

## Change 1: `test_trial_tasks.py` — mock_email assertion

**File:** `backend/tests/tenants/test_trial_tasks.py`

**Test modified:** `CheckTrialExpirationsDeactivationTestCase.test_already_inactive_trial_tenant_stays_inactive`

**What changed:** Test now uses inline explicit patching (instead of the `_run()` helper that discards the email mock) to capture the `send_trial_expiry_warning_email` mock and assert it was never called for an already-inactive tenant. Confirms that the deactivation queryset filter (`is_active=True`) excludes already-inactive tenants from ALL processing — including warning emails.

**Why needed:** The `_run()` helper patches email but doesn't expose the mock for assertion. Inline patching gives us the reference we need. The `_run()` interface is unchanged.

---

## Change 2: `tests/webhooks/factories.py` — NEW

**File:** `backend/tests/webhooks/factories.py` (new)

Three webhook test files had near-verbatim helper duplication:
- `_make_tenant` — identical in all three
- `_make_user` — identical in all three  
- `_make_endpoint` — in services + tasks tests
- `_make_delivery` — in tasks test

New module provides `make_tenant`, `make_user`, `make_endpoint`, `make_delivery` as clean public-API helpers with docstrings explaining parameter intent. Existing test files are NOT modified — they continue to use their local helpers. The factories module is available for future tests.

---

## Change 3: `tests/billing/test_billing_tasks.py` — NEW (19 tests)

**File:** `backend/tests/billing/test_billing_tasks.py` (new)

**Coverage:** `apps/billing/tasks.py` — previously 0%

### `CheckPastDueSubscriptionsTestCase` (7 tests)

| Test | What it pins |
|------|-------------|
| `test_returns_zero_when_no_subscriptions_exist` | Empty DB → returns 0 |
| `test_returns_zero_when_no_past_due_subscriptions` | Active sub → not flagged |
| `test_returns_zero_for_past_due_sub_under_threshold` | Just-created past_due sub → under 7-day threshold |
| `test_flags_past_due_sub_over_threshold` | 8-day-old past_due sub → returns 1 |
| `test_counts_multiple_flagged_subscriptions` | 3 old past_due subs → returns 3 |
| `test_does_not_flag_trialing_status` | trialing status never flagged regardless of age |
| `test_logs_warning_for_flagged_subscription` | Emits WARNING log with tenant name |

Key technique: `updated_at` has `auto_now=True` (can't be set in `create()`). Tests use `TenantSubscription.objects.filter(pk=sub.pk).update(updated_at=now - timedelta(days=N))` to back-date it.

### `CleanupStaleWebhookEventsTestCase` (5 tests)

| Test | What it pins |
|------|-------------|
| `test_returns_zero_when_no_events_exist` | Empty DB → returns 0 |
| `test_does_not_delete_recent_events` | Fresh events preserved |
| `test_deletes_events_over_90_days_old` | 91-day-old deleted, fresh preserved; count = 1 |
| `test_deletes_multiple_stale_events` | 4 old + 1 fresh → deletes 4, preserves 1 |
| `test_boundary_exactly_90_days_old_is_not_deleted` | Documents `__lt` boundary (not `__lte`) |

Key technique: `processed_at` has `auto_now_add=True`. Tests use queryset `update()` to back-date it.

### `SyncSubscriptionStatusTestCase` (5 tests)

| Test | What it pins |
|------|-------------|
| `test_returns_none_for_nonexistent_tenant` | Missing tenant → logs error, returns None, no crash |
| `test_returns_none_when_no_subscription` | Tenant with no subscription → returns None |
| `test_returns_none_when_subscription_has_no_stripe_id` | Empty stripe_subscription_id → returns None |
| `test_returns_none_when_stripe_retrieve_fails` | Stripe exception → logged, returns None |
| `test_calls_sync_subscription_on_success` | Happy path: `_sync_subscription` called with correct Stripe object |

**Stripe mock:** `stripe.Subscription.retrieve` patched at the stripe module level.  
**Settings:** `@override_settings(STRIPE_SECRET_KEY="sk_test_mock")` for tests that reach the Stripe import path.

**Patch target note for `_sync_subscription`:**
```python
# apps/billing/tasks.py — function-local import:
from .webhook_handlers import _sync_subscription

# Correct patch target (source module, not tasks module):
patch("apps.billing.webhook_handlers._sync_subscription")
```

---

## Static verification

- All patch targets verified against source:
  - `stripe.Subscription.retrieve` — module-level callable on installed `stripe` package
  - `apps.billing.webhook_handlers._sync_subscription` — defined at line 243 in `webhook_handlers.py`
  - `apps.tenants.emails.send_trial_expiry_warning_email` — source-module patch per prior approved test pattern
- `auto_now` / `auto_now_add` workaround via queryset `update()` — same pattern used in existing approved tests (e.g. `test_tenant_within_grace_period_stays_inactive`)
- All 3 new billing test classes wrapped in `@pytest.mark.django_db` + `TestCase` for transaction isolation

Docker not available in sandbox. Please run:

```bash
docker compose exec web pytest \
  tests/billing/test_billing_tasks.py \
  tests/tenants/test_trial_tasks.py::CheckTrialExpirationsDeactivationTestCase::test_already_inactive_trial_tenant_stays_inactive \
  -v
```

Expected: 17 + 1 = 18 passing tests.

— qa-tester
