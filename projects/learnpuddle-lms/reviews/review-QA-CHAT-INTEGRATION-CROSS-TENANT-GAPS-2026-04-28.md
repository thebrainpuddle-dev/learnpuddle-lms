---
tags: [review, task/QA-CHAT-INTEGRATION-CROSS-TENANT, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-28
---

# Review: QA — Chat Integration Cross-Tenant Gap Tests

## Verdict: APPROVE

## Summary
Three focused tests that close the explicit gap items from the prior
QA-CHAT-INTEGRATION-VIEW-TESTS batch review: cross-tenant isolation for the
delivery history endpoint and both happy-path + cross-tenant DELETE coverage
for the routing-rule detail endpoint. Tests pin the right invariants and
match the production behaviour I verified in `views.py`.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
None worth blocking on. One nit:
- The `rule_detail` URL is constructed inline with f-strings in two tests
  (lines 651, 682). A `rule_detail_url(integration_pk, rule_pk)` helper next to
  the existing `rules_url`/`deliveries_url` helpers would be more consistent.
  Skip unless a third caller appears.

## Positive Observations
- **404-not-403 invariant** is asserted with a clarifying message
  ("no enumeration leak"). This is the right pattern — protects against tenant
  enumeration via timing/status differences.
- **Data-presence guard.** `test_admin_cannot_access_other_tenant_deliveries`
  creates a real `ChatDelivery` on tenant B before the cross-tenant request,
  so a regression to `200 []` would still fail the test (status check). Good
  defensive design.
- **Negative-confirm on DELETE.** `test_delete_routing_rule_cross_tenant_returns_404`
  doesn't just assert 404 — it also queries `ChatRoutingRule.objects.filter(...)`
  to prove the rule was *not* deleted. That's the assertion that actually
  catches the dangerous regression (silent cross-tenant write).
- **Production code verified.** I traced `chat_routing_rule_detail`
  (views.py:243–271) and `chat_delivery_list` (views.py:283–309). Both call
  `_get_integration(pk, tenant)` as the first step and return 404 when the
  integration isn't in the request tenant — matching the QA's claimed
  invariant. The DELETE branch correctly executes only after the integration
  scope check passes.
- **Reused helpers.** `make_tenant`, `make_user`, `make_integration`,
  `auth_client`, `rules_url`, `deliveries_url` — no test-helper drift,
  consistent with the rest of the file.
- **Happy-path DELETE included** (`test_delete_routing_rule_returns_204`)
  with a follow-up GET → 404 check, so we know DELETE actually deletes.

## Files Verified
- `backend/apps/integrations_chat/tests_chat_integration_views.py` — 3 new tests
  at lines 569, 640, 662. Total tests in file now consistent with claimed 37.
- `backend/apps/integrations_chat/views.py` — production invariants confirmed
  (lines 243–271, 283–309).

## Status Update
- QA-CHAT-INTEGRATION-CROSS-TENANT-GAPS → `status/done`
