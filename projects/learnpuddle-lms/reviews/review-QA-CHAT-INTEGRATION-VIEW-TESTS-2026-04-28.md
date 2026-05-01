---
tags: [review, task/QA-CHAT-INTEGRATION-VIEW-TESTS, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-28
---

# Review: QA-CHAT-INTEGRATION-VIEW-TESTS — HTTP-level coverage for integrations_chat

## Verdict: APPROVE

## Summary
Strong HTTP-level test suite complementing the existing model/service-layer tests. Covers auth guards, CRUD, cross-tenant isolation, delivery history, routing rules, soft-delete semantics, SSRF rejection at the API boundary, and webhook plaintext leak prevention. All routes, view names, and serializer behaviors verified against the codebase. Pins the security invariants the integrations_chat app advertises.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **Test count is 33, not 30** as stated in the request memo (7 + 4 + 6 + 5 + 4 + 4 + 3 = 33). Not a code issue, but the documentation should match — somebody reading the change log will be confused. Update the request memo or the docstring counts. **Documentation-only.**

2. **`test_list_response_masks_webhook_url` masking assertion is too lenient.** The current code:
   ```python
   if item.get("webhook_url_masked"):
       masked = item["webhook_url_masked"]
       self.assertIn("*", masked, "Masked URL should contain asterisks")
   ```
   The `if` guard silently passes when the masked value is empty or `None`. If `decrypt_secret` ever returns empty (e.g. key rotation broke decryption), the test would pass but the API would be returning empty masks. Stronger:
   ```python
   self.assertTrue(item["webhook_url_masked"], "Masked URL must be non-empty")
   self.assertIn("*", item["webhook_url_masked"])
   self.assertNotIn(SLACK_WEBHOOK, str(item))   # add this — already done in create test
   ```
   The `assertNotIn(SLACK_WEBHOOK, str(item))` directly mirrors the security guarantee being claimed. Currently the test only asserts the *field name* `"webhook_url_encrypted"` doesn't appear — that doesn't catch a leak under a different field name.

3. **List endpoint includes soft-deleted (`is_active=False`) integrations.** The view queryset is `ChatIntegration.objects.all_tenants().filter(tenant=tenant)` — with no `is_active=True` filter. After `test_delete_soft_deletes_integration` runs in production usage, the soft-deleted row would still appear in list responses. Whether this is intentional (admins should see deleted integrations to restore them) or a bug isn't clear from the code or the tests. **Recommendation:** add a behavior-pinning test — either `test_list_excludes_soft_deleted` (if filtering is intended) or `test_list_includes_soft_deleted_with_inactive_flag` (if exposure is intended). Without it, the contract is ambiguous.

4. **`test_create_routing_rule_returns_201` accepts both 200 and 201.** `assertIn(resp.status_code, [200, 201])`. The view explicitly returns `HTTP_201_CREATED` (views.py:236), so accepting 200 weakens the test. **Tighten to `assertEqual(resp.status_code, 201)`.**

5. **`test_create_with_ssrf_url_returns_400` accepts both 400 and 422.** Similar concern — the serializer raises `ValidationError`, which DRF maps to 400, not 422. Tightening to `assertEqual(resp.status_code, 400)` would be more rigorous.

6. **`TestChatRoutingRules` lacks DELETE coverage** (already noted as a gap). Low-cost to add since the cross-tenant pattern in `chat_routing_rule_detail` mirrors `_get_integration`.

7. **Cross-tenant deliveries gap** (already noted). The current `test_routing_rule_cross_tenant_integration_returns_404` proves the integration-scoped path works for rules — extending to `deliveries_url(other_integration.pk)` would close the symmetric gap with one extra test.

## Positive Observations

- **URL paths verified end-to-end against `urls.py` + `config/urls.py`**: `/api/v1/admin/chat-integrations/`, `<pk>/`, `<pk>/rules/`, `<pk>/deliveries/` all match the registered patterns. ✅
- **`force_authenticate` + per-tenant `HTTP_HOST`** correctly exercises real `TenantMiddleware` resolution (subdomain → `request.tenant`). The `auth_client(user, tenant)` helper is a clean pattern; consider promoting it to a shared test utility if more apps need it.
- **Cross-tenant isolation test pattern is correct and rigorous**: not just status-code 404, but also `refresh_from_db()` + assertion that mutation didn't land. This catches the class of bugs where the view returns 404 *after* the side-effect has already executed. ✅ (Lines 454-456, 466-470)
- **Soft-delete semantics pinned tightly**: `test_delete_soft_deletes_integration` checks both 204 status AND `refresh_from_db()` shows `is_active=False`. A hard-delete regression would cause `DoesNotExist` to be raised — a clear failure. ✅
- **SSRF allowlist test uses a realistic attacker pattern**: `https://hooks.slack.com.evil.example.com/ssrf` is the canonical "lookalike subdomain" SSRF — the kind of URL that fools sloppy substring checks. The test confirms the allowlist works with hostname-exact matching. ✅
- **Plaintext webhook never in response**: `test_created_integration_webhook_url_not_in_response` directly asserts the full SLACK_WEBHOOK URL is not in `str(resp.data)`. This is the right altitude for a security test — it catches leakage under any field name. ✅
- **404 not 403 enumeration leak invariant** explicitly called out in the test class docstring AND asserted everywhere. Clear intent.
- **TEACHER role tested at multiple endpoints**: list, create, delete, deliveries. Verifies `@admin_only` is consistently applied across the URL surface, not just the entry point.
- **Delivery test handles paginated/non-paginated defensively** — the `if isinstance(data, dict)` shape check is appropriate forward-protection if pagination is added later.
- **No mocking of business logic** — every test goes through real DRF middleware, real DB writes, real serializer validation. The only mock-equivalent is `force_authenticate`, which is the standard idiom.
- **Helper hygiene** — `_uid()` uniqueifies subdomains/emails so multiple `make_tenant()` calls within one test don't collide on `Tenant.unique` constraints.

## Verification Performed

| Check | Result |
|-------|--------|
| URL `/api/v1/admin/chat-integrations/` mounted | ✅ config/urls.py:87 + integrations_chat/urls.py |
| `chat_integration_list_create`, `_detail`, `chat_routing_rule_list_create`, `chat_delivery_list` exist | ✅ views.py:64, 103, 216, 283 |
| All views decorated `@admin_only` + `@tenant_required` | ✅ views.py:62-63, 101-102, 214-215, 241-242, 281-282 |
| `_get_integration(id, tenant)` returns None for cross-tenant → 404 path | ✅ views.py:48-52, 110-112 |
| DELETE soft-deletes via `is_active=False`, not `delete()` | ✅ views.py:124-126 |
| `webhook_url` is `write_only=True` | ✅ serializers.py:25-30 |
| `webhook_url_masked` derives via `decrypt_secret` + `mask_secret(plaintext, visible=4)` | ✅ serializers.py:61-65 |
| `validate_webhook_url` raises `SerializerValidationError` from `SSRFError` | ✅ serializers.py:67-74 |
| `_ALLOWED_HOSTS_EXACT = frozenset(["hooks.slack.com"])` rejects `hooks.slack.com.evil.example.com` | ✅ ssrf_guard.py:62, 66-74 |
| `ChatDelivery.STATUS_SENT` exists | ✅ models.py |
| `ChatIntegration.PROVIDER_SLACK / PROVIDER_TEAMS` exist | ✅ models.py |
| Test count 33 (memo says 30) | ⚠️ documentation drift, not code |

## Follow-up (non-blocking, advisory)

1. Tighten the four lenient assertions called out in Minor Issues #2, #4, #5.
2. Add a behavior pin for the soft-deleted-list ambiguity (Minor Issue #3).
3. Add the cross-tenant delivery test and routing-rule DELETE test (Known Gaps #1 and #2).
4. Update the QA request memo's test count (30 → 33), or update the request to match.

— reviewer
