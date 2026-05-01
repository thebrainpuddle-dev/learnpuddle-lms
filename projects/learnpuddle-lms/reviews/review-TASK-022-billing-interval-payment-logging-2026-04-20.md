---
tags: [review, task/TASK-022, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: TASK-022 — Billing Interval on Create + Payment-Failed Logging Follow-up

## Verdict: APPROVE

## Summary
Both findings from the TASK-022 doc are addressed cleanly. The `billing_interval`
is now propagated end-to-end via Stripe checkout-session metadata (no extra API
round-trip), and the charge-retrieval failure path in `handle_invoice_payment_failed`
is promoted from `logger.debug` → `logger.warning`. Changes are small, surgical,
and backward-compatible with pre-deploy sessions.

## Scope audited
- `backend/apps/billing/stripe_service.py` — added `'billing_interval': interval`
  to `create_checkout_session` metadata.
- `backend/apps/billing/webhook_handlers.py` — reads & validates the metadata
  field in `handle_checkout_session_completed`; `logger.warning` on charge
  retrieval exception in `handle_invoice_payment_failed`.

(Note: `backend/apps/billing/views.py` and `backend/apps/billing/webhook_views.py`
also have modifications in the working tree — open-redirect defense and Stripe
webhook throttling/error-class handling. These are excellent and security-positive,
but are **out of scope** for this review request. Recommend they be tracked under
a separate task/review so they get explicit sign-off and dedicated tests.)

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

**M1 (test gap) — No regression test for `billing_interval='year'` propagation.**
The author already acknowledges this in the task doc and assigns it to qa-tester
("suggest qa-tester adds this"). The existing tests
(`tests/billing/test_billing_views.py::TestHandleCheckoutSessionCompleted`) still
pass because they rely on the `'month'` fallback — which *is* the backward-compat
path, so coverage of the new branch is implicit. Not blocking, but I'd like to
see one explicit test before we close TASK-022 out:

```python
def test_yearly_session_sets_billing_interval_year(self, db, tenant, plan_pro):
    session = _make_checkout_session(tenant.id, "PRO")
    session.metadata["billing_interval"] = "year"
    event = _make_event("checkout.session.completed", "evt_year", session)
    webhook_handlers.handle_checkout_session_completed(event)
    ts = TenantSubscription.objects.get(tenant=tenant)
    assert ts.billing_interval == "year"

def test_invalid_interval_falls_back_to_month(self, db, tenant, plan_pro):
    session = _make_checkout_session(tenant.id, "PRO")
    session.metadata["billing_interval"] = "week"  # not in whitelist
    event = _make_event("checkout.session.completed", "evt_bad", session)
    webhook_handlers.handle_checkout_session_completed(event)
    ts = TenantSubscription.objects.get(tenant=tenant)
    assert ts.billing_interval == "month"
```

These two tests are inexpensive (builds on the existing `_make_checkout_session`
helper) and lock in the guard against unexpected values.

**M2 (cosmetic) — Constant extraction.**
`('month', 'year')` appears as a magic tuple in `webhook_handlers.py` but the
valid intervals are already implicit in `SubscriptionPlan` (monthly/yearly price
IDs) and `TenantSubscription.billing_interval` choices. A module-level constant
or shared choice (e.g., `VALID_BILLING_INTERVALS`) would be slightly nicer, but
this is a 2-line scope change and not worth blocking on.

## Positive Observations

- **No extra Stripe API call.** Using metadata on the checkout session avoids a
  `stripe.Subscription.retrieve()` call on the webhook hot-path. Good instinct.
- **Defense-in-depth.** The `if billing_interval not in ('month', 'year')`
  guard protects against a tampered/stale metadata blob producing an invalid
  enum value in the DB. Good.
- **Backward-compatible deploy.** The `.get('billing_interval', 'month')`
  fallback means in-flight sessions created before this deploy continue to work,
  and the correct value is still set shortly after by the
  `customer.subscription.created` event. No migration, no flag, no user impact.
- **logger.warning upgrade is correct.** A charge-retrieval failure on a
  payment-failed event is genuinely unexpected (Stripe normally gives us the
  charge) — `warning` lets it surface in log filters without drowning the
  channel in `debug` noise. Right level.
- **Comments are excellent.** The `# NEW: forwarded to webhook handler` and
  transition-comment style match the TASK-008 `# TASK-012 transition` pattern
  the team has adopted — future readers will understand the *why*, not just
  the *what*.

## Security / tenancy check
- No secrets introduced, no raw SQL, no tenant isolation impact (webhook is
  signature-verified and unauth'd by design; tenant lookup is by ID/customer_id).
- Metadata from Stripe is treated as untrusted — the whitelist guard is correct.

## Decision
**APPROVE.** Ship it. Please track M1 (two tests) as a follow-up in the QA
coverage inbox so we don't lose it.

---

Reviewer: lp-reviewer
