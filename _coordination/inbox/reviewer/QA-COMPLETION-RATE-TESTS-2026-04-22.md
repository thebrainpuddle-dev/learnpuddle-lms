# Review Request — completion_rate tests

**From:** qa-tester
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-22
**Re:** `backend/apps/courses/tests_completion_rate.py`

---

## Summary

New test file covering the real `completion_rate` implementation shipped by
the backend-engineer in their 2026-04-22 entry (Fix 2 — Real `completion_rate`
in `CourseListSerializer`).

**File:** `backend/apps/courses/tests_completion_rate.py`
**Tests:** 6

---

## Test coverage

| Test | Assertion |
|------|-----------|
| `test_completion_rate_returns_real_value` | 1 of 2 assigned teachers with a course-level COMPLETED progress row → `completion_rate == 50.0` |
| `test_completion_rate_zero_when_no_teachers` | Course with no assigned teachers → `completion_rate == 0.0` |
| `test_completion_rate_100_when_all_complete` | All 2 assigned teachers COMPLETED → `completion_rate == 100.0` |
| `test_completion_rate_ignores_content_level_rows` | `TeacherProgress` rows with `content != None` (in-progress content items) do NOT count → `completion_rate == 0.0` |
| `test_completion_rate_zero_for_assigned_to_all_with_no_completions` | `assigned_to_all=True` course + active teachers but no completions → `completion_rate == 0.0` |
| `test_completion_rate_rounds_to_one_decimal` | 1 of 3 teachers completed → 33.333… rounded to `33.3` |

All 4 scenarios specified by the backend-engineer in the shared-log (1/2 = 50%,
no teachers = 0%, all = 100%, content-level rows ignored) are covered, plus 2
bonus scenarios (assigned_to_all, rounding).

---

## Implementation notes

- Uses `GET /api/v1/courses/` (full view + annotation path) so the `_completed_teacher_count`
  annotation in `course_list` is exercised — not just the serializer fallback.
- `TeacherProgress.all_objects.create(...)` used throughout to bypass the
  `TenantManager` contextvar filter in tests (consistent with `factories.py` pattern).
- `_make_tenant` creates a unique subdomain per test run via `uuid4().hex[:6]` to
  prevent collisions in concurrent test runs.
- `@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")` for
  tenant middleware resolution.

---

## What I'm NOT claiming

Static verification only — cannot run `pytest` in the agent sandbox (known
project-wide Docker limitation). CI will be the first live run.

---

**No git commits. No git add. No git push.**

— qa-tester
