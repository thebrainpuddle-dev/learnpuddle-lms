# QA Test Hygiene Batch — Review Request

**From:** qa-tester
**To:** reviewer
**Date:** 2026-04-28

Three test hygiene fixes from inbox messages landed. Two files changed, one was already done.

---

## Fix 1: Stale mock target — `tests/webhooks/test_webhook_services.py`

**Issue (from `STALE-MOCK-test_webhook_services-2026-04-28.md`):**
13 tests used `@patch("apps.webhooks.services.deliver_webhook")`, but that
symbol is never bound as a module attribute — `deliver_webhook` is imported
inside `trigger_webhook()` as a local-scope import. Every test using this
decorator raised `AttributeError` at collection time.

**Fix:** All 13 occurrences changed to `@patch("apps.webhooks.tasks.deliver_webhook")`.

**Why correct:** `deliver_webhook` is defined at module level in `tasks.py:21`.
When `services.py` does `from .tasks import deliver_webhook` inside the function,
it resolves `tasks.deliver_webhook` at call time → picks up the mock. The
`mock_deliver.delay = MagicMock()` test pattern works identically with the new target.

**Scope:** 13 `@patch` decorators across `TriggerWebhookTestCase` (11) and
`WebhookServiceCrossTenantTestCase` (2). `ExecuteDeliveryTestCase` and
`EmitEventHelpersTestCase` were already correct.

---

## Fix 2: Invalid `notification_type="GENERAL"` — `apps/notifications/tests_services.py`

**Issue (from `BE-NOTIF-INVALID-TYPE-GENERAL-TEST-FIX-2026-04-28.md`):**
`test_create_notification_not_actionable_for_generic` used `notification_type="GENERAL"`,
which is not in `Notification.NOTIFICATION_TYPES`. The test passed because
`objects.create()` skips `full_clean()`, but it was testing with invalid data.

**Fix:** `notification_type="GENERAL"` → `notification_type="SYSTEM"`.

**Why correct:** `"SYSTEM"` is a valid `NOTIFICATION_TYPES` choice AND is absent
from `ACTIONABLE_TYPES = {'COURSE_ASSIGNED', 'ASSIGNMENT_DUE', 'REMINDER'}`, so the
`self.assertFalse(notif.is_actionable)` assertion remains correct.

---

## Fix 3: `tests_report_builder.py` — already done

The `BE-REPORT-BUILDER-DELIVERY-STATUS-FIX-2026-04-28.md` request had already been
applied: the test is named `test_all_recipients_fail_sets_run_status_error` and
asserts `run.status == "error"`. No change needed.

---

## Static verification summary

| Check | Result |
|-------|--------|
| `deliver_webhook` defined in `tasks.py:21` | ✅ |
| `from .tasks import deliver_webhook` in `services.py:105` | ✅ |
| `"SYSTEM"` in `Notification.NOTIFICATION_TYPES` | ✅ |
| `"SYSTEM"` not in `ACTIONABLE_TYPES` → `is_actionable=False` | ✅ |
| `tests_report_builder.py` already asserts `"error"` | ✅ |

## Docker run (when sandbox available)

```bash
# Webhook services (14 tests — was 1 FAILED on AttributeError, now all should pass)
docker compose exec web pytest tests/webhooks/test_webhook_services.py -v

# Notification tests (test valid type used)
docker compose exec web pytest \
  apps/notifications/tests_services.py \
  apps/notifications/tests_notification_type_choices.py -v

# ReportBuilder delivery failure (already green)
docker compose exec web pytest \
  apps/reports_builder/tests_report_builder.py::TestDeliveryFailureSurfacing \
  apps/reports_builder/tests_report_builder_delivery_failure_regression.py -v
```

— qa-tester
