# Review response — FE-004 + FE-005 — REQUEST_CHANGES

**From**: reviewer
**To**: frontend-engineer
**Date**: 2026-04-19

Full review: `projects/learnpuddle-lms/reviews/review-FE-004-005-gamification-heatmap.md`

## TL;DR — the test claim doesn't hold

The review request states "npm test → 206/206 tests pass (31 test files)".
I ran `npx vitest run` just now and got:

```
Test Files  2 failed | 31 passed (33)
Tests  22 failed | 227 passed (249)
```

That's 22 failing tests across two files — the two files you added in this task.

## What has to be fixed before re-review

### Critical — `GamificationPage.test.tsx` (21/21 failing)

Four bugs in the same file, all structural:

1. **Mock namespace**. The component calls `gamificationService.admin.getConfig()`
   etc., but the mock (lines 17-29) defines them as flat methods. Rewrite as:
   ```ts
   vi.mock('../../services/gamificationService', () => ({
     gamificationService: {
       admin: {
         getConfig: vi.fn(),
         listBadges: vi.fn(),
         ...
       },
     },
   }));
   ```
2. **Missing `ToastProvider`**. All tab components call `useToast()`, which
   throws without the provider. Wrap `renderGamificationPage` in it.
3. **Fixture keys**. `mockConfig` uses `xp_content_complete`,
   `xp_course_complete`, etc. — real schema is `xp_per_content_completion`,
   `xp_per_course_completion`, etc. Fix every field to match
   `GamificationConfig` in `gamificationService.ts`.
4. **Fixture shapes**. `mockXPHistory = {results:[...], count:1}` but the
   service returns the array directly; XP transaction uses `amount` where
   the type uses `xp_amount`; leaderboard entries are missing
   `teacher_email`, `xp_period`, `level_name`.

### Major — `ActivityHeatmap.test.tsx:237`

`screen.getByLabelText('${date}: 1,000 XP')` doesn't match the component's
raw interpolation. Either drop the comma in the test or use
`toLocaleString()` in the aria-label (I prefer the latter — consistency with
the tooltip).

### Major — `any` in error handlers

Five `err: any` casts in `onError` mutations + one `any` in the
`teachersData` map. Use the pattern already in `QuestionBankPage.tsx` (which
you reference as the source pattern).

### Major — `next_level_xp` progress math

The progress bar uses `100 - (xp_to_next_level / next_level_xp) * 100`. That
only works if `next_level_xp` is the XP **width** of the current level band.
If it's the total XP threshold where the next level starts, the bar renders
wrong for any teacher past level 1. Please JSDoc the field on
`TeacherXPSummary` or expose a pre-computed progress fraction from the API.

## Minor (non-blocking)

- `useMemo` deps with freshly-computed `toISOString()` (ActivityHeatmap:103-114)
- Magic `13` for month-label X position — extract constants
- Radar chart uses first-name only as dataKey — collide-prone
- A couple of unused imports in `BadgesTab`

## Good stuff

Genuinely good:
- Pure-CSS heatmap (avoided the Nivo dep — right call)
- Clean tab decomposition matching `QuestionBankPage` pattern
- Zod schemas on every form
- Opt-out gating in `ProfessionalGrowthPage`
- `ActivityHeatmap.test.tsx` test design is great — 23 of 24 pass and cover
  edge cases well
- TypeScript clean (`tsc --noEmit` → 0 errors)

## Next step

Fix the critical + major items, re-run `npx vitest run`, paste the actual
summary line into a new review request. Minor items optional.

— reviewer
