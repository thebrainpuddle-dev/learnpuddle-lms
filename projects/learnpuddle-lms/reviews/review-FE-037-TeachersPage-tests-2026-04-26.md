---
tags: [review, task/FE-037, verdict/approve, reviewer/lp-reviewer, area/frontend, area/testing]
created: 2026-04-26
---

# Review: FE-037 — TeachersPage test suite

## Verdict: APPROVE

## Summary

First test coverage for the admin TeachersPage — the management hub for the platform's primary user role. 23 tests across 8 describe blocks, all passing. Test-only addition; no production code touched.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
None.

## Notes / verified

- File `frontend/src/pages/admin/TeachersPage.test.tsx` present in tree.
- Reported: `tsc --noEmit` clean; `vitest run` 797/797 (23 new + 0 regressions vs 774).
- Dual-layout (`hidden md:block` + `block md:hidden`) mocking strategy via `getAllByText` documented as a known jsdom limitation — sensible workaround.
- ConfirmDialog disambiguation via `within(await screen.findByRole('dialog'))` is the correct, scalable pattern for Headless UI dialogs whose confirm button shares an accessible name with the trigger button.
- `findByRole` (with implicit `waitFor`) for BulkActionsBar timing avoids a race that previously failed with `getByRole`. Worth noting in repo testing-conventions doc if not already.

## Positive Observations

- Server-error path tested with the actual DRF error shape (`response.data.email = [...]`), not a synthesized `Error()` — good fidelity.
- Zod validation path tested independently of the success path.
- Inactive-teacher state verified to hide the Deactivate button — small but easy regression to miss.

— lp-reviewer
