---
tags: [review, task/BE-FE-034, verdict/approve, reviewer/lp-reviewer, area/reports, area/analytics, area/multi-tenant]
created: 2026-04-25
---

# Review: BE-FE-034 — Backend analytics chart endpoints (deadline-adherence, approval-trends, course-effectiveness)

## Verdict: APPROVE

## Summary

Three new GET endpoints under `/api/v1/reports/analytics/` cleanly satisfy the FE-034 contract (matched 1:1 against the previously-approved TDD suite at `tests/reports/test_analytics_views.py`). Tenant isolation, auth guards, response shapes, and N+1 hygiene are all correct. The implementation is small, readable, and uses the right manager (auto-filtered `Course.objects` vs explicit-tenant `*.all_objects`) at each call site. Approve.

---

## Scope verified

**Files in this change:**

- `backend/apps/reports/analytics_views.py` — **new** (287 lines, 3 view functions + 1 helper)
- `backend/apps/reports/urls.py` — 3 path() entries added at top of `urlpatterns`

**URL routing chain confirmed:**
- `config/urls.py` → mounts `apps.reports.urls` under `/api/v1/reports/` (and `/api/reports/` mirror)
- `apps/reports/urls.py:12-14` — three `path("analytics/...", ...)` entries; names follow `analytics_*` convention.
- All 36 TDD tests in `tests/reports/test_analytics_views.py` hit `/api/v1/reports/analytics/...` via `_auth_client`; routing path matches.

**Decorator stack on all three views (verified per-view):**

```
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
```

Same order as the rest of `apps/reports/` — `IsAuthenticated` runs first via DRF, then `@admin_only` rejects TEACHER (403), then `@tenant_required` ensures `request.tenant` is bound. Matches the auth tests at `TestDeadlineAdherenceAuth` / `TestApprovalTrendsAuth` / `TestCourseEffectivenessAuth` (3×3 = 9 auth tests).

---

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

1. **Unused import: `Q`** (`analytics_views.py:20`).

   ```python
   from django.db.models import Avg, Q
   ```

   `Q` is never referenced anywhere in the file. Drop it. (Will trip `flake8 F401` if the linter is on the path.)

2. **`GRADED + score is None` falls into `rejected` bucket** (`approval_trends`, lines 174–179).

   ```python
   if sub.status == "GRADED":
       passing = sub.assignment.passing_score
       if sub.score is not None and sub.score >= passing:
           by_period[period]["approved"] += 1
       else:
           by_period[period]["rejected"] += 1
   ```

   A submission marked `GRADED` with `score=None` is a data-integrity edge case (shouldn't happen in production — graders are required to set a score), but if it ever does, the analytics will silently classify it as `rejected`. Two acceptable resolutions, both non-blocking:

   - Filter `GRADED + score__isnull=True` out of the queryset (treat as data anomaly, log/skip), OR
   - Add a comment line at the `else:` clarifying the intent: "GRADED with missing score is a data anomaly; classified as rejected so it surfaces in the `low approval` slice rather than going invisible."

   The QA tightening test (`test_graded_submission_below_passing_counted_as_rejected`) exercises score=50 < passing=70, so the documented contract is sharp; the edge case just isn't called out in the source. Doc-only nit.

3. **`__date__gte` / `__date__lte` filters use a function-call comparison** (deadline_adherence, approval_trends).

   ```python
   qs = qs.filter(completed_at__date__gte=start)
   ```

   On PostgreSQL this becomes `WHERE DATE(completed_at AT TIME ZONE 'UTC') >= '2026-04-01'`, which is **non-sargable** — the index on `completed_at` is not used. With monthly analytics traffic and a `tenant_id`-prefixed query plan this won't matter at current scale, but a tighter form is `completed_at__gte=tz.make_aware(datetime.combine(start, time.min))` and `completed_at__lt=tz.make_aware(datetime.combine(end + timedelta(days=1), time.min))`, which keeps the index hot. Defer-able; flag for the perf pass when the analytics volume grows.

4. **`avgScore` uses Python `dict.get(cid, 0.0)` for "no submissions" → 0.0** (`course_effectiveness`, line 274).

   The 0.0 default is correct (matches the docstring "0.0 when no submissions"), but the JSON shape conflates "no quiz submissions exist" with "all teachers scored 0". The frontend currently doesn't distinguish, so this matches the contract — but it's worth noting: if FE-034 ever wants a "no data" badge vs a "0 average" badge, the API would need a `null` here. No action needed today.

5. **No `select_related` on `course` in `course_effectiveness`**.

   The course list path uses `.order_by("title")` and then iterates `for course in courses:` reading only `course.id` and `course.title` — both present on the row, no FK traversal. So no N+1. Just calling out that I checked.

---

## Positive Observations

- **TDD discipline is visible end-to-end.** The implementation is the smallest possible code that satisfies all 36 tests; no scope creep, no incidental features. The QA-tester's tightening test (`test_graded_submission_below_passing_counted_as_rejected`) is now landed and the implementation matches its assertion.
- **N+1 prevention done right at every call site.**
  - `deadline_adherence`: `select_related("course")` because the loop reads `tp.course.deadline`.
  - `approval_trends`: `select_related("assignment")` because the loop reads `sub.assignment.passing_score`.
  - `course_effectiveness`: aggregates done in SQL (`Avg("score")` + `.values("course_id", "status")`) rather than per-course Python loops. Three queries total regardless of course count: one for courses, one for progress rollup, one for quiz-score rollup.
- **Manager choice is precise.**
  - `Course.objects.filter(is_published=True, is_active=True)` uses the auto-tenant-scoped `TenantSoftDeleteManager` — correct for the published-courses set.
  - `TeacherProgress.all_objects.filter(tenant=request.tenant, ...)` uses the unfiltered manager but with explicit `tenant=request.tenant` — correct because progress rows are sometimes inspected without TenantManager context (e.g. in this views path the tenant is bound from the request, not threadlocal). Same pattern is used in `apps/reports/views.py`.
  - `QuizSubmission.all_objects.filter(tenant=request.tenant, ...)` — same reasoning.
  - The asymmetry (Course = auto-managed, others = explicit) is deliberate and correct, not sloppy.
- **Tenant isolation tested for all three endpoints.** `test_tenant_isolation` exists in each of the three test classes; each creates Tenant B data and asserts Tenant A's response is `[]`. With the decorator stack + explicit `tenant=request.tenant` filters, the isolation guarantee is double-belt.
- **Field shape matches the FE contract verbatim.** `adherencePercent` (camelCase) on a Python view with snake_case fields elsewhere — frontend's `adminReportsService.ts` uses the same camelCase. `courseId` is `str(course.id)`, satisfying `test_course_id_is_valid_uuid_string`.
- **Stable period sort.** `by_period[period] = {"sort_key": <first_of_month_dt>, ...}` then `sorted(by_period.items(), key=lambda x: x[1]["sort_key"])` produces chronological output regardless of insertion order. Correct approach for "Jan 2026" / "Feb 2026" labels which would otherwise sort lexicographically wrong.
- **`enrolledCount` uses row-count, which is safe** because `TeacherProgress` has `unique_together = [('teacher', 'course', 'content')]` (verified in `apps/progress/models.py:56`). With `content__isnull=True`, there's exactly one row per (teacher, course) — no double-counting risk.
- **Empty-state behavior matches tests.** `if not courses: return Response([])` is the cleanest possible "no data" path. The `test_empty_data_returns_empty_list` and `test_empty_when_no_courses` assertions pass without special-casing.
- **No raw SQL, no `RawQuerySet`, no `extra()` shortcuts.** Pure ORM. Tenant-scope safe by construction.
- **Docstrings on every view name the response shape and field types.** Future maintainers don't need to grep for the frontend contract.

---

## Verification

- **Static review against contract**: all 36 tests' expected fields, types, and bucket-mapping rules are satisfied by the implementation. Hand-traced:
  - 9 auth tests (3 endpoints × {requires_authentication, teacher_cannot_access, admin_can_access}) → decorator stack covers all three cases.
  - 9 shape tests → field names, types, range-bounds match.
  - ~18 data tests → arithmetic, grouping, filters, isolation, status mapping all match.
- **Routing**: `/api/v1/reports/analytics/{deadline-adherence,approval-trends,course-effectiveness}/` resolves via `apps/reports/urls.py:12-14`.
- **Decorator coverage** (independent grep): all three view functions have the same 4-decorator stack; no view is missing `@tenant_required`.
- **Live pytest run deferred to CI** per the same Docker-sandbox blocker accepted at `review-BE-SEC-P0-AUDIT-TEST-RUN-SANDBOX-BLOCKED-2026-04-21.md`. Expectation: `pytest backend/tests/reports/test_analytics_views.py -v` → 36 passed (35 original + 1 QA tightening).

If CI surfaces a failure on any of the 36 tests, treat as a `REQUEST_CHANGES` re-open against this review note rather than a new cycle.

---

## Disposition

- **Verdict:** APPROVE
- **Status transition:** `status/review` → `status/done` once CI confirms green on the analytics test suite (author to send the run summary back to this inbox).
- **Follow-ups (non-blocking, can be filed as separate tickets if any of these become a real issue):**
  - Minor #1 — drop unused `Q` import.
  - Minor #2 — explicit handling / comment for `GRADED + score is None` edge case.
  - Minor #3 — convert `__date__gte` / `__date__lte` to sargable datetime range when analytics traffic grows.

— lp-reviewer
