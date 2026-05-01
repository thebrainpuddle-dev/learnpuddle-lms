# QA Action Required — Invalid notification_type "GENERAL" in tests_services.py

**From:** backend-engineer
**To:** qa-tester
**Date:** 2026-04-28
**Priority:** Medium — test uses an invalid choice value, producing misleading coverage

---

## Context

While fixing a production data integrity bug today (adding `'DISCUSSION_REPLY'` to
`Notification.NOTIFICATION_TYPES`), I found that `tests_services.py:134` also uses
an invalid notification type:

```python
# tests_services.py line ~134
notification_type="GENERAL"
```

`"GENERAL"` is NOT in `Notification.NOTIFICATION_TYPES`. Valid choices are:
`REMINDER`, `COURSE_ASSIGNED`, `ASSIGNMENT_DUE`, `ANNOUNCEMENT`, `SYSTEM`, `DISCUSSION_REPLY` (as of today's fix).

Django does not validate choices on `.objects.create()` so this test passes,
but it is testing with invalid data — the test should use a valid type.

---

## Fix needed (test file only — backend-engineer rule forbids test edits)

In `backend/apps/notifications/tests_services.py` at line ~134:

```python
# BEFORE (invalid type)
notification_type="GENERAL"

# AFTER (pick a valid type that matches the test's intent)
notification_type="SYSTEM"   # or "ANNOUNCEMENT", whichever fits the test scenario
```

Review the test at line 134 to confirm which valid type best matches the intent.

---

## Verification

After the fix, run:

```bash
docker compose exec web pytest apps/notifications/tests_services.py -v
docker compose exec web pytest apps/notifications/tests_notification_type_choices.py -v
```

Both suites should be green.

---

## Why this matters

The new regression test file `tests_notification_type_choices.py` (today's addition)
pins `known_production_types` — a set of all valid types used by production code.
`"GENERAL"` was never a valid type and is not in `known_production_types`, so the
production fix doesn't affect this; it's purely a test-hygiene issue.

— backend-engineer
