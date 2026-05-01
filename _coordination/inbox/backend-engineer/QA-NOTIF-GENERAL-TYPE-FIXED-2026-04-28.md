# QA Ack: Invalid notification_type "GENERAL" — FIXED

**From:** qa-tester
**To:** backend-engineer
**Date:** 2026-04-28
**Re:** `BE-NOTIF-INVALID-TYPE-GENERAL-TEST-FIX-2026-04-28.md`

## Status: FIXED

Changed `notification_type="GENERAL"` → `notification_type="SYSTEM"` in
`test_create_notification_not_actionable_for_generic` at
`backend/apps/notifications/tests_services.py:134`.

**Why SYSTEM:**
- Valid entry in `Notification.NOTIFICATION_TYPES` ✅
- Not in `ACTIONABLE_TYPES` → `is_actionable=False` (test assertion unchanged) ✅
- Semantically appropriate: a generic/system-level non-actionable notification ✅

**Also verified:**
- `tests_report_builder.py` fix was already applied — `run.status == "error"` assertion
  and `test_all_recipients_fail_sets_run_status_error` method name confirmed in place.
  No second change needed.

Docker run to confirm:
```bash
docker compose exec web pytest \
  apps/notifications/tests_services.py \
  apps/notifications/tests_notification_type_choices.py -v
```

— qa-tester
