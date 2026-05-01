# Review Request — FE-034 Backend Analytics Views

**From:** backend-engineer
**To:** reviewer
**Date:** 2026-04-25
**Priority:** Medium — FE-034 frontend is shipped; charts show error state until backend is verified live

---

## Summary

The three analytics chart backend endpoints required by FE-034 are implemented and ready for review.
All 35 TDD tests in `backend/tests/reports/test_analytics_views.py` (approved by reviewer 2026-04-24)
should pass.

---

## Files changed

| File | Action |
|------|--------|
| `backend/apps/reports/analytics_views.py` | **Created** — 3 view functions |
| `backend/apps/reports/urls.py` | **Modified** — 3 URL patterns added at top |

---

## Endpoint details

### 1. `GET /api/v1/reports/analytics/deadline-adherence/`

- **Auth**: `@admin_only @tenant_required`
- **Query params**: `start`, `end` (ISO date, optional)
- **Data source**: `TeacherProgress.all_objects.filter(tenant=request.tenant, content__isnull=True, status="COMPLETED", course__deadline__isnull=False)`
- **Logic**: Groups by calendar month of `completed_at`; on_time = `completed_at.date() <= course.deadline`
- **Response**: `[{period, adherencePercent, totalTeachers, onTime, late}]`

### 2. `GET /api/v1/reports/analytics/approval-trends/`

- **Auth**: `@admin_only @tenant_required`
- **Query params**: `start`, `end` (ISO date, optional)
- **Data source**: `AssignmentSubmission.all_objects.filter(tenant=request.tenant)` with `select_related("assignment")`
- **Mapping**: GRADED + score ≥ passing_score → approved; GRADED + score < passing_score → rejected; PENDING/SUBMITTED → pending
- **Response**: `[{period, approved, rejected, pending}]`

### 3. `GET /api/v1/reports/analytics/course-effectiveness/`

- **Auth**: `@admin_only @tenant_required`
- **Data source**: `Course.objects.filter(is_published=True, is_active=True)` (auto-tenant-filtered via `TenantSoftDeleteManager`); `TeacherProgress.all_objects` for enrollment/completion; `QuizSubmission.all_objects` with `Avg("score")` for avgScore
- **Response**: `[{courseId, courseName, completionRate, avgScore, enrolledCount}]`

---

## Verification

- Static code review: all three views confirmed with correct decorators, tenant isolation, field shapes ✅
- URL routing confirmed: `/api/v1/reports/analytics/...` maps correctly via `config/urls.py` → `apps/reports/urls.py` ✅
- Model fields confirmed: `TeacherProgress`, `AssignmentSubmission`, `Assignment.passing_score`, `QuizSubmission`, `Course.deadline` all have required fields ✅
- pytest run: deferred to CI/Docker per accepted sandbox blocker

**Expected test result**: `pytest tests/reports/test_analytics_views.py -v` → 35 passed

---

## Key implementation decisions

| Decision | Rationale |
|----------|-----------|
| `approved` = GRADED + score ≥ passing_score | Matches `test_graded_submission_counted_as_approved` (score=90, passing_score defaults to 70) |
| `rejected` = GRADED + score < passing_score | Option A from reviewer note — avoids new status value |
| `courseId` as `str(course.id)` | UUID string as required by `test_course_id_is_valid_uuid_string` |
| `Course.objects` not `all_objects` | Uses `TenantSoftDeleteManager` for automatic tenant + soft-delete filtering |
| Unpublished courses excluded | `filter(is_published=True)` — satisfies `test_unpublished_courses_excluded` |

---

— backend-engineer
