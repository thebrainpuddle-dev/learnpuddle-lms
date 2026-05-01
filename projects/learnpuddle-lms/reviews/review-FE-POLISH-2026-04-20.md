---
tags: [review, task/FE-POLISH, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: FE-POLISH — FE-004/005 + ActivityHeatmap follow-up polish

## Verdict: APPROVE (informational ack — author flagged as no-re-review-required)

## Summary
Three optional follow-up items from the FE-004/005 r2 APPROVE are cleanly implemented
and verified in the source. All three fix exactly the concerns called out in the prior
review note — no scope creep, no regressions, 340/340 vitest + clean `tsc --noEmit`
per the author. Static inspection confirms the code matches the note.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues / Observations

### 1. `GamificationPage.test.tsx` — toast-error regression tests ✅
- `frontend/src/pages/admin/GamificationPage.test.tsx:513` — `createBadge` rejection test
- `frontend/src/pages/admin/GamificationPage.test.tsx:549` — `updateConfig` rejection test
- Both reject with plain `{ code: 500 }` (not `instanceof Error`) so the fallback
  branch in `getErrorMessage` is the one under test, not the `err.message` branch.
  This is precisely the regression class flagged in the prior review ("current suite
  would not catch a toast-wiring regression").
- Assert `role="alert"` + regex-matched fallback text. Correct.

### 2. `ActivityHeatmap.tsx` — magic constant + stable date refs ✅
- `CELL_COLUMN_WIDTH = 13` extracted at module scope
  (`frontend/src/components/analytics/ActivityHeatmap.tsx:62`) and used in the
  month-label `style.left` (line 201). No bare `13` left in the file.
- `today = useMemo(() => startOfDay(new Date()), [])` — **keyed on `[]`**, not
  `[weeks]` as the author's note describes. This is the correct choice (stable
  reference for component lifetime); the note wording is just slightly imprecise.
- `rangeEnd` → `[today]`, `rangeStart` → `[today, weeks]`. Deps are clean.
- `eslint-disable-next-line react-hooks/exhaustive-deps` is gone — confirmed zero
  matches for `eslint-disable` or `toISOString` in the file.

**Nit (won't block, worth tracking):** `today` captured once at mount means if the
component is mounted across a midnight boundary the heatmap won't advance until
next navigation. Not a regression — prior behaviour re-computed on every render,
which was its own bug (unstable refs). If this matters in practice, a 60s setInterval
+ state update on `startOfDay(new Date())` change would fix it. Leaving as a
follow-up observation, not a request.

### 3. `GamificationPage.tsx` — Radar dataKey collision fix ✅
- `radarData` now keys per-teacher values by `teacher_id`
  (`frontend/src/pages/admin/GamificationPage.tsx:647,651,655,659` — all four
  metrics use `Object.fromEntries(top5.map((e) => [e.teacher_id, ...]))`).
- `top5Entries` iterated in the Radar loop (line 802); `dataKey={entry.teacher_id}`
  (unique), `name={entry.teacher_name.split(' ')[0]}` for legend display only.
- The collision case (two teachers sharing a first name silently clobbering each
  other's series) is now impossible — `teacher_id` is DB-unique.

## Positive Observations
- Every follow-up from the prior review is addressed at the exact location flagged,
  with no drift into adjacent files.
- The test-rejection shape (`{ code: 500 }` plain object) is a deliberate choice
  to exercise the fallback branch — shows the author understood *why* the test was
  requested, not just *what* to add.
- Radar fix separates identity (`teacher_id` in data + `dataKey`) from presentation
  (`teacher_name.split(' ')[0]` in `name` for the legend) — clean separation of
  concerns.
- Test count went 338 → 340 (exactly the two tests added); no accidental skips or
  deletions elsewhere.

## Verification (static)
- Code matches author's claims in all three files.
- No `eslint-disable` or `toISOString` residue in `ActivityHeatmap.tsx`.
- No `any` types introduced.
- No new imports of concern.
- Author-reported `npx vitest run → 340/340` + `tsc --noEmit → 0 errors` trusted
  (reviewer sandbox has no Node runtime for re-execution).

No changes requested. Closing the FE-POLISH thread.

— lp-reviewer
