# FE-034 Analytics — TDD Tests Approved & Ready

**From:** reviewer
**To:** backend-engineer
**Date:** 2026-04-24
**Re:** Implementing the three analytics endpoints

---

QA-tester landed 35 TDD tests in `backend/tests/reports/test_analytics_views.py` defining the
HTTP contract for FE-034. I've reviewed them — **APPROVED**. They will return 404 until you
implement the views. Use them as your spec.

## Endpoints to implement

Add to `apps/reports/urls.py` and `apps/reports/views.py`:

| Method+Path | Returns |
|---|---|
| `GET /api/v1/reports/analytics/deadline-adherence/` | `[{period, adherencePercent, totalTeachers, onTime, late}]` |
| `GET /api/v1/reports/analytics/approval-trends/` | `[{period, approved, rejected, pending}]` |
| `GET /api/v1/reports/analytics/course-effectiveness/` | `[{courseId, courseName, completionRate, avgScore, enrolledCount}]` |

All three must:
- Be decorated `@admin_only @tenant_required`
- Honor tenant isolation (the tests verify a second tenant's data must not leak)
- Accept optional `start` and `end` ISO-date params (deadline-adherence + approval-trends)
- Exclude unpublished courses (course-effectiveness only)

## Implementation notes from the tests

- **deadline-adherence**: an "on time" completion is `TeacherProgress.completed_at <= course.deadline`,
  "late" is the inverse. Group by month-period (string like "Jan 2026").
- **approval-trends**: tests treat `AssignmentSubmission.status == 'GRADED' && score >= passing_score`
  as `approved`. The `rejected` mapping is **undefined** — pick one and tell QA so they can
  tighten the test:
  - Option A: `GRADED && score < passing_score`
  - Option B: introduce a new status value
  - Option C: stay at 0 forever
- **course-effectiveness**: `enrolledCount` = teachers with a course-level `TeacherProgress`
  row (i.e. `content=None`). `avgScore` = mean of `QuizSubmission.score` for quizzes attached
  to the course. `completionRate` = `COUNT(status='COMPLETED') / enrolledCount * 100`. Must
  filter `Course.is_published=True`.

## Run the failing tests first

```bash
docker compose exec web pytest backend/tests/reports/test_analytics_views.py -v
```

You'll see 35 failing/error tests — all 404s. Implement the views, re-run, watch them go green.

## Heads-up

There's a known month-boundary edge case in `test_date_range_filtering` (uses `now - 1day`
which crosses month boundaries on the 1st). Reviewer/QA agreed not blocking; will tighten
in a follow-up.

— reviewer
