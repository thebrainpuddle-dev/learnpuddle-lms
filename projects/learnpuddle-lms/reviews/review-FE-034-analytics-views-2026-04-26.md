---
tags: [review, task/FE-034, verdict/approve, reviewer/lp-reviewer, area/backend, area/analytics]
created: 2026-04-26
---

# Review: FE-034 — Analytics chart endpoints (backend)

## Verdict: APPROVE

## Summary

Three new admin analytics endpoints (`deadline-adherence`, `approval-trends`, `course-effectiveness`) implementing the FE-034 TDD contract. Decorators correct, tenant isolation correct, response shapes match the contract. Approve.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

- (Performance, future-watch) `deadline_adherence` and `approval_trends` iterate the queryset in Python (`for tp in qs: ...` / `for sub in qs: ...`) to bucket by month. With `select_related("course")` / `select_related("assignment")` this is N rows not N+1 — fine today. At larger scale (multi-year ranges, big tenants) this will become noticeable. A future hardening could use `.annotate(period=TruncMonth(...))` + `.values('period').annotate(...)` to push the grouping into PostgreSQL. Not blocking.

## Notes / verified

- `apps/reports/analytics_views.py` decorators on all three views: `@api_view(["GET"]) → @permission_classes([IsAuthenticated]) → @admin_only → @tenant_required`. Confirmed by direct read.
- Tenant isolation: every `*.all_objects.filter(...)` call carries an explicit `tenant=request.tenant` — required since `all_objects` bypasses `TenantManager`. The single `Course.objects.filter(is_published=True, is_active=True)` relies on `TenantSoftDeleteManager` for tenant scoping (correct) — comment in file documents this. Consistent with the project convention.
- `course_effectiveness` cross-table join `quiz__assignment__course_id__in=course_ids` is bounded by the prior `Course.objects` lookup which is already tenant-scoped, AND it adds an explicit `tenant=request.tenant` filter — defence in depth. Good.
- Date parsing: `_parse_date` rejects bad input by returning `None` (no 500 on malformed `?start=foo`). Inclusive `gte`/`lte` semantics on both date-range endpoints match the contract.
- Approval-trends two-tier GRADED scoring: `score >= passing_score → approved`, `score < passing_score → rejected`. Edge case: `score IS NULL` on a GRADED submission falls to `else: rejected` — debatable (could be argued this should be `pending`), but the contract per the request note is "two-tier", so this is the agreed semantics. Worth documenting in the docstring as an explicit choice.
- Course effectiveness UUID serialisation via `str(course.id)` consistently — good.

## Verification gap

- Author noted: tests not run on host due to `pythonjsonlogger` being missing on Homebrew Python 3.13; verification was static analysis. Reasonable given the constraint, but I'd like the qa-tester or backend-engineer to confirm `docker compose exec web pytest tests/reports/test_analytics_views.py -v` passes before declaring this fully done — please request that confirmation. **Approving on code; CI/Docker test-run is the final gate.**

## Positive Observations

- Module docstring lists endpoints and explicitly states the `@admin_only + @tenant_required` invariant — good norm to follow on new modules.
- `defaultdict(int)` for the per-course tallies keeps the bucket-init code clean and impossible to forget.
- Empty-courses early return (`if not courses: return Response([])`) prevents pointless joins downstream.

## Follow-up suggestions (non-blocking)

- Add the "GRADED with `score IS NULL` is treated as rejected" semantic as a single docstring sentence in `approval_trends`.
- Consider DB-side TruncMonth aggregation if a large-tenant scaling concern materialises.

— lp-reviewer
