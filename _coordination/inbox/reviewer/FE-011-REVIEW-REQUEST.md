# FE-011 Review Request — Admin Engagement Heatmap

**Branch:** `maic-sprint-1-presence-rhythm` (uncommitted working tree)
**Author:** frontend-engineer
**Date:** 2026-04-20

## Scope

Closes the last Phase 4 analytics UI gap — the **Admin Engagement
Heatmap** at `/admin/analytics/engagement`. The page renders a
tenant-wide 7 (day-of-week) × 24 (hour-of-day) grid of teacher
activity, colour-graded from cool to warm, with a timezone toggle
(local vs. UTC) and a 7/30/90-day window selector.

No backend endpoint existed for this shape of data. Per the task brief,
option (A) — a lightweight aggregation endpoint — was preferred because
a tenant with even modest activity easily blows past the 50-row heuristic
(`TeacherProgress.last_accessed` fires on every progress write). Doing
the bucketing server-side keeps the response at a predictable 168 cells.

## Backend changes

### New files
- `backend/apps/reports/engagement_views.py` — `engagement_heatmap`
  view. `@admin_only @tenant_required`. Accepts `tz` (IANA, defaults
  UTC, invalid values fall back to UTC with a `tz_fallback=true`
  flag), `start`, `end` (ISO dates). Buckets by Python
  `datetime.weekday()` (Mon-first) × `.hour`, using `zoneinfo`. Signal
  used: `TeacherProgress.last_accessed`. Window is clamped at 365 days.
  Query is tenant-scoped via `all_objects.filter(tenant=…)` to
  sidestep any thread-local TenantManager surprises in tests.

- `backend/apps/reports/tests_engagement.py` — 4 tests:
  1. Admin-happy-path with fixed timestamps → expected bucket counts,
     correct `max_cell`, `total_events`, and 168-cell shape.
  2. Cross-tenant isolation — 5 events in Tenant B do not leak into
     Tenant A's response.
  3. Non-admin (TEACHER) → 401/403.
  4. Invalid `tz` → 200 with `timezone:"UTC"`, `tz_fallback:true`.

### Modified
- `backend/apps/reports/urls.py` — route
  `GET /api/reports/engagement/heatmap/`.

## Frontend changes

### New files
- `frontend/src/pages/admin/EngagementHeatmapPage.tsx` — custom CSS-grid
  heatmap (no new libs). Tailwind-only colour scale: `slate-100` →
  `blue-100/300/500/600/700`. Each cell is a `role="gridcell"` with
  `data-testid`, `data-count`, and a `title` tooltip. Header controls:
  window `<select>` (7/30/90 days) + timezone `<select>` (Local vs.
  UTC; local is auto-detected via `Intl.DateTimeFormat`). Summary
  strip shows window range, total events, peak cell. Legend row under
  the grid. Empty + error states both have dedicated test IDs.
- `frontend/src/pages/admin/EngagementHeatmapPage.test.tsx` — 6 tests:
  grid render with counts, legend, empty state, error + retry,
  timezone-toggle refetch with `tz:'UTC'`, window-preset refetch
  producing a fresher `start`.

### Modified
- `frontend/src/services/adminReportsService.ts` — typed
  `engagementHeatmap(params)` + `EngagementHeatmapResponse`,
  `EngagementHeatmapCell`, `EngagementHeatmapParams` interfaces. No
  `any` introduced.
- `frontend/src/App.tsx` — `React.lazy` import + new
  `analytics/engagement` route nested under the admin shell.
- `frontend/src/components/layout/AdminSidebar.tsx` — **Engagement
  Heatmap** entry under **INSIGHTS**, uses `FireIcon`, `tourId`
  `admin-nav-engagement`.
- `frontend/src/pages/admin/index.ts` — re-export `EngagementHeatmapPage`.

## Visual description

- Header row: title with flame icon + explainer; right-aligned
  `Window` and `Timezone` selects.
- Summary strip: three cards — window range, total events, peak cell.
- Main panel: the grid itself lives in a bordered card, with a small
  pill showing the effective timezone (with `(fallback)` suffix when
  the backend swapped an invalid tz). Column headers are compact
  "12a, 1a, … 11p" labels; row headers are Mon–Sun. Cells are 24px tall
  with the count shown inside non-zero buckets; zero-buckets stay
  neutral grey.
- Legend: "Less → More" with a 6-swatch row matching the step colours.
- Empty state: centred flame icon + "No engagement yet in this window"
  copy, replacing the grid but leaving the header/summary intact.
- Error state: role="alert" red card with *Retry* button.

## Verification

- `npx tsc --noEmit` — 0 errors.
- `npx vitest run src/pages/admin/EngagementHeatmapPage.test.tsx` —
  **6/6 green**.
- Regression sample (`SkillRadarPage`, `DashboardPage`) — 18/18 green.
- Backend tests written following the pattern in `apps/reports/tests.py`;
  they could not be executed from this agent environment (no docker CLI
  available in sandbox). Ready to run via
  `docker compose exec web pytest apps/reports/tests_engagement.py`.

No commits were made per agent rules.
