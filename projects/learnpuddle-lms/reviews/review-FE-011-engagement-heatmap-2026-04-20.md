---
tags: [review, task/FE-011, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: FE-011 — Admin Engagement Heatmap

## Verdict: APPROVE

## Summary

Closes the Phase 4 analytics UI gap with a focused, accessible, and
tenant-scoped engagement heatmap. Backend aggregation is the correct
option given `TeacherProgress.last_accessed` fires on every progress
write. Frontend renders a proper `role="grid"` with deterministic test
IDs and useful empty/error states. No `any`, no console noise, no
regressions. Safe to merge.

## Checks performed

### Backend (`backend/apps/reports/engagement_views.py`)

- Endpoint decorated with `@admin_only @tenant_required` — verified
  via `test_rejects_non_admin` (teacher gets 401/403).
- Tenant scoping uses `TeacherProgress.all_objects.filter(tenant=request.tenant, ...)`
  — explicit, and paired with the bypass-TenantManager rationale in
  the docstring. Cross-tenant isolation verified by
  `test_cross_tenant_isolation` (5 events on Tenant B, 0 leaking into
  Tenant A's response).
- `zoneinfo.ZoneInfo` import is correct; invalid tz values fall back
  to `"UTC"` with `tz_fallback=true` in the response
  (`test_invalid_tz_falls_back_to_utc`).
- Response shape is locked down: 7 × 24 = 168 cells every time
  (even when empty), plus `total_events`, `max_cell`, `timezone`,
  `tz_fallback`, `start`, `end`. Verified by
  `test_admin_sees_buckets_aggregated_for_own_tenant` (asserts both
  `len(cells) == 168` and the specific bucket counts).
- Window is clamped to `MAX_WINDOW_DAYS=365`.
- Iteration uses `qs.iterator(chunk_size=2000)` — safe for large
  tenants.
- Route registered: `GET /api/reports/engagement/heatmap/` (see
  `apps/reports/urls.py` diff).

### Backend tests (`tests_engagement.py`)

- 4 tests — admin happy path with exact bucket assertions,
  cross-tenant isolation, non-admin rejection, invalid-tz fallback.
- Uses a real login via `/api/users/auth/login/` with
  `HTTP_HOST="test.lms.com"` so the full middleware stack
  (tenant resolution + auth) is exercised.
- Directly `UPDATE`s `last_accessed` after create to work around
  `auto_now` — pragmatic and acceptable.

### Frontend (`EngagementHeatmapPage.tsx`)

- No `any` types anywhere; `EngagementHeatmapResponse`,
  `EngagementHeatmapCell`, `EngagementHeatmapParams` are all in
  `adminReportsService.ts`.
- No `console.log`/`console.error` statements.
- Sidebar entry lives under `INSIGHTS` with `FireIcon` and
  `tourId="admin-nav-engagement"` (AdminSidebar.tsx:91).
- Route `/admin/analytics/engagement` is nested inside the
  `ProtectedRoute allowedRoles={['SCHOOL_ADMIN']}` block in
  `App.tsx:447-464` — role-gated correctly.
- Grid is built via CSS grid with `gridTemplateColumns: '56px repeat(24, minmax(22px, 1fr))'`
  wrapped in `overflow-x-auto`, so it degrades cleanly on narrow
  viewports.
- Cells expose `role="gridcell"`, `data-testid="heatmap-cell-{day}-{hour}"`,
  `data-count`, and a readable `title` tooltip — good a11y posture.
- Colour scale is discrete (5 steps + empty), a11y-safe.
- Empty state (`heatmap-empty`) and error state (`heatmap-error`
  with `role="alert"` and a Retry button) both present.
- TZ toggle auto-detects via `Intl.DateTimeFormat` with a `try/catch`
  fallback to `'UTC'`.

### Frontend tests (`EngagementHeatmapPage.test.tsx`)

- 6 tests, matching the scope statement: grid/counts, legend, empty
  state, error + retry, tz-toggle refetch with `tz: 'UTC'`, window
  preset refetch with fresher `start`.
- Uses `@testing-library/user-event` for controls — realistic
  interaction model.
- Mocks `adminReportsService.engagementHeatmap` via
  `vi.mock(...)` + `vi.mocked(...)`.

### Service wiring (`adminReportsService.ts`)

- Strips undefined params before issuing the GET — no
  `?tz=undefined` in the wire payload.
- Types are exhaustive and match the backend contract 1:1.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues / Notes (non-blocking)

1. **`isoTomorrow`** sets `end` to `today + 1` in UTC. That's
   intentional and matches the backend's "end is exclusive" contract.
   Worth a one-line comment — a future maintainer might see "why is
   end in the future?" and try to "fix" it.
2. **`window` preset comparison** in the window-preset test uses a
   lexicographic string comparison (`String(latest.start) > String(first)`).
   That happens to work for ISO `YYYY-MM-DD`, but a
   `new Date(...)` compare would be more defensible to readers.
3. **`bucketColor` threshold ladder** is reasonable but uses
   `>` 0.8 / 0.6 / 0.4 / 0.2. A cell with exactly `count == max`
   (ratio == 1) lands in `>0.8` → `bg-blue-700` — correct. But a
   single-event tenant produces `ratio == 1.0` in its own bucket and
   gets the hottest colour, which can look alarming. Consider a
   minimum-events threshold before colouring past `bg-blue-300`, in
   a later polish pass.
4. **Error state does not re-expose the window / tz selectors.**
   When the API fails the user cannot change the window without first
   retrying successfully. Low priority.
5. **Backend docstring** says "Signal used: `TeacherProgress.last_accessed`"
   but this field is set by `auto_now` rather than an explicit signal
   — the word "signal" is overloaded here. Purely cosmetic.

## Positive Observations

- The bucket test asserts **specific day/hour counts** and the
  `max_cell` value — catches off-by-one and tz-drift regressions in a
  way a "just count totals" test would miss.
- Cross-tenant isolation uses two real tenants with two subdomains
  (`test` and `other`) — properly exercises
  `TenantMiddleware.resolve_tenant`, not just an ORM filter.
- Frontend uses `useMemo` for both the browser-tz detect and the
  derived `start`/`end`, keeping the queryKey stable — no re-render
  thrash.
- All interactive elements carry labels (`<label htmlFor=...>`).

## Test plan

- Backend: `docker compose exec web pytest apps/reports/tests_engagement.py -v`
- Frontend: `cd frontend && npx vitest run src/pages/admin/EngagementHeatmapPage.test.tsx`
- Regression: `npx tsc --noEmit` across the frontend tree.

---
Reviewed by: lp-reviewer
