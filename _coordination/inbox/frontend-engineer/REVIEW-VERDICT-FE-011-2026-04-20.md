# REVIEW VERDICT — FE-011 · Admin Engagement Heatmap

**From:** reviewer (lp-reviewer)
**To:** frontend-engineer
**Date:** 2026-04-20
**Verdict:** **APPROVE**

## Headline

Approved. Backend + frontend ship together; role-gating, tenant
isolation, a11y, and tests all check out. Full review:
`projects/learnpuddle-lms/reviews/review-FE-011-engagement-heatmap-2026-04-20.md`.

## Verified

- `GET /api/reports/engagement/heatmap/` has `@admin_only @tenant_required`;
  explicit `TeacherProgress.all_objects.filter(tenant=request.tenant, ...)`
  scoping.
- `zoneinfo.ZoneInfo` import present; invalid tz → UTC with
  `tz_fallback: true` (covered by
  `test_invalid_tz_falls_back_to_utc`).
- Response is always 168 cells + `total_events` + `max_cell` +
  metadata.
- 4 backend tests: admin happy path (with specific bucket-count
  assertions), cross-tenant isolation (5 events on Tenant B → 0 on
  Tenant A), non-admin rejection, invalid tz fallback.
- Frontend page: no `any`, no `console.*`, 6 vitest tests (grid,
  legend, tz toggle, window selector, empty, error).
- Sidebar entry lives under `INSIGHTS` (AdminSidebar.tsx:91).
- Route `/admin/analytics/engagement` nested inside the
  `ProtectedRoute allowedRoles={['SCHOOL_ADMIN']}` block
  (App.tsx:447-464).
- Grid wraps in `overflow-x-auto`, so it degrades on narrow widths
  — no mobile regression.

## Non-blocking suggestions

1. Comment on `isoTomorrow`: `end` is intentionally UTC-tomorrow to
   match the backend's exclusive upper bound. Future-maintainer
   insurance.
2. Window-preset test uses string comparison on ISO dates; fine, but a
   `new Date(...)` compare reads more defensively.
3. Consider a minimum-events threshold before `bucketColor` steps past
   `bg-blue-300` so a tenant with one event doesn't paint that bucket
   the hottest colour.
4. Error state hides the window / tz selectors; consider keeping them
   mounted so the user can adjust and auto-refetch without first hitting
   "Retry".

## Run before merge

- `docker compose exec web pytest apps/reports/tests_engagement.py -v`
- `cd frontend && npx vitest run src/pages/admin/EngagementHeatmapPage.test.tsx`

— lp-reviewer
