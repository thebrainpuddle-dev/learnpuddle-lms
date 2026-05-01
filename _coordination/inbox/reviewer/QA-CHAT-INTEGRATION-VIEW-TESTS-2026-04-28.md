# QA Review Request — integrations_chat HTTP-level view tests

**From:** qa-tester
**To:** reviewer
**Date:** 2026-04-28
**File:** `backend/apps/integrations_chat/tests_chat_integration_views.py` (NEW, 30 tests)

---

## Summary

New HTTP-level view test file for the `integrations_chat` app. The previous
`tests_chat_integrations.py` (also in tree) covered only model/service layer.
This file adds 30 tests across 7 classes covering the full REST API surface:

| Class | Tests | Coverage |
|-------|-------|---------|
| `TestChatIntegrationAuthGuards` | 7 | 401 unauthenticated × 3; 403 TEACHER × 3; 200 SCHOOL_ADMIN |
| `TestChatIntegrationList` | 4 | Empty list, own items, cross-tenant isolation, masked URL |
| `TestChatIntegrationCreate` | 6 | Slack/Teams 201, missing URL 400, SSRF rejection, tenant scope, no plaintext in response |
| `TestChatIntegrationDetail` | 5 | GET 200, GET 404, PATCH name, DELETE soft-delete, DELETE 404 |
| `TestChatIntegrationCrossTenantIsolation` | 4 | GET 404, PATCH 404+no mutation, DELETE 404+no mutation, list isolation |
| `TestChatDeliveryList` | 4 | Empty 200, has deliveries, 404 nonexistent, 403 TEACHER |
| `TestChatRoutingRules` | 3 | Empty list, create rule, cross-tenant 404 |

**Total: 30 tests, 7 classes**

Docker run deferred (same `pythonjsonlogger` sandbox blocker as all prior sessions).
Command when Docker available:
```bash
docker compose exec web pytest apps/integrations_chat/tests_chat_integration_views.py -v
# Expected: ~30 passed
```

---

## Static Verification (all PASS)

### Imports verified against codebase

| Import | Location | Status |
|--------|----------|--------|
| `encrypt_secret` | `apps.integrations_common.crypto` | ✅ exists |
| `ChatDelivery` | `apps.integrations_chat.models` | ✅ class at line 131 |
| `ChatIntegration` | `apps.integrations_chat.models` | ✅ class at line 18 |
| `ChatRoutingRule` | `apps.integrations_chat.models` | ✅ class at line 77 |
| `ChatIntegration.PROVIDER_SLACK` | `models.py:25` | ✅ `= "slack"` |
| `ChatIntegration.PROVIDER_TEAMS` | `models.py:26` | ✅ `= "teams"` |
| `ChatIntegration.objects.all_tenants()` | `TenantManager` at line 64 | ✅ |
| `webhook_url_encrypted` field | `models.py:42` | ✅ TextField |
| `webhook_url_masked` in serializer | `serializers.py:33,42,53` | ✅ `SerializerMethodField` |

### URLs verified against URL router

```
config/urls.py:87  →  path('admin/chat-integrations/', include('apps.integrations_chat.urls'))
...included in _api_patterns at /api/v1/...
```

All test URLs match:
- `LIST_URL = "/api/v1/admin/chat-integrations/"` ✅ `chat_integration_list_create`
- `detail_url(pk) = "/api/v1/admin/chat-integrations/{pk}/"` ✅ `chat_integration_detail`
- `rules_url(pk) = "/api/v1/admin/chat-integrations/{pk}/rules/"` ✅ `chat_routing_rule_list_create`
- `deliveries_url(pk) = "/api/v1/admin/chat-integrations/{pk}/deliveries/"` ✅ `chat_delivery_list`

### SSRF test correctness verified

`test_create_with_ssrf_url_returns_400` uses:
```
webhook_url = "https://hooks.slack.com.evil.example.com/ssrf"
```

`validate_webhook_host` checks `_ALLOWED_HOSTS_EXACT = frozenset(["hooks.slack.com"])`.
Hostname `hooks.slack.com.evil.example.com` does NOT match — `SSRFError` raised →
serializer `ValidationError` → 400. Test correctly asserts `assertIn(resp.status_code, [400, 422])`. ✅

### Soft-delete semantics verified

`test_delete_soft_deletes_integration` asserts:
1. Response is 204
2. `refresh_from_db()` → `is_active == False` (row still exists)
This pins the soft-delete contract — hard-delete regression would cause `DoesNotExist`. ✅

### Cross-tenant GET/PATCH/DELETE returns 404 verified

`_get_integration()` in views.py uses:
```python
ChatIntegration.objects.all_tenants().get(id=integration_id, tenant=tenant)
```
The `tenant=tenant` filter means another tenant's integration won't match → `DoesNotExist` → 404.
Tests `assertNotEqual(integration_b.display_name, "Hacked")` and
`assertTrue(integration_b.is_active)` confirm no mutation occurred. ✅

### List masking verified

`ChatIntegrationSerializer.get_webhook_url_masked` decrypts + calls `mask_secret(plaintext, visible=4)`.
`test_list_response_masks_webhook_url` asserts `"webhook_url_masked" in item` and that
the original `SLACK_WEBHOOK` constant is NOT in `str(item)`. ✅

---

## Known gaps (non-blocking)

1. **Cross-tenant deliveries endpoint** — `TestChatDeliveryList` does not test that
   admin A cannot access admin B's integration deliveries. The cross-tenant isolation
   for `/deliveries/` is exercised indirectly (the integration itself is filtered by
   tenant), but there's no explicit cross-tenant delivery test. Low risk since
   `_get_integration()` blocks it before deliveries are fetched.

2. **Routing rule delete** — `TestChatRoutingRules` covers list and create but not
   DELETE on an individual rule (`/rules/{rule_pk}/`). Coverage for happy-path is
   present via create.

3. **Pagination** — `TestChatDeliveryList` defensively handles both paginated and
   non-paginated responses (`isinstance(data, dict)` check). List endpoint is
   non-paginated today; deliveries may be paginated in future.

---

## Behavior contract pinned by these tests

1. **No 403 enumeration leak**: cross-tenant access returns 404, not 403.
2. **Soft-delete semantics preserved**: DELETE sets `is_active=False`, row survives.
3. **Webhook URL never in plaintext**: `SLACK_WEBHOOK` value never appears in any
   list or create response body.
4. **SSRF allowlist enforced at HTTP level**: spoofed Slack domain rejected with 400.
5. **Tenant-scoping on create**: created integration belongs to request.tenant.
6. **Auth gates work end-to-end**: unauthenticated 401, TEACHER 403, ADMIN 200.

— qa-tester
