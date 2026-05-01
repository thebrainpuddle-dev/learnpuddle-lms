---
tags: [review, task/FE-040, verdict/approve, reviewer/lp-reviewer, area/frontend, area/testing]
created: 2026-04-26
---

# Review: FE-040 — StudentsPage test suite

## Verdict: APPROVE

## Summary

First test coverage for the admin StudentsPage — one of the most feature-dense admin pages. 51 tests across 13 describe blocks: 3 Zod schemas, 3 modals, 2 tabs, dual desktop+mobile layout, BulkActionsBar, ConfirmDialog, CSV import, tenant usage quota. Test-only addition; no production code touched.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
None blocking.

## Notes / verified

- File `frontend/src/pages/admin/StudentsPage.test.tsx` present in tree (720 LOC — appropriate for 51 tests across 3 forms and 2 tabs).
- Reported: `tsc --noEmit` clean; `vitest run src/pages/admin/StudentsPage.test.tsx` 51/51; full suite 966/966 (zero regressions).
- Reviewed dual-layout strategy (`getStudentTableRow()` helper + `getAllByText(...)[0].closest('tr')`) — solid and reusable. Should consider promoting to `frontend/src/test-utils/` if any other dual-layout page tests adopt the pattern.
- Activate/Deactivate substring collision resolved via `/^Activate$/i` exact-match — correct.
- BulkActionsBar split-DOM-nodes (`<span>{count}</span><span>selected</span>`) handled with separate assertions — pragmatic; same generic "data-testid would harden" comment applies.
- Server-error toast tested distinct from validation-error path. Cancel-without-mutation explicitly asserted on every modal.

## Positive Observations

- Zero-iteration delivery for 51 tests (across CRUD on two entities + bulk + invitation flow) suggests the author is well-calibrated on the testing patterns.
- Tenant usage quota (12/100) gets a single-purpose test rather than being lumped in with another flow — easy to find/maintain.
- Filter selects with proper `htmlFor`/`id` (unlike AnalyticsPage) are exercised via `getByLabelText` — preferred a11y-aligned pattern. Confirms label association works elsewhere; AnalyticsPage's filters should be brought to the same standard (separate non-blocking ticket per FE-039 review).

— lp-reviewer
