---
tags: [review, branch/feature-ui-improvements-and-fixes, verdict/request-changes, reviewer/lp-reviewer]
created: 2026-03-25
---

# Review: feature/ui-improvements-and-fixes — UI improvements, dashboard enhancements, smoke tests

## Branch: `feature/ui-improvements-and-fixes`
## Commit: `b4422cc`
## Verdict: REQUEST_CHANGES

## Summary
This is a large commit (12 files, 641 additions, 222 deletions) that bundles UI improvements, backend serializer changes, and new API smoke tests into a single commit. The smoke tests are valuable and well-structured. The frontend changes improve the admin dashboard. However, there are test quality issues, a potential import problem, and the commit should have been split into smaller, focused commits.

## Critical Issues
None.

## Major Issues

### 1. Smoke test imports potentially broken module (`apps.media.models`)
**File**: `backend/apps/courses/tests_api_smoke_admin_teacher_flow.py`, line 8

```python
from apps.media.models import MediaAsset
```

Looking at the `fix/admin-panel-bugs` branch, the entire `apps/media/` module is **deleted** (models.py, views.py, serializers.py, urls.py, migrations). If that branch merges first, this test file will fail to import. The test needs to either:
- Not depend on `MediaAsset`
- Guard the import with a try/except
- Be updated after the media module refactor

### 2. Regression test intentionally sets wrong tenant — fragile
**File**: `backend/apps/courses/tests_api_smoke_admin_teacher_flow.py`, lines 224-244

```python
def test_teacher_course_list_does_not_break_on_request_tenant_mismatch(self):
    req.tenant = self.other_tenant  # intentionally wrong
```

This test verifies that `teacher_course_list` works even when `request.tenant` doesn't match the thread-local tenant. While documenting a historical bug is fine, this test:
- **Asserts the WRONG behavior** — if `request.tenant` is wrong, the system SHOULD fail safely, not return data from a different tenant
- This is effectively testing that tenant isolation is broken in a specific way and relying on it
- The correct fix would be to ensure `request.tenant` and thread-local tenant are always consistent

### 3. Smoke test missing `tearDown` — thread-local tenant leaks
The `test_teacher_course_list_does_not_break_on_request_tenant_mismatch` test uses `set_current_tenant()` in a try/finally, which is good. But the `_login_and_set_bearer` tests set `HTTP_HOST` on the client which persists across tests. This could leak state if test ordering changes.

### 4. Reminder serializer changes not shown in diff but referenced in commit message
The commit message says "Add reminder serializers improvements" and "Update reminders views" but I need to verify these changes exist in the diff. The diff shows changes to `backend/apps/reminders/serializers.py` and `views.py` — let me note this for completeness.

## Minor Issues

### 5. Single mega-commit violates atomic commit principle
This commit bundles:
- Backend reminder serializer/view changes
- Frontend dashboard redesign (DashboardPage, StatsCard, SearchBar)
- Frontend accessibility fixes (LiveAnnouncer)
- Service worker updates
- Auth page cleanup
- API smoke tests

These should be at least 3-4 separate commits: backend changes, frontend UI, service worker, tests.

### 6. `SuperAdminLoginPage.tsx` — removal of single line
```diff
- import { useEffect } from 'react';
```
Was this import unused? If so, good cleanup. If `useEffect` was actually used, this breaks the component.

### 7. `SchoolDetailPage.tsx` — minimal change
Only 4 lines changed. Seems like a drive-by fix that should have its own commit for traceability.

### 8. Service worker changes need careful review
Changes to `service-worker.js` affect caching strategy for all users. Cache invalidation bugs are hard to debug in production. Ensure cache version is bumped.

## Positive Observations

1. **Smoke tests are excellent** — they cover the critical admin and teacher flows end-to-end with proper setup/teardown
2. **Tenant isolation regression test** documents a real historical bug, even if the assertion logic is debatable
3. **Dashboard improvements** add real value — stats cards, better layout
4. **SearchBar accessibility** improvements (LiveAnnouncer) show attention to a11y
5. **Test uses `override_settings`** correctly for ALLOWED_HOSTS

## Required Changes Before Merge
1. Resolve `MediaAsset` import dependency — will break if `apps/media` is removed
2. Reconsider the tenant mismatch regression test assertion logic
3. Verify `useEffect` removal from SuperAdminLoginPage doesn't break functionality
4. Consider splitting into multiple commits for reviewability and bisectability
