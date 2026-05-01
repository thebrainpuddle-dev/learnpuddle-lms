---
tags: [review, qa-coverage, area/billing, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: QA Coverage — `apps/billing/` views + webhook handlers

## Verdict: APPROVE

## Summary

Serious, well-organized coverage of previously-untested billing surface.
50 tests (qa-tester's estimate of ~41 undercounted by ~9) across 12
classes; every Stripe network call mocked at `apps.billing.stripe_service.*`;
cross-tenant isolation tests present on subscription detail + payment
history; webhook handlers covered for happy-path + missing-metadata +
unknown-tenant + idempotency. Two non-blocking production smells flagged
and filed as a follow-up spec (do-not-implement, per reviewer brief).

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

1. qa-tester's handoff notes "41 tests" but actual count is **50**
   (`grep -c "def test_"` on `backend/tests/billing/test_billing_views.py`).
   Not a blocker — undercount rather than overcount. Worth noting in the
   shared-log for accurate coverage metrics.
2. `stripe_service.py` itself is still only exercised through mocks at the
   call boundary. qa-tester correctly flagged this; recommended as a
   separate follow-up and not in scope here.

## Verification performed

### Mocking boundary (no real network)
- `grep -c "apps.billing.stripe_service"` shows 8 mock references across
  `create_checkout_session`, `create_portal_session`, `preview_plan_change`,
  and `_get_stripe().Charge.retrieve` (for payment-failed reason lookup).
- Webhook-handler tests call handlers directly with fabricated events —
  bypassing `construct_webhook_event` entirely. This is intentional and
  correct: signature verification is already covered by
  `test_stripe_webhook.py` and is not the behavior under test here.

### `StripeObj(dict)` helper (L540–L549)
- Subclasses `dict`; `__getattr__` falls back to `self[key]`. Supports
  both `obj["items"]["data"]` (dict) AND `obj.id` (attr) — matches how
  `webhook_handlers.py` consumes the real `stripe.stripe_object.StripeObject`.
  Correct.

### Class-by-class coverage
- `TestPlanList` — public access, inactive exclusion, sort order.
- `TestSubscriptionDetail` — 401/403 auth boundaries, 200 happy, 404
  no-subscription, **cross-tenant** (admin A → tenant B returns 404, not
  tenant B's data).
- `TestCreateCheckout` — teacher 403, enterprise rejection, inactive/unknown
  plan 404, foreign success_url + cancel_url rejected, happy-path Stripe
  call + payload assertion, Stripe exception → 400.
- `TestCreatePortal` — foreign return_url rejected, default return_url
  permitted in DEBUG, Stripe exception → 400.
- `TestPaymentHistory` — teacher 403, **cross-tenant** (tenant A never
  sees tenant B invoices).
- `TestPreviewPlanChange` — 403, happy, Stripe error → 400.
- `TestHandleCheckoutSessionCompleted` — creates TenantSubscription,
  flips `is_trial=False`, applies plan preset, idempotent on duplicate,
  missing-metadata / unknown-tenant / unknown-plan all recorded as errors.
- `TestHandleSubscriptionLifecycle` — `.created` sync; `.updated` →
  past_due; trialing populates trial_start/trial_end; yearly interval
  derived from Stripe price; plan resolved via price_id when metadata
  missing; tenant resolved via stripe_customer_id fallback; unknown
  tenant recorded; double-delivery of `.updated` is idempotent.
- `TestHandleSubscriptionDeleted` — marks canceled + canceled_at,
  downgrades to FREE via `apply_plan_preset`; unknown subscription id
  recorded.
- `TestHandleInvoicePaid` — PaymentHistory created (amount/status/linked
  subscription); no-tenant-for-customer records error + no row;
  idempotent update-in-place.
- `TestHandleInvoicePaymentFailed` — records failed PaymentHistory
  including `failure_reason` from Charge; blank charge → blank reason;
  unknown customer recorded.
- `TestIdempotencyTracking` — `_already_processed` + `_record_event`
  primitive behavior.

All six required webhook events are covered (checkout.session.completed,
subscription.created/updated/deleted, invoice.paid, invoice.payment_failed)
with happy + missing-metadata + unknown-tenant + idempotency cases.

### Production smells flagged by qa-tester (non-blocking)
- `webhook_handlers.py` L85: `billing_interval='month'` hardcoded on
  initial `checkout.session.completed` creation — confirmed. Comment
  says "Will be updated by subscription.created/updated." The race
  window qa-tester described is real but rare. Filed as
  `docs/coordination/TASK-022-billing-interval-idempotency-followup.md`
  per reviewer brief.
- `handle_invoice_payment_failed` swallows charge-retrieval failures at
  `logger.debug` — also captured in TASK-022 follow-up.

## Positive Observations

- Two proper cross-tenant isolation tests on the right endpoints
  (`subscription_detail`, `payment_history`). This is exactly the
  class of bug that can leak billing data between schools, and it's
  now regression-guarded.
- Idempotency tests on both the dispatch-level (`_already_processed`
  primitive) AND at the handler level (duplicate delivery of
  `.updated` / `.paid` / `.session.completed`). Thorough.
- Every Stripe error path surfaces as HTTP 400 with no leak of the
  underlying exception — asserted on every view-level Stripe mock.
- `StripeObj(dict)` is a really clean stand-in; it prevents the common
  "real code uses `obj.id`, test uses `obj['id']`" drift.

## Follow-up items

- `docs/coordination/TASK-022-billing-interval-idempotency-followup.md`
  created (documentation only; no implementation requested in this pass).
