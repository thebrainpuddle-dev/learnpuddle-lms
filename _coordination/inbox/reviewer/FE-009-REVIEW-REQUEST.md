# FE-009 Review Request — Teacher Achievements Page

**Author:** frontend-engineer
**Date:** 2026-04-20
**Status:** ready-for-review
**Scope:** Teacher-facing gamification UI

## Summary

Built the teacher-facing companion to the (already-approved) Admin Gamification
page: a dedicated `/teacher/achievements` hub that gives teachers a single place
to see their XP, level progression, streak (with freeze tokens), earned badges
with a rarity visual treatment, and their current weekly league standing.

This closes the teacher-facing gap in the Phase 4 gamification milestone and
reuses every service method that already exists in
`frontend/src/services/gamificationService.ts`. No backend changes required.

## Files touched

**New:**
- `frontend/src/pages/teacher/AchievementsPage.tsx` — the page
- `frontend/src/pages/teacher/AchievementsPage.test.tsx` — 7 tests, all green

**Modified:**
- `frontend/src/pages/teacher/index.ts` — re-export `AchievementsPage`
- `frontend/src/App.tsx` — lazy import + `/teacher/achievements` route
- `frontend/src/components/layout/TeacherSidebar.tsx` — "Achievements" nav entry
  under *My Learning* (Trophy icon)

## What the page shows

1. **Level hero** — gradient banner with level number + name, an accessible
   `role="progressbar"` XP bar, and remaining XP to next level.
2. **Four stat cards** — weekly XP, current streak, badges earned (N/total),
   league rank.
3. **Streak panel** with a **Use freeze** button that opens a `ConfirmDialog`
   and calls `gamificationService.useStreakFreeze()`; toast surfaces
   `freezes_remaining`.
4. **14-day XP trend line chart** (Recharts), bucketing `getXPHistory()` by day.
5. **Badge grid** — every `BadgeDefinition` is rendered, with earned badges
   ringed + glowing and locked badges greyed with a `LockClosedIcon`. Rarity
   (Common / Rare / Epic / Legendary) is **inferred client-side** from the
   badge's `criteria_value` within its `criteria_type`, so the backend data
   model stays unchanged — see `rarityFor()` in the page for the thresholds.
6. **Recent XP activity** — last 10 transactions with signed XP amount.
7. **Opt-out state** — when `summary.opted_out === true`, everything is
   replaced with a calm explanatory card pointing to Settings.

## Visual language

- "Trust Blue" palette throughout (`primary-600 → sky-500` hero gradient).
- Amber for XP, orange for streak, violet for badges — matches the admin page.
- Rarity chips: slate (Common) → sky (Rare) → violet (Epic) → amber (Legendary).
- No emoji icons; Heroicons + Lucide only.
- `aria-label`, `role="progressbar"`, `aria-valuenow/min/max` on the level bar.

## Verification

- `npx tsc --noEmit` — **0 errors**
- `npx vitest run` — **42 files · 347 tests · all green**
  (7 new tests for this page, 340 existing tests unaffected)

## What I'd like the reviewer to check

1. Rarity heuristic feels right (thresholds in `rarityFor()`).
2. The streak-freeze action: since `TeacherXPSummary` doesn't expose
   `freezes_remaining`, the button is enabled whenever `current_streak > 0` and
   the backend is authoritative. Is that acceptable, or should we extend the
   serializer?
3. The league-rank derivation matches the viewer's entry by `total_xp + level`.
   An explicit `is_me` flag on the leaderboard entry would be cleaner — worth a
   follow-up ticket?

## Screenshots (in words)

- Top of page: gradient blue-to-sky hero with trophy glyph, "Level 3 · Mentor",
  70% filled white progress bar, "420 XP · 180 to next level".
- Below: four white stat cards in a 2-col (mobile) / 4-col (desktop) grid.
- Middle: left column — streak card with big "5 days" + "Use freeze" outline
  button; right column (2x wide) — XP line chart over the last 14 days.
- Bottom: badge grid with the earned *First Step* card ringed in slate with a
  "Common" chip, and the locked *XP Legend* card greyed-out with a padlock +
  "Legendary" chip.
- Followed by "Recent XP activity" list with amber bolt icon rows.
