# QA: Chat Integration Cross-Tenant Gap Tests

**From:** qa-tester
**To:** reviewer
**Date:** 2026-04-28
**Re:** REVIEW-VERDICT-QA-2026-04-28-batch.md — gap items for `/deliveries/` + routing-rule DELETE

---

## Summary

Addressed two explicit gaps from the QA-CHAT-INTEGRATION-VIEW-TESTS batch
review ("add cross-tenant test for /deliveries/ and routing-rule DELETE").

**File changed:** `backend/apps/integrations_chat/tests_chat_integration_views.py`

**Net change:** +3 tests (34 → 37)

---

## Tests added

### 1. `TestChatDeliveryList::test_admin_cannot_access_other_tenant_deliveries`

Cross-tenant isolation for `GET /api/v1/admin/chat-integrations/{pk}/deliveries/`:

- Sets up tenant A + tenant B with their own integrations.
- Creates a `ChatDelivery` on tenant B's integration (to confirm data exists to leak).
- Tenant A's admin GETs the deliveries URL using tenant B's integration pk.
- Asserts 404 (not 200, not 403 — consistent with the other cross-tenant pattern).

This pins the invariant that the delivery history for tenant B is invisible
to tenant A, even if tenant A's admin guesses the integration UUID.

### 2. `TestChatRoutingRules::test_delete_routing_rule_returns_204`

Happy-path DELETE for `DELETE /api/v1/admin/chat-integrations/{pk}/rules/{rule_pk}/`:

- Creates a routing rule via POST (asserts 201).
- DELETEs the rule via the detail URL.
- Asserts 204 No Content.
- Asserts a subsequent GET on the same URL returns 404 (rule is gone).

This is the first DELETE coverage for the rule detail endpoint.

### 3. `TestChatRoutingRules::test_delete_routing_rule_cross_tenant_returns_404`

Cross-tenant isolation for routing-rule DELETE:

- Creates a routing rule on tenant B's integration via B's admin client.
- Attempts DELETE via tenant A's admin (wrong Host header / different tenant).
- Asserts 404 (no enumeration leak).
- Asserts `ChatRoutingRule.objects.filter(id=rule_pk).exists()` is True
  — verifies the rule was NOT deleted by the cross-tenant request.

---

## Invariants verified against production code

- `chat_routing_rule_detail` (views.py:243) calls `_get_integration(pk, tenant)` first.
  If the integration isn't in the request tenant, returns 404 — so a tenant A request
  with tenant B's integration pk will 404 before even looking up the rule.
- `chat_delivery_list` (views.py:283) similarly calls `_get_integration(pk, tenant)`
  before returning deliveries — same 404 guarantee.

---

## Docker run command

```bash
docker compose exec web pytest \
  apps/integrations_chat/tests_chat_integration_views.py -v
```

Expected: **37 PASS** (was 34 after earlier tightening session).

---

— qa-tester
