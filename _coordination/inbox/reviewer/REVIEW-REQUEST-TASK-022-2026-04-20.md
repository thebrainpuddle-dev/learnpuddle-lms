# Review Request: TASK-022 (Billing Interval + Payment Logging)

**From:** backend-engineer
**To:** reviewer
**Date:** 2026-04-20
**Task:** TASK-022 — Billing webhook: interval-on-create + payment-failed logging follow-up

---

## Summary

Both findings from the TASK-022 documentation have been resolved.

### Finding 1 — `billing_interval` no longer hardcoded to `'month'` ✅

**Approach**: embed `billing_interval` in the Stripe checkout session metadata at
creation time, then read it back in the webhook handler.

This avoids an extra `stripe.Subscription.retrieve()` API call. The `interval`
parameter is already available in `create_checkout_session()` — it just wasn't
being forwarded to the session metadata.

**`backend/apps/billing/stripe_service.py`**
```python
metadata={
    'tenant_id': str(tenant.id),
    'plan_code': plan.plan_code,
    'billing_interval': interval,  # NEW: forwarded to webhook handler
},
```

**`backend/apps/billing/webhook_handlers.py`**
```python
billing_interval = session.metadata.get('billing_interval', 'month')
if billing_interval not in ('month', 'year'):
    billing_interval = 'month'  # Guard against unexpected values
```

Backward-compatible: the `'month'` fallback handles sessions created before this
change. The `subscription.created` event corrects the value shortly after in any case.

### Finding 2 — `logger.warning` on charge-retrieval failure ✅

Already fixed in a prior session. Line 210 of `webhook_handlers.py` already uses
`logger.warning`. Confirmed in codebase.

---

## Files changed

| File | Change |
|------|--------|
| `backend/apps/billing/stripe_service.py` | Added `'billing_interval': interval` to session metadata |
| `backend/apps/billing/webhook_handlers.py` | Replaced hardcoded `'month'` with metadata read + validation guard |
| `docs/coordination/TASK-022-billing-interval-idempotency-followup.md` | Updated status, acceptance criteria, implementation notes |

## Acceptance criteria status

- [x] `billing_interval` resolved from Stripe on initial `checkout.session.completed`
- [ ] Regression test for yearly plan checkout → `billing_interval='year'` (suggest qa-tester adds this)
- [x] `handle_invoice_payment_failed` uses `logger.warning` on charge-retrieval failure
- [ ] Existing 50-test suite stays green (pending Docker CI)

---

Ready for review.
