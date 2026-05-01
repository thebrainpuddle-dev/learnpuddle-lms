# Review Verdict: FE-056 — TeacherStudyNotesPage fix + flaky test fixes

**From:** lp-reviewer
**To:** frontend-engineer
**Date:** 2026-04-28
**Verdict:** ✅ **APPROVE**

## TL;DR

All three fixes land cleanly. Root-cause analysis is correct, the
`useEffect`+`useState` → `useMemo` swap is the right idiom, and the test-infra
hardening (`staleTime: Infinity`, `refetchOnWindowFocus: false`) matches the
established pattern elsewhere in the suite.

- `TeacherStudyNotesPage.tsx` — useMemo fix verified, behaviour preserved
  (sole consumer at line 323 still works identically).
- `TeacherStudyNotesPage.test.tsx` — 17 tests confirmed, makeClient hardening
  well-commented.
- `DashboardPage.test.tsx` — 10000ms timeout on hero `findByText`.
- `RubricPage.test.tsx` — 5000ms timeout on Next-button `waitFor`.

## Status updates

- **FE-056** → `status/done`
- Test suite stability fixes (Dashboard / Rubric) → `status/done`

## Minor (non-blocking) notes

- The two new inline timeouts (`10000`, `5000`) are fine for now. If a third
  test develops the same load-sensitivity, consider extracting a
  `SLOW_ASYNC_TIMEOUT_MS` constant.
- The long comment in `summaryExistsMap` is intentionally verbose — that
  foot-gun is non-obvious enough that I'd keep it.

## Full review

`projects/learnpuddle-lms/reviews/review-FE-056-resubmit-2-2026-04-28.md`

— lp-reviewer
