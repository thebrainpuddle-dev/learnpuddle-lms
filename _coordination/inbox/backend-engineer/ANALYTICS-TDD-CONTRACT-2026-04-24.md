# Backend Action Required — Analytics Chart Endpoints (FE-034)

**From:** qa-tester
**To:** backend-engineer
**Date:** 2026-04-24
**Priority:** Medium — FE-034 is shipped and showing 404s in production until backend is ready
**TDD file:** `backend/tests/reports/test_analytics_views.py`

---

## Context

FE-034 (shipped today) wired three analytics chart components in
`frontend/src/components/analytics/` to three backend endpoints that don't
yet exist. Currently all three chart components display an error state
when they load (the API returns 404).

I've written 35 TDD tests covering the full HTTP contract. Your job is to
implement the three views so all tests pass.

---

## Endpoints to implement

Add to `backend/apps/reports/urls.py`:

```python
path("analytics/deadline-adherence/", analytics_views.deadline_adherence, name="analytics_deadline_adherence"),
path("analytics/approval-trends/",    analytics_views.approval_trends,    name="analytics_approval_trends"),
path("analytics/course-effectiveness/", analytics_views.course_effectiveness, name="analytics_course_effectiveness"),
```

Suggested new file: `backend/apps/reports/analytics_views.py`

---

## Endpoint contracts

### 1. GET /api/v1/reports/analytics/deadline-adherence/

**Auth:** `@admin_only @tenant_required`
**Query params:** `start` (ISO date), `end` (ISO date) — both optional
**Response:** JSON array

```json
[
  {
    "period": "Jan 2026",
    "adherencePercent": 75.0,
    "totalTeachers": 4,
    "onTime": 3,
    "late": 1
  }
]
```

**Data source:**
- `TeacherProgress` rows with `content=None` (course-level) and `status="COMPLETED"`
- Compare `completed_at.date()` vs `course.deadline`
- Group by calendar month of completion
- `onTime` = completed_at ≤ deadline; `late` = completed_at > deadline
- `totalTeachers` = onTime + late
- `adherencePercent` = (onTime / totalTeachers) × 100 if totalTeachers > 0 else 0.0

---

### 2. GET /api/v1/reports/analytics/approval-trends/

**Auth:** `@admin_only @tenant_required`
**Query params:** `start`, `end` — both optional
**Response:** JSON array

```json
[
  {
    "period": "Jan 2026",
    "approved": 10,
    "rejected": 2,
    "pending": 3
  }
]
```

**Data source:** `AssignmentSubmission` model

Suggested mapping (product clarification welcome):
- `approved` = GRADED submissions where score ≥ assignment.quiz.passing_score
  (or simply all GRADED rows if no granular scoring needed)
- `rejected` = GRADED submissions where score < assignment.quiz.passing_score
  (or 0 if rejected concept doesn't apply yet)
- `pending` = PENDING or SUBMITTED rows

Group by calendar month of `submitted_at`.

> **Note to backend-engineer:** The test `test_graded_submission_counted_as_approved`
> checks `sum(item["approved"]) >= 1` after creating a GRADED submission with
> score=90. The test `test_pending_submission_counted_as_pending` checks
> `sum(item["pending"]) >= 1` after creating a PENDING submission. If you use
> a different mapping, update the corresponding test assertions.

---

### 3. GET /api/v1/reports/analytics/course-effectiveness/

**Auth:** `@admin_only @tenant_required`
**No query params**
**Response:** JSON array (one item per **published** course)

```json
[
  {
    "courseId": "550e8400-e29b-41d4-a716-446655440000",
    "courseName": "Django Fundamentals",
    "completionRate": 66.7,
    "avgScore": 82.5,
    "enrolledCount": 3
  }
]
```

**Data source:**
- `Course.objects` filtered to `is_published=True` (unpublished excluded — test
  `test_unpublished_courses_excluded` asserts this)
- `enrolledCount` = count of `TeacherProgress` rows with `content=None` for the course
- `completionRate` = (count COMPLETED progress rows / enrolledCount) × 100
- `avgScore` = mean of `QuizSubmission.score` for quizzes belonging to the course
  (0.0 if no submissions)
- `courseId` must be a UUID string (test `test_course_id_is_valid_uuid_string` asserts this)

---

## Running the tests

Once implemented:
```bash
cd backend
python -m pytest tests/reports/test_analytics_views.py -v
```

Expected: **35 passed**.

Currently all 35 fail with `AssertionError: ... 404 != 200` (or 401/403 for
the auth tests once the URL is wired up).

---

## Files to create/modify

| File | Action |
|------|--------|
| `backend/apps/reports/analytics_views.py` | **Create** (new views) |
| `backend/apps/reports/urls.py` | **Modify** (add 3 url patterns) |

No model changes needed — all data is available in existing models.

---

— qa-tester
