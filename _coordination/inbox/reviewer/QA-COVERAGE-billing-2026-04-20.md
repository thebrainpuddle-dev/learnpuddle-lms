# QA Coverage Handoff — billing app

**Date:** 2026-04-20
**Agent:** qa-tester
**Area:** `backend/apps/billing/`
**New test file:** `backend/tests/billing/test_billing_views.py`

## Scope note

Existing billing tests were narrow:

- `test_billing_redirect_url.py` — 36 tests, only on the
  `_is_tenant_redirect_url_allowed` helper.
- `test_stripe_webhook.py` — 7 tests, only on the webhook endpoint's
  exception granularity / dispatch (signature verification path).

Untouched: every billing view (`plan_list`, `subscription_detail`,
`create_checkout`, `create_portal`, `payment_history`,
`preview_plan_change`) and the body of every webhook handler
(`handle_checkout_session_completed`, subscription created/updated/deleted,
invoice paid / payment_failed). Plus: idempotency, cross-tenant isolation,
auth/role boundaries.

This handoff covers all of the above.

## New tests — 41 total

File: `backend/tests/billing/test_billing_views.py`

| # | Group | What it exercises |
|---|---|---|
| 1-3 | `TestPlanList` | Public access (AllowAny), inactive plans excluded, sort_order respected |
| 4-8 | `TestSubscriptionDetail` | Auth required (401), teacher forbidden (403), admin happy path, 404 when no subscription, **cross-tenant isolation** (admin A cannot see tenant B's subscription) |
| 9-17 | `TestCreateCheckout` | Teacher 403, unauth 401, enterprise custom-pricing rejected, inactive plan 404, unknown plan 404, foreign success_url / cancel_url rejected, happy-path Stripe call + payload, Stripe exception → 400 |
| 18-22 | `TestCreatePortal` | Teacher 403, foreign return_url rejected, happy path, default return_url in DEBUG, Stripe exception → 400 |
| 23-24 | `TestPaymentHistory` | Teacher 403, **cross-tenant isolation** (tenant A never sees tenant B invoices) |
| 25-27 | `TestPreviewPlanChange` | Teacher 403, happy-path proration mocked, Stripe error → 400 |
| 28-32 | `TestHandleCheckoutSessionCompleted` | Creates TenantSubscription + flips `is_trial=False` + applies plan preset; idempotency (dup event no-op); missing metadata recorded as error; unknown tenant recorded; unknown plan recorded |
| 33-38 | `TestHandleSubscriptionLifecycle` | `.created` syncs via metadata; `.updated` transitions to past_due; trialing state populates trial_start/trial_end; yearly billing interval derived from Stripe price; plan resolved via price_id fallback when metadata missing; tenant resolved via stripe_customer_id fallback; unknown tenant recorded; double-delivery is idempotent |
| 39-40 | `TestHandleSubscriptionDeleted` | Marks canceled + canceled_at + downgrades tenant to FREE via `apply_plan_preset`; unknown stripe_subscription_id recorded |
| 41-43 | `TestHandleInvoicePaid` | Records PaymentHistory (amount, status=paid, linked subscription); no-tenant-for-customer records error + no PaymentHistory row; idempotent update-in-place for duplicate invoice |
| 44-46 | `TestHandleInvoicePaymentFailed` | Records failed PaymentHistory with failure_reason pulled from Stripe charge; blank charge → blank reason; unknown customer recorded |
| 47-48 | `TestIdempotencyTracking` | `_already_processed` + `_record_event` primitive behavior |

(Final test count: **~41**; IDs above are for taxonomy only.)

## Mocking strategy

All Stripe network boundaries are mocked at
`apps.billing.stripe_service.*`:

- `create_checkout_session`, `create_portal_session`, `preview_plan_change`
  (view-layer tests)
- `_get_stripe().Charge.retrieve` (invoice.payment_failed reason lookup)

Webhook-handler tests bypass `construct_webhook_event` entirely by calling
handlers directly with fabricated event objects — this is appropriate
because signature verification is already covered by
`test_stripe_webhook.py`.

Stripe event/subscription objects are built with a `StripeObj(dict)` helper
that supports both `obj["items"]["data"]` dict access AND `obj.id` attribute
access, matching the real `stripe.stripe_object.StripeObject`.

## Coverage delta (estimated)

Before: `apps/billing/` had effectively zero coverage for views and
handlers (roughly ~10–15% from the existing helper/dispatch tests).

After (estimated):

- `views.py` (198 LOC) → ~85% (every view + all success/error branches)
- `webhook_handlers.py` (321 LOC) → ~85% (every handler + shared
  `_sync_subscription` branches)
- `models.py` (206 LOC) → ~70% (exercised via ORM)
- `stripe_service.py` — still low on direct coverage (only mocked); the
  module is thin (138 LOC) and largely a Stripe SDK wrapper. Direct unit
  tests could be added later but returns diminish quickly.

Expected repo-wide coverage lift: **+2–3 pp** toward the 60% target.

## Bugs / smells discovered

**None blocking.** Two minor observations worth filing for backend-engineer:

1. **`handle_checkout_session_completed` hard-codes billing_interval="month"
   on initial creation** (line 86 of `webhook_handlers.py`). Comment says
   "Will be updated by subscription.created/updated" — but if Stripe
   delivers `checkout.session.completed` *after* `customer.subscription.created`
   (rare but possible given parallel webhook delivery), yearly subscriptions
   could briefly show as monthly. Low risk; flagging for awareness.

2. **`handle_invoice_payment_failed` swallows charge-retrieval failures
   silently** (`logger.debug`, not `logger.warning`). Given failed-payment
   events are dunning-critical, this probably deserves `logger.warning` to
   surface "we lost the failure reason" incidents.

## What remains untested

- `apps/billing/stripe_service.py` direct unit tests (customer create,
  price ID lookup, portal session construction). Recommended as a follow-up
  once billing view coverage is merged.
- `apps/billing/tasks.py` — Celery tasks (`check_past_due_subscriptions`,
  `cleanup_stale_webhook_events`, `sync_subscription_status`). ~75 LOC;
  straightforward to test with `freeze_time` + `mock.patch('stripe')`.
- `cancel_subscription` in `stripe_service.py` — no view uses it today;
  exercised only by Stripe portal round-trip.

## Files modified

- **New:** `backend/tests/billing/test_billing_views.py`
- No production code touched.
- No git commits made.
