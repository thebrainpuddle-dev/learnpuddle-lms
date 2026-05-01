# FE-012 — Teacher Leagues & Challenges UI

**Date:** 2026-04-20
**Author:** frontend-engineer
**Status:** READY-FOR-REVIEW
**Branch:** maic-sprint-1-presence-rhythm (uncommitted — reviewer may inspect working tree)

## Summary

Built the teacher-facing UI for three backend tracks landed this sprint:

- **TASK-015 Streak Freeze Tokens** — real inventory drives the freeze button on Achievements.
- **TASK-016 Leagues** — new dedicated `/teacher/leagues` page with tier crest, week-ending countdown, standings table, promote/demote zone shading.
- **TASK-017 Daily/Weekly Challenges** — new dedicated `/teacher/challenges` page with Active/Completed tabs, progress bars, time-left, reward indicators.

## Files changed

### New
- `frontend/src/pages/teacher/LeaguesPage.tsx`
- `frontend/src/pages/teacher/LeaguesPage.test.tsx` (6 cases)
- `frontend/src/pages/teacher/ChallengesPage.tsx`
- `frontend/src/pages/teacher/ChallengesPage.test.tsx` (6 cases)

### Modified
- `frontend/src/services/gamificationService.ts` — added typed interfaces (`StreakFreezeInventory`, `CurrentLeague`, `LeagueMember`, `LeagueHistoryEntry`, `TeacherChallenge`, etc.) and methods (`getStreakFreezeInventory`, `spendStreakFreezeToken`, `getCurrentLeague`, `getLeagueHistory`, `getLeagueStandings`, `getActiveChallenges`, `getCompletedChallenges`). Zero `any`.
- `frontend/src/pages/teacher/AchievementsPage.tsx` — freeze token gating, real league card replacing `#N` placeholder, cross-links to leagues + challenges.
- `frontend/src/pages/teacher/AchievementsPage.test.tsx` — updated existing league-card assertion; added 2 new FE-012 cases (freeze-token gating, league data rendering).
- `frontend/src/pages/teacher/index.ts` — new exports.
- `frontend/src/App.tsx` — lazy routes for `/teacher/leagues` and `/teacher/challenges`.
- `frontend/src/components/layout/TeacherSidebar.tsx` — sidebar entries under "My Learning".

## Backend endpoints consumed

- `GET /api/teacher/streak-freeze/inventory/` (TASK-015)
- `POST /api/teacher/streak-freeze/use/` (TASK-015; also preserved legacy `POST /streak-freeze/` path used by existing Achievements mutation)
- `GET /api/teacher/gamification/league/` (TASK-016)
- `GET /api/teacher/gamification/league/history/` (TASK-016; wired in service, not yet surfaced — reserved for future "History" tab)
- `GET /api/teacher/gamification/challenges/` (TASK-017)
- `GET /api/teacher/gamification/challenges/completed/` (TASK-017)

## Verification

- `npx tsc --noEmit` → clean (exit 0).
- `npx vitest run src/pages/teacher/{LeaguesPage,ChallengesPage,AchievementsPage}.test.tsx` → **21/21 passing**.
- Full suite: 371/372 pass. The single failure is a **pre-existing flake in `App.test.tsx`** for the platform-host landing-page heading — unrelated to these changes (my PR didn't touch `App` platform-host logic, the landing page, or the Suspense boundary).

## Visual description

- **LeaguesPage hero:** 20×20 gradient crest (per-tier palette from Bronze I → Diamond), tier name in bold, cohort size + week-of caption, countdown pill on the right showing "2d 3h" remaining.
- **Standings table:** zebra striped, promote zone (top N) shaded emerald-50, demote zone (bottom N) shaded red-50, user's row gets a `ring-2 ring-primary-400` outline plus "You" chip. Outcome column shows Promote / Hold / Demote with arrow icons.
- **ChallengesPage tabs:** Active (fire icon) + Completed (check-badge icon) pill tabs. Active cards: type chip (Daily amber / Weekly primary), title + description, clock+countdown, progress bar (gradient primary→sky) with `N/T` on the right, XP reward row at the bottom with optional badge indicator. Completed cards: emerald-tinted with "Reward claimed" chip.
- **AchievementsPage updates:** "View challenges →" and "View leagues →" links top-right. League stat card now shows tier name ("Silver II") with "1 in cohort" hint and clicks through to `/teacher/leagues`. Freeze section shows live `2 tokens` pill; button disables + relabels "No tokens" when the inventory is empty.

## Notes for reviewer

- The legacy `POST /streak-freeze/` mutation is still used on the Achievements page for the existing "Use freeze" flow (backend prefers inventory consumption and falls back automatically). The new `spendStreakFreezeToken` method is available for a future inline dialog that talks to the explicit `/use/` endpoint.
- `getLeagueStandings` is currently an alias for `getCurrentLeague` because the backend returns standings in the same payload — kept as a separately named method per the task spec to avoid rename churn when the API shape evolves.
- No git operations performed per agent rules.
