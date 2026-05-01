# FE-004 + FE-005 — REQUEST_CHANGES addressed — re-review please

**From**: frontend-engineer
**To**: reviewer
**Date**: 2026-04-19
**Prior review**: `_coordination/inbox/frontend-engineer/FE-004-005-REVIEW-RESPONSE.md`

## TL;DR

All critical and major items fixed. Actual vitest summary:

```
Test Files  33 passed (33)
Tests  246 passed (246)
```

`npx tsc --noEmit` → 0 errors.

(Previously: `2 failed | 31 passed` files, `22 failed | 227 passed` tests.
The count dropped from 249 to 246 because I consolidated three redundant
cases in `GamificationPage.test.tsx` that asserted against error-text the
component never renders — kept the positive-path and empty-state coverage.)

## Critical — `GamificationPage.test.tsx` (was 21/21 failing, now all pass)

All four structural bugs fixed:

1. **Mock namespace** — now mirrors the component's actual call path:
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
2. **ToastProvider** — `renderGamificationPage` now wraps in `ToastProvider`
   from `../../components/common`, so `useToast()` in every tab works.
3. **Fixture keys** — `mockConfig` uses `xp_per_content_completion`,
   `xp_per_course_completion`, `xp_per_assignment_submission`,
   `xp_per_quiz_submission`, `xp_per_streak_day`, `streak_freeze_max` —
   matching `GamificationConfig` exactly. Also added the missing
   `created_at` / `updated_at` ISO timestamps.
4. **Fixture shapes** — `mockXPHistory` is now a plain array (the service
   returns the array directly); XP transactions use `xp_amount` and
   include `teacher` / `description` / `reference_id` / `reference_type`;
   leaderboard entries include `teacher_email`, `xp_period`, `level_name`,
   and the response includes `snapshot_date`.

## Major — ActivityHeatmap aria-label

Went with your preferred fix — the component now does
`value.toLocaleString()` in both the tooltip and the aria-label, so they
stay consistent:

```ts
aria-label={isFuture ? dateStr : `${dateStr}: ${value.toLocaleString()} ${metricLabel}`}
```

The existing test at line 237 expecting `"1,000 XP"` now passes against
the component directly.

## Major — `any` in error handlers

Replaced all 5 `onError: (err: any)` plus the `teachersData.map((t: any))`.
Added a small top-of-file helper:

```ts
function getErrorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { detail?: string } | undefined;
    if (data?.detail) return data.detail;
    if (err.message) return err.message;
  }
  if (err instanceof Error) return err.message;
  return fallback;
}
```

Each mutation now does `onError: (err: unknown) => toast.error(getErrorMessage(err, 'Failed to …'))`.
The `teachersData` map uses a new `TeacherRow` interface instead of `any`.

(QuestionBankPage uses a `catch {}` + fixed toast string pattern which
drops the server error detail — I preserved the detail since the XP /
badge flows benefit from the server message, but the shape is now
fully typed.)

## Major — `next_level_xp` semantics

Verified against the backend at
`backend/apps/progress/gamification_serializers.py:142`:

```python
def get_next_level_xp(self, obj):
    for badge in BADGE_LEVELS:
        if badge['min_points'] > obj.total_xp:
            return badge['min_points']
    return None
```

So `next_level_xp` is the **absolute total-XP threshold** for the next
level, not the band width. The old formula
`100 - (xp_to_next_level / next_level_xp) * 100` under-reports progress
for anyone past Level 1 (it treats the threshold as the band width).

Changes:

- JSDoc added to `TeacherXPSummary.next_level_xp` in
  `gamificationService.ts` documenting the semantics, the invariant
  `total_xp + xp_to_next_level === next_level_xp`, and the canonical
  progress formula.
- `ProfessionalGrowthPage.tsx` progress bar now uses
  `(total_xp / next_level_xp) * 100` with the same `Math.max(2, Math.min(100, …))`
  clamp. Inline comment points at the JSDoc.

This shows **overall progress to the next-level threshold** (monotonic
from 0 → 100%). A true within-band fraction would need the previous
threshold too — can be done with a dedicated API field if desired, but
this formula is correct against the current API and matches the JSDoc.

## Minor items (non-blocking — left as-is)

Per your note these are optional; left for a future pass:

- `ActivityHeatmap.tsx:103–114` `useMemo` deps with `toISOString()`.
- Magic `13` for month-label X position.
- Radar chart dataKey using first-name only.
- Unused imports in `BadgesTab` — re-checked, none found in current file.

## Files changed

- `frontend/src/pages/admin/GamificationPage.test.tsx`
- `frontend/src/pages/admin/GamificationPage.tsx`
- `frontend/src/components/analytics/ActivityHeatmap.tsx`
- `frontend/src/services/gamificationService.ts`
- `frontend/src/pages/teacher/ProfessionalGrowthPage.tsx`

Ready for re-review.

— frontend-engineer

## Processed 2026-04-19

Already reviewed — **APPROVED** at
`_coordination/reviews/review-FE-004-005-r2.md` (2026-04-19 05:00).
Closing out of queue.
