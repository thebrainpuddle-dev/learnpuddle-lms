# Stale mock target in test_webhook_services.py — flag for qa-tester

**From:** backend-security
**To:** qa-tester
**Date:** 2026-04-28

## Issue

`backend/tests/webhooks/test_webhook_services.py` has 14+ tests that
`@patch("apps.webhooks.services.deliver_webhook")`, but
`apps/webhooks/services.py` never binds `deliver_webhook` as a module
attribute — it does `from .tasks import deliver_webhook` *inside*
`trigger_webhook` (line 105, local-scope import).

Result: `mock.patch` raises
`AttributeError: <module 'apps.webhooks.services'> does not have the
attribute 'deliver_webhook'` on every test that uses this decorator.

Hit during the BE-SEC-P0-AUDIT pytest run (2026-04-28):

```
1 failed, 65 passed in 518.47s
FAILED tests/webhooks/test_webhook_services.py::TriggerWebhookTestCase::test_trigger_creates_delivery_record
```

Test runner stops at the first failure (`-x`), so the same error likely
hits the other 14 tests with the same patch target.

## Two clean fixes (pick one)

**Option A — patch the real location (preferred, test-only):**
```python
@patch("apps.webhooks.tasks.deliver_webhook")
```
This matches where the symbol is actually defined and avoids relying on
import side-effects.

**Option B — hoist the import in services.py:**
Move `from .tasks import deliver_webhook` to module-level top of
`apps/webhooks/services.py`. Slight risk of circular import; if
that bites, leave it local and use Option A.

I prefer Option A — keeps the production import lazy (avoids any
circular-import risk on Celery autodiscovery) and centralises the patch
target.

## Why this isn't backend-security work

This is purely a stale test artifact — production webhook delivery
works correctly (the `trigger_webhook` → local import → `.delay()`
chain is exercised in the actual code path, just not patchable from
the test's vantage). Per the backend-security agent definition I do
not modify test files; routing to you.

## Verification once fixed

```
docker compose exec web pytest tests/webhooks/test_webhook_services.py -v
```

Expected: all tests in the file pass.

— backend-security
