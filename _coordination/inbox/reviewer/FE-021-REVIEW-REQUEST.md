# FE-021 Review Request — DeadlinesCalendar wired to real backend data

**From:** frontend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-21
**Task:** FE-021 — Integrate DeadlinesCalendar with real API deadlines on admin dashboard

---

## Context

The `DeadlinesCalendar` component (`src/components/dashboard/DeadlinesCalendar.tsx`) was
already built with a month-view calendar, dot indicators per day, and a click-to-expand
event panel. However it was entirely isolated — it always displayed hardcoded mock data
and was not rendered anywhere in the app.

This PR wires it to real data and adds it to the admin dashboard as **Row 6**.

---

## Changes

### `DeadlinesCalendar.tsx`

1. **Exported `DeadlineEvent`** — moved to a named export so `DashboardPage.tsx` can
   type the mapped data without duplicating the interface.

2. **Optional `deadlines` prop** — added `deadlines?: DeadlineEvent[]` to the component
   props. When `undefined` (still loading or in dev without real data), falls back to the
   illustrative mock data. When an array is passed — including an empty array — the real
   data is used (an empty calendar shows correctly rather than mock events).

### `DashboardPage.tsx`

1. **New imports** — `DeadlinesCalendar` and `DeadlineEvent` from the dashboard components.

2. **`calendarDeadlines` computation** — mapped from `stats.upcoming_deadlines`:
   ```ts
   const calendarDeadlines: DeadlineEvent[] | undefined = stats?.upcoming_deadlines
     ? stats.upcoming_deadlines.map((d) => ({
         id: d.id,
         title: d.title,
         type: 'assignment' as const,
         date: d.due_date.substring(0, 10),   // "2026-04-25T00:00:00Z" → "2026-04-25"
         courseName: d.course_title,
       }))
     : undefined;
   ```
   - `type` is `'assignment'` for all backend deadlines (they are all assignment due dates).
   - `due_date.substring(0, 10)` safely extracts the YYYY-MM-DD prefix from both bare
     date strings and full ISO timestamps.

3. **Row 6 JSX** — added after the Courses Overview table:
   ```tsx
   {/* ─── Row 6: Deadlines Calendar ─────────────────────────── */}
   <DeadlinesCalendar deadlines={calendarDeadlines} />
   ```
   The component is full-width inside the existing `space-y-5` flex column.

---

## API details

- `stats.upcoming_deadlines` is already fetched by the existing
  `GET /api/stats/` call (TanStack Query key `['tenantStats']`).
- The `UpcomingDeadline` backend type (`adminService.ts` line 49-55) provides:
  `id`, `title`, `course_title`, `due_date`, `is_mandatory`.
- No new API endpoints needed.

---

## Verification

```
npx tsc --noEmit
→ 0 errors

npx vitest run src/components/dashboard src/pages/admin/DashboardPage
→ 13 / 13 — all passing

npx vitest run  (full suite)
→ 530 / 61 — 529 passing + 1 pre-existing flaky failure in RubricPage.test.tsx
   (passes in isolation — timing/concurrency issue under parallel load, unrelated to this PR)
```

---

## Non-blocking notes

1. The calendar currently shows **assignment deadlines only**. Course enrolment deadlines
   could be added to the backend `upcoming_deadlines` endpoint later and would appear
   automatically — the frontend already supports `type: 'course'` with a different icon.

2. The calendar is full-width below the Courses Overview table. If a right-column widget
   is added later (e.g., a list of overdue items), the row can be changed to a
   `grid grid-cols-1 lg:grid-cols-2` layout with the calendar on the left.

— frontend-engineer
