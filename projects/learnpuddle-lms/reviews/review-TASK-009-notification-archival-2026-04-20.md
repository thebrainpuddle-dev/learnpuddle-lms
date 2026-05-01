---
tags: [review, task/TASK-009, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: TASK-009 — Notification Archival (90-day TTL)

## Verdict: APPROVE

## Summary

Solid, well-scoped archival implementation. Two additive migrations, a
correctly-chained `ActiveNotificationManager`, two Celery beat tasks with
sane cutoffs, and — a pleasant surprise over what the review request
promised — a **491-line test file** (`tests_archival.py`) covering manager
behaviour, boundary dates, multi-tenant isolation, and the full
create→archive→delete lifecycle. Tenant isolation is preserved throughout.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

### m1 — `all_objects` used in user-facing archive views — intentional but undocumented

**Files**:
- `backend/apps/notifications/views.py:165-169` (`notification_archive`)
- `backend/apps/notifications/views.py:197-202` (`notification_bulk_archive`)
- `backend/apps/notifications/views.py:349-355` (`announcement_delete`)

These user-facing endpoints query `Notification.all_objects` instead of the
default (tenant-scoped) `Notification.objects`. The usage is **correct** in
each case:

- `notification_archive` needs to return 200 with serialized data when the
  notification is already archived (line 173-174) — the active manager
  would hide it and raise 404.
- `announcement_delete` cascades over archived and active rows with the
  same title/message/created_at — needs the full set.
- `notification_bulk_archive` filters `is_archived=False` explicitly, so
  it's equivalent to either manager.

**Tenant isolation is preserved** because every call filters
`tenant=request.tenant` and `teacher=request.user` manually — I verified
this line-by-line. No cross-tenant leakage is possible.

**Action**: add a 1-line comment above each `all_objects` usage explaining
**why** (e.g. `# all_objects: we need to see already-archived rows so
re-archival is idempotent`). This prevents the next developer from
"fixing" it to `.objects` and breaking the idempotent-archive contract.
Non-blocking.

### m2 — No unarchive / restore path

**Status**: explicitly deferred by author.

The only way to undo a premature archival right now is a raw SQL `UPDATE`
or Django shell. For a user-facing feature this is fine (no one expects
the "Archived" bin to be recoverable at the API level), but consider
adding a management command `unarchive_notification --id <uuid>` for
support ops. Low priority.

### m3 — Two migrations instead of one

**Files**:
- `backend/apps/notifications/migrations/0005_notification_archived_at.py` (adds `archived_at`)
- `backend/apps/notifications/migrations/0006_notification_is_archived.py` (adds `is_archived`)

The review request described a single migration `0005` adding both
fields. The diff actually landed two separate migrations — presumably
because `is_archived` was added after `archived_at`. Not a problem
(Django handles multiple additive migrations fine), but the task
description is out of sync. Update the task doc to reflect reality.

### m4 — Dual-path archived flag is mildly redundant

`is_archived` and `archived_at` always move together (task sets both;
queries use `is_archived=False, archived_at__isnull=True`). This is
defensible (bool is cheaper to index/filter than a datetime) but if you
ever backfill `archived_at` without flipping `is_archived` — or
vice-versa — queries will disagree. Pick one as canonical in your
mental model and treat the other as a denormalisation. The tests already
cover both together, so current behaviour is safe.

## Positive Observations

- **`ActiveNotificationManager` correctly chains tenant + active filters** — inherits from `TenantManager`, calls `super().get_queryset()`, then layers `.filter(is_archived=False, archived_at__isnull=True)` (models.py:21). Good use of inheritance.
- **`all_objects = models.Manager()` escape hatch** — the right way to give Celery tasks cross-tenant access without polluting the default manager.
- **Bulk operations** in tasks.py — archival uses `.update()` and deletion uses `.delete()` on querysets. No per-row loops, no N+1. Will scale to millions of rows.
- **Idempotent archival**: `archive_old_notifications` filters `archived_at__isnull=True` (tasks.py:350) so re-runs don't re-stamp `archived_at`. Subtle but important for correctness.
- **Boundary-case tests** in `tests_archival.py` — notifications exactly 90 days old, multi-tenant cohorts, re-stamp prevention, 30-day grace window all covered.
- **Celery beat schedule** correctly staggered — archive runs daily at 03:00 UTC, delete weekly Sunday at 04:00 UTC. Good separation so the slow archival sweep doesn't collide with the hard-delete scan.
- **Pure additive migrations** — `null=True` / `default=False` allow a no-downtime deploy against a production table with millions of rows.
- **`db_index=True` on both fields** — the cron task filters on `archived_at <= cutoff`, which hits the index.

## Verification Notes

- Latest migration chain: `0001 → 0007_rename_notif_tenant_teacher_created_idx`. New migrations slot cleanly at `0005` and `0006`. No conflicts.
- `ActiveNotificationManager` correctly delegates to `TenantManager.get_queryset()` via `super()` — tenant isolation is preserved by default.
- Tests exist and are comprehensive (author said "deferred to qa-tester" but in fact shipped them — even better).

## Ready to Merge

Yes. Address m1 (inline comments) as a trivial follow-up.
