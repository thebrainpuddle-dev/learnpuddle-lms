---
tags: [review, task/FE-010, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: FE-010 — Admin Skill Radar Page

## Verdict: APPROVE

## Summary
Small, well-scoped UI on top of an existing tenant-scoped endpoint.
Types are strict, error + empty states are real, the category filter
actually re-keys the React Query, and the 5 new vitest cases exercise
the behaviors that matter. No new libraries, no `any`.

## Requirements vs. acceptance criteria
- Backend endpoint is correct and already guarded.
  `GET /api/reports/manager/skills-overview/` is decorated
  `@teacher_or_admin @tenant_required` in
  `backend/apps/reports/manager_views.py` (line 311-313). Tenant
  scoping is enforced inside the view via `_get_managed_teachers`.
- Route `/admin/analytics/skills` is nested under the `SCHOOL_ADMIN`
  `ProtectedRoute` block in `App.tsx` (line 444), so SCHOOL_ADMIN
  gating is correct. SUPER_ADMIN does not receive direct access via
  this shell, which matches the existing admin-analytics convention.
- Sidebar entry lives under INSIGHTS with `tourId`
  `admin-nav-skill-radar`.
- No `any` introduced. `SkillOverviewItem`,
  `SkillsOverviewSummary`, `SkillsOverviewResponse`,
  `SkillOverviewTeacherDetail` are all explicitly typed.
- No `console.log` left in the page.
- Recharts usage is standard; `ResponsiveContainer` + `RadarChart`
  + two `<Radar>` series; no new dependencies.
- Error path: `role="alert"` red panel with a Retry button that calls
  `query.refetch()`. Covered by test
  `renders a recoverable error state when the API fails`.
- Category filter re-fetches via React Query key
  `['admin', 'skills-overview', { category }]`. Test
  `refetches with category param when filter changes` asserts
  `mockedOverview` is called with `{ category: 'Pedagogy' }`.

## Critical issues
None.

## Major issues
None.

## Minor issues
- `categoriesQuery.queryFn` casts `res.data as string[]`. Upstream
  `skillsService.categories` already types the response; exposing a
  `string[]` return from the service would be marginally cleaner than
  casting inside the page.
- Coverage color thresholds (80/50) are inline magic numbers. Fine for
  one screen; if this logic recurs elsewhere, extract to a util.
- The `PolarRadiusAxis` uses `domain={[0,5]}` while `toRadarRows`
  computes a dynamic `fullMark`. If a tenant uses a >5 scale the axis
  will clip even though the data supports it. Low-impact — level 5 is
  the product default.
- Radar series use red/green-adjacent palette only indirectly
  (blue/amber); fine for colour-blind safety. Legend has readable
  labels, which covers the accessibility path.

## Positive observations
- `axios.isAxiosError` guard in `getErrorMessage` pulls real server
  `detail` when available and falls back cleanly.
- Focus-areas card filters `below_target > 0` before sorting by gap,
  so skills already at/above target do not pollute the top-5.
- jsdom-safe Recharts mocks in the test keep the suite deterministic
  without snapshotting SVG.
- `data-testid` markers on stat cards, radar wrapper, focus list and
  table make tests terse and the DOM semantically labelled.
- `MemoryRouter` + `QueryClientProvider` + `ToastProvider` render
  harness matches the existing test convention.
- Empty-state copy is helpful, not just "No data".
- `tsc --noEmit` clean; 352/352 vitest green as reported.

## Verification status
Reviewer did not rerun vitest/tsc; author reports both green.
Recommend CI to re-confirm. No functional concerns.
