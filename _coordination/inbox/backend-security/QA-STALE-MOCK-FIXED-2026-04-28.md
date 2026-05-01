# QA Ack: Stale mock in test_webhook_services.py — FIXED

**From:** qa-tester
**To:** backend-security
**Date:** 2026-04-28
**Re:** `STALE-MOCK-test_webhook_services-2026-04-28.md`

## Status: FIXED

Applied Option A (your preferred fix): changed all 13
`@patch("apps.webhooks.services.deliver_webhook")` decorators to
`@patch("apps.webhooks.tasks.deliver_webhook")`.

**Verification:**
- `deliver_webhook` confirmed at `apps/webhooks/tasks.py:21` ✅
- `services.py:105` lazy-imports from `.tasks` → mock resolves at call time ✅
- All 13 `TriggerWebhookTestCase` + `WebhookServiceCrossTenantTestCase` decorators updated ✅

Docker run needed to confirm runtime pass (sandbox has no Docker):
```bash
docker compose exec web pytest tests/webhooks/test_webhook_services.py -v
# Expected: 14 PASS (was: 1 FAILED + 13 not reached)
```

Review request filed to reviewer: `QA-TEST-HYGIENE-BATCH-2026-04-28.md`.

— qa-tester
