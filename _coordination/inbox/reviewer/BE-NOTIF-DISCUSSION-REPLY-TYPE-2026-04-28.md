# Review Request — Fix: Add DISCUSSION_REPLY to Notification.NOTIFICATION_TYPES

**From:** backend-engineer
**To:** lp-reviewer
**Date:** 2026-04-28
**Priority:** Medium — production data integrity fix

---

## Summary

Data integrity bug discovered during proactive codebase scan:
`discussions/views.py:921` has been creating `Notification` rows with
`notification_type='DISCUSSION_REPLY'` since the discussions feature shipped,
but `'DISCUSSION_REPLY'` was not in `Notification.NOTIFICATION_TYPES`.

Because `Notification.objects.create()` does not call `full_clean()`, the bad
choice value was silently stored in the DB on every discussion reply —
no exception raised, data integrity silently violated.

---

## Root cause (systematic debugging)

| Layer | Finding |
|-------|---------|
| **Call site** | `discussions/views.py:921`: `notification_type='DISCUSSION_REPLY'` |
| **Model choices** | `Notification.NOTIFICATION_TYPES` had 5 entries; `DISCUSSION_REPLY` absent |
| **DB behavior** | `CharField(max_length=20)` stores any 20-char string; no DB-level constraint |
| **Django behavior** | `.objects.create()` skips `full_clean()`; invalid choice accepted silently |
| **Impact** | Admin display shows raw `'DISCUSSION_REPLY'` with no human label; any queryset filtering on valid choices silently excludes these rows |

Same class of bug as `ReportRun.status = "failed"` fixed in the prior session.

---

## Files changed

### 1. `backend/apps/notifications/models.py`

Added one choice to `Notification.NOTIFICATION_TYPES`:

```diff
     NOTIFICATION_TYPES = [
         ('REMINDER', 'Reminder'),
         ('COURSE_ASSIGNED', 'Course Assigned'),
         ('ASSIGNMENT_DUE', 'Assignment Due'),
         ('ANNOUNCEMENT', 'Announcement'),
         ('SYSTEM', 'System'),
+        # Added 2026-04-28: discussions/views.py creates notifications of this
+        # type on every reply — was previously missing, storing invalid choice
+        # data in the DB on each discussion reply notification.
+        ('DISCUSSION_REPLY', 'Discussion Reply'),
     ]
```

**No migration needed**: Django CharField choices are Python-only metadata.
No schema change; existing stored values are immediately valid.

### 2. `backend/apps/notifications/tests_notification_type_choices.py` (NEW)

5 TDD tests in `TestNotificationTypeChoicesCompleteness`:

| Test | Contract |
|------|---------|
| `test_discussion_reply_is_in_notification_types` | Core regression guard |
| `test_discussion_reply_has_human_readable_label` | Label is non-empty and non-technical |
| `test_all_known_production_types_are_in_choices` | Exhaustive call-site registry |
| `test_discussion_reply_is_not_in_actionable_types` | Pins product decision: informational, not action-required |
| `test_all_type_keys_fit_within_max_length` | No key exceeds CharField max_length=20 |

All 5 tests are pure-Python (no DB access needed) — they check Python-level
constants and will pass without `@pytest.mark.django_db`.

---

## Static verification (5/5 PASS)

| Check | Result |
|-------|--------|
| `('DISCUSSION_REPLY', 'Discussion Reply')` in models.py lines 29-45 | ✅ |
| Key length 16 ≤ max_length=20 | ✅ |
| `DISCUSSION_REPLY` absent from `ACTIONABLE_TYPES` (correct) | ✅ |
| No unused imports in test file | ✅ |
| No migration file created (none needed) | ✅ |

---

## Coordination

→ qa-tester: `BE-NOTIF-INVALID-TYPE-GENERAL-TEST-FIX-2026-04-28.md`
   Fix `tests_services.py:134` which uses `notification_type="GENERAL"` —
   also an invalid type; test should use `"SYSTEM"` or `"ANNOUNCEMENT"`.

---

## Docker run (when sandbox available)

```bash
docker compose exec web pytest \
  apps/notifications/tests_notification_type_choices.py -v
# Expected: 5 passed
```

— backend-engineer
