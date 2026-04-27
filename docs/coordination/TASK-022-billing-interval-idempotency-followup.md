# TASK-022 — Billing webhook: interval-on-create + payment-failed logging follow-up

**Status:** done (Finding 1 implemented 2026-04-20; Finding 2 implemented 2026-04-20; tests confirmed 2026-04-21)
**Filed by:** reviewer (lp-reviewer)
**Date:** 2026-04-20
**Origin:** QA billing coverage review (`projects/learnpuddle-lms/reviews/review-QA-billing-coverage-2026-04-20.md`)
**Priority:** Low

## Context

qa-tester landed `backend/tests/billing/test_billing_views.py` (50 tests covering billing views + all webhook handlers). During that work, two non-blocking production smells surfaced. Tests were added to document the current behavior; this doc captures the recommended fixes so they aren't lost.

## Finding 1 — `billing_interval` hard-coded to `"month"` on initial creation

**Location:** `backend/apps/billing/webhook_handlers.py` L85

```python
# handle_checkout_session_completed
TenantSubscription.objects.create(
    ...
    billing_interval='month',  # Will be updated by subscription.created/updated
    ...
)
```

### Why it's a smell

Stripe does not guarantee webhook-delivery order. If `customer.subscription.created` is processed **before** `checkout.session.completed` for a yearly subscription, the sequence is:

1. `subscription.created` arrives → `_sync_subscription` tries to update a subscription that doesn't exist yet → falls through into error path (or creates with correct yearly interval, depending on handler branch).
2. `checkout.session.completed` then arrives → `handle_checkout_session_completed` overwrites with `billing_interval='month'`.

Net result: a yearly subscription briefly shows as monthly in the admin UI and in PaymentHistory views. Self-heals on the next `subscription.updated` — but could be visible for minutes to hours.

### Recommended fix

Derive `billing_interval` from the Stripe session at creation time. `checkout.Session` exposes the price info via `line_items` or the subsequent `subscription` object. Cleanest pattern:

```python
stripe = _get_stripe()
sub = stripe.Subscription.retrieve(session.subscription)
price = sub['items']['data'][0]['price']
billing_interval = 'year' if price['recurring']['interval'] == 'year' else 'month'
```

Alternative: re-use the existing `_sync_subscription(sub)` path inside `handle_checkout_session_completed` so one code path owns interval resolution.

### Tests to add

- checkout.session.completed for a yearly price → TenantSubscription.billing_interval == 'year'.

## Finding 2 — `handle_invoice_payment_failed` silently swallows charge-retrieval failures

**Location:** `backend/apps/billing/webhook_handlers.py` (search for `Charge.retrieve` in the payment-failed handler)

Current behavior: on `Charge.retrieve` exception, `logger.debug(...)` and continue with blank `failure_reason`.

### Why it's a smell

Failed-payment webhooks are dunning-critical. If we lose the failure reason, we lose the ability to tell a customer *why* their payment failed in the dashboard ("card declined" vs "insufficient funds" vs "fraud_hold"). `logger.debug` is below the default production log level — these incidents become invisible.

### Recommended fix

- Change `logger.debug(...)` → `logger.warning(...)` with structured fields (`stripe_invoice_id`, `charge_id`, `exception class name`).
- Consider capturing the error in Sentry (if `SENTRY_DSN` configured).
- Keep the "continue with blank reason" fallback — we still want to record the PaymentHistory row even if we couldn't retrieve the charge.

### Tests to add

- Charge.retrieve raises → PaymentHistory still recorded (already covered), AND logger.warning was called (new assertion).

## Out of scope for TASK-022

- Full refactor of `_sync_subscription` / order-insensitive webhook processing.
- Stripe event replay tooling.
- Retry policy for failed `Charge.retrieve` calls.

## Acceptance (if/when implemented)

- [x] `billing_interval` resolved from Stripe on initial `checkout.session.completed` creation.
- [x] Regression test for yearly plan checkout → `billing_interval='year'`. (Confirmed by qa-tester 2026-04-21: `test_yearly_checkout_sets_billing_interval_year` at line 717-745 in `backend/tests/billing/test_billing_views.py`)
- [x] `handle_invoice_payment_failed` uses `logger.warning` (not `debug`) on charge-retrieval failure.
- [x] Existing 50-test suite confirmed present (qa-tester 2026-04-21).

## Implementation Notes (2026-04-20)

### Finding 1 — `billing_interval` derivation (backend-engineer)

**Chosen approach: embed `billing_interval` in the Stripe checkout session metadata.**

This avoids an extra `stripe.Subscription.retrieve()` API call and uses the same
pattern already established for `tenant_id` / `plan_code` in the session metadata.

Changes:

| File | Change |
|------|--------|
| `backend/apps/billing/stripe_service.py:54` | Added `'billing_interval': interval` to session `metadata` dict |
| `backend/apps/billing/webhook_handlers.py:75-94` | Reads `session.metadata.get('billing_interval', 'month')` with a `('month', 'year')` guard; removes hardcoded `'month'` |

Backward compatibility: the `'month'` fallback in the webhook handler means sessions
created before this change land safely (the subscription.created event corrects the
value shortly after regardless).

### Finding 2 — `logger.debug` → `logger.warning` (already fixed)

`handle_invoice_payment_failed` at line 210 already uses `logger.warning`. This was
fixed in an earlier backend-engineer session (shared-log 2026-04-20 follow-up entry).

## Owner

backend-engineer
