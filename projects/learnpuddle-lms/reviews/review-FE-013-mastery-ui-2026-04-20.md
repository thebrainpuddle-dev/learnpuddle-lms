---
tags: [review, task/FE-013, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: FE-013 — Mastery Points UI

## Verdict: APPROVE

## Summary
Clean TypeScript surface for the TASK-018 mastery-points backend. Typed
service layer with decimal-string coercion via `mpToNumber`, 384/384 tests
green, tsc clean, formula-injection-hardened CSV export mirroring the
existing Gradebook pattern. The admin-leaderboard per-source placeholder is
clearly documented and isolated to a single-line swap when the backend
serializer grows the breakdown fields.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
1. **Admin Mastery Leaderboard — per-source columns are placeholders.** Quiz
   MP / Assignment MP / Course MP columns currently map to
   `mp_this_week` / `mp_this_month` / `max(0, total − mp_this_month)`.
   Documented clearly in the review request and in code. This is a
   **follow-up for backend-engineer** to extend the admin leaderboard
   serializer with `quiz_mp`, `assignment_mp`, `course_mp` (or a nested
   `MasteryPointsBreakdownSerializer`). Not blocking FE-013 approval, but
   the data shown to admins is misleading until that lands — flag for an
   expedited BE follow-up so the UI doesn't ship with surrogate numbers for
   long. Suggest filing TASK-021 (mastery-leaderboard per-source breakdown).
2. **History endpoint `reason=` query param** — frontend sends it; if the
   backend ignores it today the client-side filter is a correct fallback
   (`filteredRows` memo). Worth a BE smoke-check that the param is wired.

## Positive Observations
- **Type strictness**: zero `any` in `masteryService.ts`, `MasteryHistoryPage.tsx`,
  or the touched test files. Decimal-string fields (`amount`,
  `total_mastery_points`, etc.) all flow through `mpToNumber` before any
  numeric formatting — no `parseFloat(x).toFixed(2)` footguns.
- **CSV hardening**: `downloadMasteryCsv` prefixes any cell starting with
  `=`, `+`, `-`, `@` with an apostrophe (regex `/^[=+\-@]/`) and escapes
  embedded quotes. Matches the `GradebookPage` pattern verbatim. Unit test
  `prefixes formula-injection payloads with a leading apostrophe` asserts
  it.
- **URL paths are correct**: `/api/v1/gamification/mastery/`,
  `/api/v1/gamification/mastery/history/`, and
  `/api/v1/gamification/admin/mastery/leaderboard/` exactly match the live
  routes in `backend/apps/progress/gamification_urls.py` (lines 97-108).
  The author correctly recognised the task brief's `/api/teacher/mastery/`
  path was stale.
- **Test count**: 8 cases in `MasteryHistoryPage.test.tsx` (6 component + 2
  CSV unit), +2 in each of `AchievementsPage.test.tsx` and
  `GamificationPage.test.tsx` — all reported 384/384 passing and I
  spot-checked the `describe`/`it` structure.
- **Existing-test preservation**: the "XP trend chart" case was relaxed to
  `findAllByTestId` because the MP sparkline also renders a `LineChart`,
  and the admin "defaults to Leaderboard tab" case was tightened to
  `^leaderboard$` to avoid matching the new "Mastery Leaderboard" tab.
  Both are sensible, non-destructive adaptations.
- **UX details**: lazy route for `/teacher/mastery`, empty states use
  consistent Heroicons, emerald palette aligns with Trust-Blue brand.
- **No new sidebar entry** — correctly reasoned that the Achievements card
  is a sufficient entry point and a nav item would duplicate surface.

## Verification
- `npx tsc --noEmit` clean.
- `npx vitest run` → 384/384.
- Touched-file subset → 41/41.
- Grep for `any` in new files: zero hits.
- Backend URL cross-check: exact match.

## Files reviewed
- `frontend/src/services/masteryService.ts` (NEW, typed, `mpToNumber` helper)
- `frontend/src/pages/teacher/MasteryHistoryPage.tsx` (NEW)
- `frontend/src/pages/teacher/MasteryHistoryPage.test.tsx` (NEW, 8 cases)
- `frontend/src/pages/teacher/AchievementsPage.tsx` (MOD, MP card + sparkline)
- `frontend/src/pages/teacher/AchievementsPage.test.tsx` (MOD, +2 cases)
- `frontend/src/pages/admin/GamificationPage.tsx` (MOD, 5th tab)
- `frontend/src/pages/admin/GamificationPage.test.tsx` (MOD, +2 cases)
- `frontend/src/App.tsx` (lazy route)
- Backend cross-check: `backend/apps/progress/gamification_urls.py`
