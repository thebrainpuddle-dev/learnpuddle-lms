---
tags: [review, task/QA-COMPLETION-RATE-TESTS, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-22
---

# Review: QA-COMPLETION-RATE-TESTS — tests_completion_rate.py (6 tests)

## Verdict: APPROVE

## Summary
Six net-new tests in `backend/apps/courses/tests_completion_rate.py` cover the
real `completion_rate` shipped by backend-engineer (Fix 2, 2026-04-22). All four
scenarios called out in the shared-log are present plus two well-chosen bonus
cases (`assigned_to_all=True` with zero completions, rounding to 1dp = 33.3).
Tests exercise the annotation path through `GET /api/v1/courses/`, not just the
serializer fallback. No production code touched.

## Verification performed

1. **All 6 tests exist with correct assertions** (file lines 144–290):
   - `test_completion_rate_returns_real_value` — 1 of 2 teachers → `50.0` (line 159-163).
   - `test_completion_rate_zero_when_no_teachers` — no assignments → `0.0` (line 178-182).
   - `test_completion_rate_100_when_all_complete` — 2 of 2 → `100.0` (line 203-207).
   - `test_completion_rate_ignores_content_level_rows` — content-level IN_PROGRESS
     row does NOT count → `0.0` (line 230-238).
   - `test_completion_rate_zero_for_assigned_to_all_with_no_completions` —
     `assigned_to_all=True` + 2 active teachers + 0 completions → `0.0` (line 259-264).
   - `test_completion_rate_rounds_to_one_decimal` — 1 of 3 → `33.3` (line 285-290).

2. **Annotation path exercised.** `_get_course_data` hits `GET /api/v1/courses/`
   (line 132), which routes to `course_list_create` in
   `backend/apps/courses/views.py:116`. The queryset annotation
   `_completed_teacher_count=Count('progress', filter=Q(progress__content__isnull=True,
   progress__status='COMPLETED'), distinct=True)` is applied at lines 145–152, and
   `CourseListSerializer.get_completion_rate` (serializers.py:197) prefers
   `obj._completed_teacher_count` when present. Tests therefore cover the
   production hot path, not only the DB-count fallback.

3. **Tenant/middleware hygiene correct.**
   - `@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")` on the
     TestCase (line 114).
   - Unique subdomain per test via `uuid.uuid4().hex[:6]` in `_make_tenant`
     (line 31). `Host` header (`f"{subdomain}.lms.com"`) lets `TenantMiddleware`
     resolve the right tenant per request.
   - `TeacherProgress.all_objects.create(...)` used in both helpers
     (`_complete_course`, `_inprogress_content`) to bypass the `TenantManager`
     contextvar that is not populated inside `TestCase.setUp`. Matches the
     existing `factories.py` pattern.

4. **No production code modified.** Only new files in the diff; `serializers.py`
   and `views.py` show no churn tied to this task (their modifications predate
   it and were reviewed separately in `review-BE-CALENDAR-CALLBACK-AND-
   COMPLETION-RATE-2026-04-22.md`).

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **Sandbox could not execute `pytest`** — known project-wide Docker limit.
   Review is static only; CI will be the first live run. Not a defect.

2. **`_make_content` hard-codes `content_type="TEXT"`.** Fine for this test; if
   future coverage needs video/quiz-type rows for content-level progress
   assertions, the helper will need a parameter. Non-blocking.

3. **Helper duplication.** `_make_tenant` / `_make_user` / `_make_course`
   overlap with `apps/courses/tests/factories.py` helpers used elsewhere. Keeping
   the new file self-contained is fine, but a follow-up could de-dupe into the
   shared factory module. Non-blocking.

## Positive Observations

- Each test has a clear docstring tying the assertion back to the backend-engineer
  shared-log scenario numbering.
- The rounding test (33.3) guards against silent regressions if someone swaps
  `round(..., 1)` for `int()` or drops the multiplier order.
- The `assigned_to_all=True` test explicitly creates active teachers so
  `get_assigned_teacher_count` returns a non-zero denominator — the test would
  false-pass as 0.0 otherwise.
- Content-level ignore test creates a real `Module` + `Content` and a
  `status="IN_PROGRESS"` row, so it actually exercises the `content__isnull=True`
  filter in the annotation.

— lp-reviewer
