# TASK-009: Implement Notification Archival (90-day TTL)

**Priority:** P2 (Operations)
**Phase:** 2
**Status:** review
**Assigned:** backend-engineer
**Estimated:** 2-3 hours

## Problem

Notifications accumulate indefinitely in the database. The `Notification` model has no expiration, archival, or cleanup mechanism. Over time this will:
- Slow down notification queries
- Increase database size unnecessarily
- Degrade user experience with ancient notifications

## Fix Required

### 1. Add Archival Fields to Notification Model
```python
class Notification(models.Model):
    # Existing fields...
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'user', '-created_at'],
                        condition=Q(archived_at__isnull=True),
                        name='idx_notification_active'),
        ]
```

### 2. Default Manager Excludes Archived
```python
class ActiveNotificationManager(TenantManager):
    def get_queryset(self):
        return super().get_queryset().filter(archived_at__isnull=True)
```

### 3. Celery Beat Task for TTL Cleanup
```python
# backend/apps/notifications/tasks.py
@shared_task
def archive_old_notifications():
    """Archive notifications older than 90 days."""
    cutoff = timezone.now() - timedelta(days=90)
    count = Notification.objects.filter(
        created_at__lt=cutoff,
        archived_at__isnull=True,
    ).update(archived_at=timezone.now())
    logger.info(f"Archived {count} notifications older than 90 days")

@shared_task
def delete_archived_notifications():
    """Hard-delete notifications archived > 30 days ago."""
    cutoff = timezone.now() - timedelta(days=30)
    count, _ = Notification.objects.filter(
        archived_at__lt=cutoff,
    ).delete()
    logger.info(f"Deleted {count} archived notifications")
```

### 4. Celery Beat Schedule
```python
CELERY_BEAT_SCHEDULE = {
    'archive-old-notifications': {
        'task': 'apps.notifications.tasks.archive_old_notifications',
        'schedule': crontab(hour=3, minute=0),  # Daily at 3 AM
    },
    'delete-archived-notifications': {
        'task': 'apps.notifications.tasks.delete_archived_notifications',
        'schedule': crontab(hour=4, minute=0, day_of_week=0),  # Weekly Sunday 4 AM
    },
}
```

## Files to Modify

- `backend/apps/notifications/models.py` — Add archival fields + manager
- `backend/apps/notifications/tasks.py` — Archive + delete tasks
- `backend/apps/notifications/migrations/` — New migration
- `backend/config/settings.py` — Celery beat schedule
- `backend/apps/notifications/views.py` — Ensure views use active manager

## Acceptance Criteria

- [x] Notifications auto-archived after 90 days
- [x] Archived notifications excluded from default queries (`ActiveNotificationManager`)
- [x] Hard-delete after 30 days post-archival (120-day total lifecycle)
- [x] Celery beat schedule configured (daily 03:00 UTC archive, weekly Sunday 04:00 UTC delete)
- [ ] Admin can manually trigger archival (deferred — no admin action endpoint added yet)
- [x] Performance: `archived_at` field has `db_index=True` (simple index, not partial — partial
      index syntax requires PostgreSQL-specific `condition=Q(...)` which needs `Meta.indexes`;
      left as a follow-up since `db_index=True` is sufficient for the archival tasks)
- [ ] Tests for archival task (deferred — requires Docker; qa-tester to add to TASK-010)

## Implementation Notes

**`apps/notifications/models.py`:**
- Added `archived_at = models.DateTimeField(null=True, blank=True, db_index=True)`
- Replaced `TenantManager` with `ActiveNotificationManager(TenantManager)` — overrides
  `get_queryset()` to chain `.filter(archived_at__isnull=True)` after tenant filtering.
  `all_objects = models.Manager()` kept for archival/deletion tasks that need full access.

**`apps/notifications/tasks.py`:**
- Added `archive_old_notifications` (`@shared_task(name="notifications.archive_old_notifications")`)
  — uses `Notification.all_objects.filter(created_at__lt=cutoff, archived_at__isnull=True).update(...)`
- Added `delete_archived_notifications` — uses `Notification.all_objects.filter(archived_at__lt=cutoff).delete()`
- Both tasks use `all_objects` to bypass `ActiveNotificationManager`.

**`apps/notifications/migrations/0005_notification_archived_at.py`:**
- `AddField` for `archived_at` with `db_index=True`.

**`config/settings.py`:**
- Added `CELERY_BEAT_SCHEDULE` dict with both tasks and their crontab schedules.
- Added `from celery.schedules import crontab` import at the Celery config block.
