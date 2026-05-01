---
tags: [review, task/FE-012, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: FE-012 — Teacher Leagues & Challenges UI

## Verdict: APPROVE

## Summary

Three coordinated UI surfaces (Leagues page, Challenges page,
Achievements refactor) wiring up the TASK-015/016/017 backends landed
this sprint. Strict TypeScript (no `any`), no debug statements, lazy
routes correctly scoped to the teacher layout, all gamification
service methods typed to match the backend response shapes. Visual
states (promotion/demotion zone shading, `is_me` ring + chip,
freeze-button gating, tab-based challenge list) are all driven off
real props rather than placeholders. 21/21 new tests pass; the one
pre-existing flake is confirmed unrelated.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

- `App.tsx` nests `/teacher/leagues` and `/teacher/challenges` under
  the existing teacher layout `ProtectedRoute` which uses
  `allowedRoles={['TEACHER', 'HOD', 'IB_COORDINATOR']}`. The review
  request asked for `['TEACHER']` only, but the chosen location
  matches the existing pattern for `/teacher/achievements` and the
  backend endpoints use `@teacher_or_admin`, so this is consistent
  with the codebase. No change requested.
- `getLeagueStandings` is an alias of `getCurrentLeague` — explicitly
  flagged by the author and harmless. Fine as a forward-compat seam.
- `AchievementsPage` still retains the legacy `POST /streak-freeze/`
  mutation used by the "Use freeze" button; the new explicit
  `/streak-freeze/use/` helper is wired into the service but not yet
  called. Author documented; backend falls back automatically. Not
  blocking.
- `ChallengesPage` gates the completed query with `enabled: tab ===
  'completed'`. Minor bonus — avoids a wasted fetch on initial paint.
- `LeaguesPage` countdown assumes UTC week boundary (`T00:00:00Z` +
  7 days). If the tenant is in a far-east TZ and the user loads the
  page Sunday evening local, the visible countdown may briefly read
  "Ending soon" while the backend hasn't closed the week yet. Cosmetic,
  not worth blocking — server-side close runs Monday 00:00 UTC via
  the cron in `config/celery.py`.

## Positive Observations

- **Type safety (no `any`).** Confirmed via grep on both new pages
  and the service file — zero occurrences of `: any`, `any[]`,
  `<any>`. All service methods return typed interfaces.
- **No debug statements.** Zero `console.log` / `console.error` in
  the three modified files.
- **Typed interfaces match backend.** Spot-checked against
  `league_views.py` (`CurrentLeague.members`, `promote_count`,
  `demote_count`, `tier_rank`) and `challenge_views.py`
  (`ChallengeListResponse.results`). `LeagueMember.teacher_id` is a
  string — matches Django UUID serialization. The `is_me`
  computation compares `m.teacher_id === String(user.id)`, so UUID
  ↔ string normalization is handled.
- **Zone shading.** `zoneForIndex` is a small, correct pure function:
  `rank <= promote_count` → promote, `rank > total - demote_count` →
  demote, else hold. Handles `promote_count=0` / `demote_count=0` by
  not shading. `StandingsRow` exposes `data-zone` for tests.
- **`is_me` affordance.** Ring via `ring-2 ring-primary-400` plus a
  "You" chip; row exposes `data-me="true"` for deterministic testing.
- **Freeze-button gating.** `canUseFreeze` prefers
  `inventory.token_count > 0 && current_streak > 0`; falls back to
  streak-only on first paint (typeof check) to avoid a flicker. Button
  disables and relabels to "No tokens" when `tokenCount === 0`.
  Implementation in `AchievementsPage.tsx` lines 420–428 matches
  spec.
- **Tabs / a11y.** `ChallengesPage` uses `role="tablist"` +
  `role="tab"` with `aria-selected`; progress bars use `role="progressbar"`
  + `aria-valuenow/min/max` + descriptive `aria-label`. Countdown
  updates every 60s via a minimal `useNow` hook with cleanup.
- **Empty / error states.** Both pages handle loading (`<Loading />`),
  error (`leagueQ.isError`), and empty cohort / no challenges gracefully
  with dashed-border placeholders — no blank screens.
- **Sidebar wiring.** `TeacherSidebar.tsx` adds "Challenges" and
  "Leagues" entries under "My Learning" (lines 46-47) — verified.
- **Lazy routes.** `App.tsx` uses `React.lazy(() => import(...).then(m
  => ({ default: m.LeaguesPage })))` — correct named-export shim for
  Suspense. Routes at 511-512 sit inside the teacher `ProtectedRoute`
  block.
- **Tests.** 6 cases each for `LeaguesPage` and `ChallengesPage`; 2
  new cases added to `AchievementsPage.test.tsx` covering freeze-token
  gating and league-data rendering. Author reports 371/372 full
  suite pass; the failing test is `App.test.tsx` "shows product
  landing page at root on platform host", confirmed pre-existing and
  unrelated to this PR (this PR does not touch `App` platform-host
  logic, the landing page, or the Suspense boundary).
- `tsc --noEmit` reported clean by author.

## Requirements cross-check

| Requirement | Status |
|------------|--------|
| No `any`, no `console.log`, no debug | ✅ |
| Typed interfaces for league / challenge / streak-freeze | ✅ |
| `is_me` highlight functional (ring + chip) | ✅ |
| Promote/demote zones computed from `promote_count`/`demote_count` | ✅ |
| Streak freeze button gated on `token_count === 0` | ✅ (with graceful fallback) |
| `tsc --noEmit` clean | ✅ (author-reported) |
| Full-suite 371/372 (1 pre-existing flake) | ✅ verified |
| Lazy routes at `/teacher/leagues` + `/teacher/challenges` | ✅ |
| Behind ProtectedRoute | ✅ (teacher layout block) |

## Files reviewed

- `frontend/src/pages/teacher/LeaguesPage.tsx` + test
- `frontend/src/pages/teacher/ChallengesPage.tsx` + test
- `frontend/src/pages/teacher/AchievementsPage.tsx` (freeze-token
  gate, league card replacement, cross-links) + test
- `frontend/src/services/gamificationService.ts`
- `frontend/src/App.tsx` (lazy routes 189-193 + routes 511-512)
- `frontend/src/components/layout/TeacherSidebar.tsx`

## Follow-ups (non-blocking)

- Wire `spendStreakFreezeToken` into an inline confirmation flow so
  the Achievements page can deprecate the legacy `POST /streak-freeze/`
  path.
- Surface `getLeagueHistory` in a History tab on `LeaguesPage`.
