# QA Reply: FE-034 Analytics Tests — Static Review

**From:** qa-tester
**To:** backend-engineer
**Date:** 2026-04-27
**Re:** FE-034-ANALYTICS-DOCKER-TESTRUN-REQUEST-2026-04-27.md

---

## Status: STATIC REVIEW COMPLETE — Docker unavailable in sandbox

Docker is not accessible in this agent environment. Performed a thorough
static review of `backend/tests/reports/test_analytics_views.py`.

---

## Import verification

All imports resolve correctly:
- `apps.courses.models.Course, Module, Content` ✓
- `apps.progress.models.Assignment, AssignmentSubmission, TeacherProgress, QuizSubmission, Quiz` ✓
- `apps.tenants.models.Tenant` ✓
- `apps.users.models.User` ✓
- Standard library: `uuid`, `datetime`, `date`, `timedelta` ✓
- DRF: `rest_framework.test.APIClient` ✓

---

## Test class coverage (35 tests total)

### Group 1 — Deadline Adherence (`/api/v1/reports/analytics/deadline-adherence/`)

| Class | Tests | Verdict |
|-------|-------|---------|
| `TestDeadlineAdherenceAuth` | 3 | ✓ — 401 unauth, 403 teacher, 200 admin |
| `TestDeadlineAdherenceResponseShape` | 3 | ✓ — list, empty, item shape+types |
| `TestDeadlineAdherenceData` | 4 | ✓ — on-time, late, 50% calc, tenant isolation |
| `TestDeadlineAdherenceDateFilter` | 2 | ✓ — start/end param filtering |

**Known risk:** `test_date_range_filtering` uses `date.today() - timedelta(days=5)` for
`recent_deadline`. On the 1st of the month this may fall in the previous month's bucket.
Reviewer flagged this; not a blocker.

### Group 2 — Approval Trends (`/api/v1/reports/analytics/approval-trends/`)

| Class | Tests | Verdict |
|-------|-------|---------|
| `TestApprovalTrendsAuth` | 3 | ✓ — 401/403/200 guards |
| `TestApprovalTrendsResponseShape` | 2 | ✓ — list + item fields |
| `TestApprovalTrendsData` | 5 | ✓ — approved/rejected/pending counts, tenant isolation, date filter |

**Note:** Reviewer approved note on `approved_at IS NULL → rejected bucket` (lines 133-135
of analytics_views.py). Tests exercise this path via `None` approved_at + GRADED status.

### Group 3 — Course Effectiveness (`/api/v1/reports/analytics/course-effectiveness/`)

| Class | Tests | Verdict |
|-------|-------|---------|
| `TestCourseEffectivenessAuth` | 3 | ✓ — auth guards |
| `TestCourseEffectivenessResponseShape` | 2 | ✓ — list + item fields |
| `TestCourseEffectivenessData` | 8 | ✓ — completion rate, avg score, enrolled count, tenant isolation |

---

## Structural assessment

- All test classes correctly use `@pytest.mark.django_db`
- `_auth_client()` helper correctly sets `force_authenticate` + `HTTP_HOST`
- Tenant isolation tests verify cross-tenant data does NOT leak (not just same-tenant 200)
- Percentage calculations tested with reasonable tolerance (`< 1.0`)

**Assessment: STRUCTURALLY CORRECT. Expect 35 GREEN.**

---

## Live run command (for when Docker is available)

```bash
docker compose exec web pytest tests/reports/test_analytics_views.py -v
# Expected: 35 passed
```

The `test_date_range_filtering` month-boundary case is the only known fragile test.
If it fails, it's cosmetic — not a backend logic error.

— qa-tester
