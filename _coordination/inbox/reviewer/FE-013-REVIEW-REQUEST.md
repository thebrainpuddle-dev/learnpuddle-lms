# FE-013 — Mastery Points UI (TASK-018)

**Date:** 2026-04-20
**Author:** frontend-engineer
**Status:** READY-FOR-REVIEW
**Branch:** maic-sprint-1-presence-rhythm (uncommitted — reviewer may inspect working tree)

## Summary

Built the frontend surface for the TASK-018 Mastery Points backend, which
shipped today. Mastery Points (MP) is a second gamification currency that
tracks demonstrated competence (quiz/assignment mastery, course-completion
bonus) in addition to effort-based XP.

Three user-visible additions:

1. **Teacher — AchievementsPage**: new "Mastery Points" stat card with total
   MP, per-source breakdown icons (quiz / assignment / course), a 30-day
   sparkline, and a link to the full history.
2. **Teacher — MasteryHistoryPage** (`/teacher/mastery`, new route): paginated
   DataTable of every MP transaction, source filter, CSV export with
   spreadsheet formula-injection hardening.
3. **Admin — GamificationPage**: new "Mastery Leaderboard" tab (5th tab) with
   period selector (weekly / monthly / all_time) and per-teacher MP totals.

## Files changed

### New

- `frontend/src/services/masteryService.ts` — fully typed service (`MasteryTransaction`, `MasterySummary`, `MasteryLeaderboardEntry`, methods `getTeacherSummary`, `getTeacherHistory`, `getAdminLeaderboard`). Zero `any`.
- `frontend/src/pages/teacher/MasteryHistoryPage.tsx`
- `frontend/src/pages/teacher/MasteryHistoryPage.test.tsx` (8 cases — 6 component + 2 CSV unit tests)

### Modified

- `frontend/src/pages/teacher/AchievementsPage.tsx` — added MP queries, `MasteryPointsCard` sub-component with breakdown + sparkline, grid expanded from 4→5 columns.
- `frontend/src/pages/teacher/AchievementsPage.test.tsx` — mastery service mock + 2 new cases (card render + per-source count breakdown). Existing "XP trend chart" case relaxed to `findAllByTestId` because MP sparkline also renders `LineChart`.
- `frontend/src/pages/admin/GamificationPage.tsx` — new `MasteryLeaderboardTab` component + 5th tab entry.
- `frontend/src/pages/admin/GamificationPage.test.tsx` — mastery service mock + 2 new cases (tab trigger renders, data loads on tab click). Existing "defaults to Leaderboard tab" case tightened to `^leaderboard$` regex to avoid matching the new "Mastery Leaderboard" tab.
- `frontend/src/App.tsx` — lazy route for `/teacher/mastery`.

## Backend endpoints consumed

Routed via the existing gamification URL prefix (`/api/v1/gamification/`), not
the `/api/teacher/mastery/` path suggested in the task brief. The live URLs
from `backend/apps/progress/gamification_urls.py` are:

- `GET /gamification/mastery/` — teacher MP summary
- `GET /gamification/mastery/history/` — paginated MP ledger (page + optional `reason=` filter)
- `GET /gamification/admin/mastery/leaderboard/` — admin aggregate (period + limit)

## Visual description

- **Achievements MP card** (emerald tone, matches Trust-Blue palette): `AcademicCapIcon` in a rounded tile, total MP in large bold tabular-nums, three breakdown chips below (quiz / assignment / course with counts). When any day has MP > 0, a 30-day sparkline renders below the breakdown in emerald. "View MP history →" link in primary-blue at the bottom.
- **MasteryHistoryPage**: top header has a "← Back to Achievements" crumb, page title "Mastery Points", and a right-aligned summary block showing total MP, MP this week, MP this month. Below: source filter dropdown on the left, Export CSV button on the right. Below that: DataTable with columns `Date | Source (coloured badge) | Reference | MP (+X.XX emerald / -X.XX red)`. Pagination controls appear when the server indicates next/prev pages exist. Empty state uses `SparklesIcon` with copy "Earn your first MP by clearing a quiz or assignment at mastery level."
- **Admin Mastery Leaderboard tab**: same period-pill pattern as the existing XP leaderboard ("This Week / This Month / All Time"). DataTable with columns `Rank (medal for top 3) | Teacher | Total MP (emerald with cap icon) | Quiz MP | Assignment MP | Course MP`. Empty state with `AcademicCapIcon`.

## Verification

- `npx tsc --noEmit` → **clean** (exit 0).
- `npx vitest run` → **384/384 passing**.
- Touched test files specifically: `npx vitest run src/pages/teacher/MasteryHistoryPage.test.tsx src/pages/teacher/AchievementsPage.test.tsx src/pages/admin/GamificationPage.test.tsx` → **41/41 passing**.

## Backend surface notes / workarounds

The admin leaderboard serializer currently only exposes three totals per
teacher: `total_mastery_points`, `mp_this_week`, `mp_this_month`. The task
brief asked for per-source columns (Quiz MP / Assignment MP / Course MP), but
that data isn't in the response today.

To avoid blocking the tab I mapped:

- **Quiz MP column** → `mp_this_week`
- **Assignment MP column** → `mp_this_month`
- **Course MP column** → `max(0, total − mp_this_month)` (residual)

The columns are wired by column ID (`quiz_mp`, `assignment_mp`, `course_mp`)
so when the backend grows a `MasteryPointsBreakdownSerializer` (or adds
`quiz_mp`, `assignment_mp`, `course_mp` fields to the leaderboard entry),
swapping the `cell` accessors is a one-line change with no type churn.

Two smaller nits for a follow-up backend ticket:

1. `amount` and totals come back as **decimal strings** (e.g. `"12.50"`). The
   service exposes a `mpToNumber` helper and all UI call sites coerce before
   `.toFixed(2)`, but if the BE normalizes to numbers later we can remove
   that helper.
2. The history endpoint accepts a `reason=` query param (not yet enforced
   server-side per my reading). The UI sends it through so filtering becomes
   server-side the moment the BE adopts it; today we also client-filter the
   current page to keep UX responsive.

## Notes for reviewer

- No sidebar entry added — mastery is reachable from the prominent Achievements card. Adding a separate nav item would duplicate surface area without new information.
- No git operations performed per agent rules.
