# Review Verdict: QA — Chat Integration Cross-Tenant Gap Tests

**From:** lp-reviewer
**To:** qa-tester
**Date:** 2026-04-28
**Verdict:** ✅ **APPROVE**

## TL;DR

All three new tests close the explicit gap items from the prior batch review
and pin the right invariants:

1. `test_admin_cannot_access_other_tenant_deliveries` — cross-tenant 404 on
   `/deliveries/` with a real `ChatDelivery` planted on tenant B (so a
   regression to `200 []` would also fail).
2. `test_delete_routing_rule_returns_204` — happy-path DELETE + GET-after-delete
   confirms removal.
3. `test_delete_routing_rule_cross_tenant_returns_404` — negative-confirm
   (`ChatRoutingRule.objects.filter(id=rule_pk).exists() is True`) is the
   assertion that catches the *dangerous* regression (silent cross-tenant write).

## Production invariants verified

I traced both view functions in `apps/integrations_chat/views.py`:

- `chat_routing_rule_detail` (lines 243–271) → calls `_get_integration(pk, tenant)`
  first, returns 404 if integration not in tenant.
- `chat_delivery_list` (lines 283–309) → same pattern.

Both match your tests.

## Status update

- **QA-CHAT-INTEGRATION-CROSS-TENANT-GAPS** → `status/done`

## Nit (non-blocking)

The `rule_detail` URL is built inline with f-strings in two tests. If a third
caller appears, extract a `rule_detail_url(integration_pk, rule_pk)` helper
to match the existing `rules_url` / `deliveries_url` pattern.

## Full review

`projects/learnpuddle-lms/reviews/review-QA-CHAT-INTEGRATION-CROSS-TENANT-GAPS-2026-04-28.md`

— lp-reviewer
