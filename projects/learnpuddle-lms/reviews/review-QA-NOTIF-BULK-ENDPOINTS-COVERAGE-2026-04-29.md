---
tags: [review, qa/notifications, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-29
---

# Review: QA-NOTIF-BULK-ENDPOINTS-COVERAGE (+15)

## Verdict: APPROVE

## Summary
Closes the zero-coverage gap on `notification_bulk_mark_read` and `notification_bulk_archive`. Fifteen new tests across two `TestCase` classes cover happy path, validation, auth, idempotency, and same-tenant cross-teacher isolation. Endpoints, URLs, and response shapes match the source.

## Verification

### Source contracts confirmed
- `apps/notifications/views.py:118-135` — `notification_bulk_mark_read`
  - 400 on empty/missing `ids` ✅
  - Filters by `teacher=request.user, tenant=request.tenant, is_read=False` ✅
  - Returns `{'marked_read': updated}` ✅
- `apps/notifications/views.py:195-215` — `notification_bulk_archive`
  - 400 on empty/missing `ids` ✅
  - Uses `all_objects` with explicit `tenant=request.tenant` filter (so soft-deleted rows are still scoped) ✅
  - `is_archived=False` filter → idempotency ✅
  - Returns `{'archived': updated}` ✅

### Test inventory matches request
| Class | Tests | Confirmed |
|-------|-------|-----------|
| `NotificationBulkMarkReadTestCase` | 7 | ✅ (lines 543-638) |
| `NotificationBulkArchiveTestCase` | 8 | ✅ (lines 650-763) |
| **Total new** | **15** | ✅ (33 → 48 in file) |

## Critical Issues
None.

## Major Issues
None.

## Minor Issues (non-blocking)
- **Misnamed isolation tests.** `test_bulk_mark_read_does_not_affect_other_teachers_notifications` (line 622) and the matching archive test (line 748) create `other_teacher` in the **same** tenant — so they verify *cross-teacher* isolation, not *cross-tenant* isolation. The docstring on the mark-read variant calls it "Cross-tenant safety" (line 624), which is misleading. Either:
  - Rename docstring to "Cross-teacher isolation" (most honest), or
  - Add a true cross-tenant test that creates a separate `Tenant` + teacher and confirms IDs from the foreign tenant are silently ignored. Tenant isolation is the higher-impact security boundary in this LMS, so a true cross-tenant probe would be valuable. Not blocking — the view's `tenant=request.tenant` filter is already pinned by the existing test suite for sibling endpoints.
- **`marked_read=0` happy-path not exercised.** When all submitted IDs belong to already-read notifications, the response should be `{'marked_read': 0, 'status': 200}`. There's an analogous test for the archive endpoint (`test_bulk_archive_is_idempotent`) but no symmetric one for mark-read. Recommend adding `test_bulk_mark_read_is_idempotent` for parity. Optional.

## Positive Observations
- Tests are crisp and contract-focused: status code, mutated-vs-unmutated row state, response payload count, and 401-vs-400 boundaries are all separately asserted.
- Idempotency test (`test_bulk_archive_is_idempotent`, line 729) directly exercises the `is_archived=False` filter that prevents double-archiving — exactly the behavioral spec a future refactor needs to preserve.
- `test_..._returns_count_of_marked` and `..._returns_count_of_archived` pin the `{'marked_read': N}` / `{'archived': N}` response shape — important because the frontend relies on these counters for toast messages.
- Helpers (`_make_tenant`, `_make_user`, `_make_notification`, `_client_for`, `_anon_client`) match the pre-existing pattern in this file — no DRY violation.
- Each TestCase has its own `@override_settings` block with `ALLOWED_HOSTS=["*"]` — correct for multi-tenant subdomain testing.
