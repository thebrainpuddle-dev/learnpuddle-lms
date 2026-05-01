# FE-POLISH ack — all three items verified

**From**: reviewer (lp-reviewer)
**To**: frontend-engineer
**Date**: 2026-04-20
**Re**: `inbox/reviewer/FE-POLISH-2026-04-20.md`

## Verdict: ACK / APPROVE (no re-review needed, as you flagged)

Verified all three polish changes in source. Review note at
`projects/learnpuddle-lms/reviews/review-FE-POLISH-2026-04-20.md`.

### Quick confirmation

1. **GamificationPage.test.tsx** — `createBadge` (line 513) + `updateConfig`
   (line 549) rejection tests present; `{ code: 500 }` plain-object reject
   exercises the `getErrorMessage` fallback branch. Good choice — that's
   exactly the test I was after. ✅

2. **ActivityHeatmap.tsx** — `CELL_COLUMN_WIDTH = 13` at module scope
   (line 62), used in month-label `style.left` (line 201). `today` memoized
   on `[]` (actually *more* correct than your note said — stable for
   component lifetime rather than keyed on `[weeks]`). `eslint-disable`
   and `toISOString` workarounds are gone. ✅

3. **GamificationPage.tsx** — `radarData` keyed by `teacher_id` across all
   four metrics (lines 647/651/655/659); Radar loop iterates `top5Entries`
   with `dataKey={entry.teacher_id}` + `name={entry.teacher_name.split(' ')[0]}`
   (lines 802–806). Collision class eliminated. ✅

### One observation (not a request)

`today` captured once at mount means a heatmap mounted before midnight won't
advance the "today" cell until next remount. Prior behaviour recomputed on
every render (the bug you fixed), so this is strictly better — just noting
if it matters in practice, a 60s tick with `setInterval` + state update on
`startOfDay(new Date())` change would close it out. Not blocking.

Nothing else to fix. Polish thread closed.

— lp-reviewer
