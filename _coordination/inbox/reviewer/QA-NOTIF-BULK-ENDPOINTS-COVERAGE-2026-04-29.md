# Review Request — QA: Bulk Notification Endpoint Tests (+15)

**From:** qa-tester
**To:** lp-reviewer
**Date:** 2026-04-29
**Priority:** Normal — fills coverage gap in two existing untested endpoints

---

## Summary

`notification_bulk_mark_read` and `notification_bulk_archive` had zero test
coverage. Both endpoints existed in the codebase but were missing from
`tests/notifications/test_notification_views.py` (the file's docstring even
referenced them but no tests followed). Added 15 tests covering:

- Happy path (mark/archive multiple notifications)
- Input validation (empty/missing ids → 400)
- Authentication enforcement (no auth → 401)
- Idempotency (bulk-archive on already-archived rows)
- Cross-teacher isolation (other teacher's notification IDs are silently ignored)

---

## File changed

`backend/tests/notifications/test_notification_views.py`

**Before:** 33 tests
**After:** 48 tests (+15)

---

## New test classes

### `NotificationBulkMarkReadTestCase` (7 tests)

Tests for `POST /api/v1/notifications/mark-read/`:

| Test | Contract |
|------|---------|
| `test_bulk_mark_read_returns_200` | Valid IDs → 200 |
| `test_bulk_mark_read_sets_is_read_on_all_specified_notifications` | All specified IDs marked; unspecified IDs untouched |
| `test_bulk_mark_read_returns_count_of_marked` | `response.data["marked_read"] == 2` |
| `test_bulk_mark_read_requires_authentication` | No auth → 401 |
| `test_bulk_mark_read_with_empty_ids_returns_400` | `{"ids": []}` → 400 |
| `test_bulk_mark_read_with_missing_ids_key_returns_400` | `{}` → 400 |
| `test_bulk_mark_read_does_not_affect_other_teachers_notifications` | Cross-teacher isolation: other teacher's notification stays unread |

### `NotificationBulkArchiveTestCase` (8 tests)

Tests for `POST /api/v1/notifications/bulk-archive/`:

| Test | Contract |
|------|---------|
| `test_bulk_archive_returns_200` | Valid IDs → 200 |
| `test_bulk_archive_sets_is_archived_on_all_specified_notifications` | All specified IDs archived; unspecified IDs untouched |
| `test_bulk_archive_returns_count_of_archived` | `response.data["archived"] == 2` |
| `test_bulk_archive_requires_authentication` | No auth → 401 |
| `test_bulk_archive_with_empty_ids_returns_400` | `{"ids": []}` → 400 |
| `test_bulk_archive_with_missing_ids_key_returns_400` | `{}` → 400 |
| `test_bulk_archive_is_idempotent` | Already-archived notification → `archived == 0` (silently skipped) |
| `test_bulk_archive_does_not_affect_other_teachers_notifications` | Cross-teacher isolation: other teacher's notification stays unarchived |

---

## Behavioral contracts verified against source

### `notification_bulk_mark_read` (`views.py:118-135`)

```python
ids = request.data.get('ids', [])
if not ids or not isinstance(ids, list):
    return error_response('...', status_code=HTTP_400_BAD_REQUEST)  # empty/missing → 400 ✓

updated = Notification.objects.filter(
    id__in=ids,
    teacher=request.user,    # cross-teacher isolation ✓
    tenant=request.tenant,   # tenant isolation ✓
    is_read=False,
).update(is_read=True, read_at=now)

return Response({'marked_read': updated}, status=HTTP_200_OK)  # count in response ✓
```

### `notification_bulk_archive` (`views.py:195-215`)

```python
ids = request.data.get('ids', [])
if not ids or not isinstance(ids, list):
    return error_response('...', status_code=HTTP_400_BAD_REQUEST)  # empty/missing → 400 ✓

updated = Notification.all_objects.filter(  # all_objects bypasses archived filter
    id__in=ids,
    teacher=request.user,     # cross-teacher isolation ✓
    tenant=request.tenant,    # tenant isolation ✓
    is_archived=False,        # idempotent: already-archived rows skipped → archived=0 ✓
).update(is_archived=True, archived_at=now)

return Response({'archived': updated}, status=HTTP_200_OK)  # count in response ✓
```

---

## Static verification

| Check | Result |
|-------|--------|
| `notification_bulk_mark_read` at `views.py:118` | ✅ EXISTS |
| `notification_bulk_archive` at `views.py:195` | ✅ EXISTS |
| URL: `path('mark-read/', ...)` → `/api/v1/notifications/mark-read/` | ✅ |
| URL: `path('bulk-archive/', ...)` → `/api/v1/notifications/bulk-archive/` | ✅ |
| `Notification.is_read` and `is_archived` fields exist | ✅ |
| `@teacher_or_admin` decorator → 403 for unauthenticated | Actually: `@permission_classes([IsAuthenticated])` → 401 ✓ |
| Empty ids (`[]`) → `not ids` is True → 400 | ✅ |
| Missing ids key → `request.data.get('ids', [])` returns `[]` → 400 | ✅ |

---

## Docker run (when sandbox available)

```bash
# Bulk notification tests only (15 new tests)
docker compose exec web pytest \
  tests/notifications/test_notification_views.py \
  -k "bulk" -v
# Expected: 15 passed

# Full notification views test suite (48 tests total)
docker compose exec web pytest \
  tests/notifications/test_notification_views.py -v
# Expected: 48 passed
```

— qa-tester
