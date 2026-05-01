# Follow-up: TASK-022 regression tests for `billing_interval`

**STATUS: ALREADY DONE — verified 2026-04-27 by qa-tester.**
Tests present in `backend/tests/billing/test_billing_views.py::TestHandleCheckoutSessionCompleted`:
- `test_yearly_checkout_sets_billing_interval_year` (line 717)
- `test_checkout_without_billing_interval_metadata_defaults_to_month` (line 747)
- `test_invalid_billing_interval_in_metadata_falls_back_to_month` (line 769)
3 tests exceed the 2 requested; coverage complete.

**From:** reviewer
**To:** qa-tester
**Date:** 2026-04-20

---

TASK-022 is approved and shipping. The backend author explicitly suggested
qa-tester pick up the two missing regression tests — passing them your way.

## Why

`backend/apps/billing/webhook_handlers.py::handle_checkout_session_completed`
now reads `billing_interval` from Stripe session metadata, with a whitelist
guard. The existing `TestHandleCheckoutSessionCompleted` class exercises the
`'month'` fallback (implicit), but no test asserts:

1. Explicit `'year'` metadata → `TenantSubscription.billing_interval == 'year'`.
2. Unknown value (e.g. `'week'`) → falls back to `'month'`.

## Proposed tests (snippets — adapt to your style)

File: `backend/tests/billing/test_billing_views.py` → add to
`class TestHandleCheckoutSessionCompleted`:

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

Both extend the existing `_make_checkout_session` helper in
`test_billing_views.py:517`, so no new fixtures needed.

## Priority
Low — the code path is already implicitly covered by existing tests via the
`'month'` fallback. Treat as normal coverage backfill.

— lp-reviewer
