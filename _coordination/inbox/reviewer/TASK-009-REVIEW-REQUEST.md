# Review Request — TASK-009: Notification Archival (90-day TTL)

**Author:** backend-engineer
**Date:** 2026-04-20
**Priority:** P2 (Operations)
**Status:** ready-for-review

## Summary

Implemented automatic archival and hard-deletion of old notifications to
prevent unbounded table growth.

## Lifecycle

```
Created → Active (default queries) → Archived after 90 days → Hard-deleted after 30 more days
```

Total: 120-day retention, then hard-delete.

## Changes

### 1. `apps/notifications/models.py`

- Added `archived_at = models.DateTimeField(null=True, blank=True, db_index=True)`
- Added `is_archived = models.BooleanField(default=False, db_index=True)` (dual-path flag)
- Replaced `TenantManager` with `ActiveNotificationManager` which chains
  `.filter(archived_at__isnull=True)` after tenant filtering
- Added `all_objects = models.Manager()` escape-hatch for archival tasks

### 2. `apps/notifications/tasks.py`

- `archive_old_notifications` — bulk-`update()` notifications older than 90 days
  (uses `all_objects` to bypass active manager)
- `delete_archived_notifications` — hard-`delete()` notifications archived
  more than 30 days ago (uses `all_objects`)

### 3. `apps/notifications/migrations/0005_notification_archived_at.py`

Additive-only migration: `AddField` for `archived_at` with `db_index=True`.

### 4. `config/settings.py`

Added two entries to `CELERY_BEAT_SCHEDULE`:
- `archive-old-notifications` — daily at 03:00 UTC
- `delete-archived-notifications` — weekly Sunday at 04:00 UTC

## Files Changed

| File | Change |
|------|--------|
| `backend/apps/notifications/models.py` | Added archival fields + `ActiveNotificationManager` |
| `backend/apps/notifications/tasks.py` | Added archive + delete tasks |
| `backend/apps/notifications/migrations/0005_notification_archived_at.py` | NEW additive migration |
| `backend/config/settings.py` | Beat schedule entries |

## Acceptance Criteria

- [x] Notifications auto-archived after 90 days (`archive_old_notifications` task)
- [x] Archived notifications excluded from default queries (`ActiveNotificationManager`)
- [x] Hard-delete after 30 days post-archival (`delete_archived_notifications` task)
- [x] Celery beat schedule configured (daily 03:00 UTC archive, weekly Sunday 04:00 UTC delete)
- [x] `archived_at` indexed (`db_index=True`)
- [ ] Admin manual trigger endpoint — deferred; no blocker
- [ ] Automated tests — deferred to qa-tester (Docker required)

## Notes

Migration is additive-only (new nullable field). All existing queries use the
new `ActiveNotificationManager` which excludes archived records by default.
The `all_objects` manager is used in archival tasks that need full access.
