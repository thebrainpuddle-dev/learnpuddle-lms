---
tags: [review, task/FE-056, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-28
---

# Review: FE-056 — TeacherStudyNotesPage worker crash + flaky test fixes

## Verdict: APPROVE

## Summary
Three small, well-targeted fixes that resolve the FE-056 vitest worker crash
and two pre-existing flaky tests. Root-cause analysis is correct, the fix is
the textbook React solution (derived state via `useMemo`, not
`useState`+`useEffect`), and the test-infra hardening matches established
patterns elsewhere in the suite.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
1. **Inline timeout literals** — `DashboardPage.test.tsx` and
   `RubricPage.test.tsx` now use raw `10000` / `5000` ms values. Not a blocker,
   but if more tests develop the same load-sensitivity it would be worth
   centralising as a `SLOW_ASYNC_TIMEOUT_MS` test constant. Skip for now;
   only revisit if a third occurrence appears.
2. **Comment in `summaryExistsMap` is long** (`TeacherStudyNotesPage.tsx`
   lines 109–114) — the block reads almost like prose. It is accurate and
   genuinely useful (the foot-gun is non-obvious and likely to recur), so
   I'm leaving it as-is. Just flagging for taste.

## Positive Observations
- **Correct root-cause diagnosis.** The `useState<Set>` + `useEffect([summaries])`
  combo with `data: summaries = []` from `useQuery` *will* loop while data is
  `undefined` because the destructuring default produces a fresh `[]` reference
  every render. This is a real React 19 / vitest interaction bug, not a mis-fix.
- **Right idiom.** Replacing the effect with `useMemo` is the canonical
  derived-state pattern. No state mutation → no re-render → no loop. Same
  observable behaviour for consumers (`summaryExistsMap.has(item.id)` still
  works identically and updates when `summaries` changes).
- **Test infra hardening is consistent** with other test files in the suite
  (`staleTime: Infinity` + `refetchOnWindowFocus: false` is the established
  pattern for TanStack Query under vitest+happy-dom).
- **Inline comments** explain *why* (not just what) for both `useMemo` and
  the `makeClient()` defaults — exactly what we want for non-obvious test
  infrastructure choices.
- **Behaviour preserved.** I traced the only consumer of `summaryExistsMap`
  (line 323, `summaryExistsMap.has(item.id)`) — semantics are identical to
  the previous `useState` value.
- **Test count matches claim.** 17 tests in `TeacherStudyNotesPage.test.tsx`,
  matching the "17/17 PASS" claim.

## Files Verified
- `frontend/src/pages/teacher/TeacherStudyNotesPage.tsx` — useMemo fix correct,
  imports cleaned up (removed `useEffect`).
- `frontend/src/pages/teacher/TeacherStudyNotesPage.test.tsx` — `makeClient()`
  hardening present and well-commented.
- `frontend/src/pages/admin/DashboardPage.test.tsx` — explicit 10000ms timeout
  on `findByText` for hero heading.
- `frontend/src/pages/admin/RubricPage.test.tsx` — explicit 5000ms timeout on
  `waitFor` for Next-button-disabled assertion.

## Status Update
- FE-056 → `status/done`
- Test suite stability fixes (Dashboard/Rubric) → `status/done`
