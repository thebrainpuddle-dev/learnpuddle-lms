---
tags: [review, task/FE-041, verdict/approve, reviewer/lp-reviewer, area/frontend, area/testing]
created: 2026-04-26
---

# Review: FE-041 — GroupsPage test suite

## Verdict: APPROVE

## Summary

First test coverage for the admin GroupsPage — 29 tests across 9 describe blocks covering two-panel layout, Zod-validated create modal, ConfirmDialog deletion, member add/remove, and teacher picker. Test-only addition; no production code touched.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

- (Non-blocking a11y) `group_type` `<select>` has no `htmlFor`/`id` label association — tests must rely on `getByRole('combobox')` selecting the only combobox in the modal. Worth a small a11y fix on the modal markup. Consistent with similar findings in FE-039.

## Notes / verified

- File `frontend/src/pages/admin/GroupsPage.test.tsx` present in tree (424 LOC).
- Reported: `tsc --noEmit` clean; `vitest run` 995/995 (29 new + 0 regressions). 29/29 first-run pass.
- ConfirmDialog "Delete" disambiguation via `within(dialog).getByRole('button', { name: /^Delete$/i })` matches the FE-037 / FE-040 ConfirmDialog pattern — consistent, easy to read.
- Fixture isolation (MEMBER_ALICE in group; BOB / CAROL only in `listTeachers`) keeps the "available to add" computation honest without tests papering over it.
- Implicit-label checkbox-name resolution (`getByRole('checkbox', { name: /Bob Chen/i })`) is the right approach for `<label><input/>name</label>` markup.

## Positive Observations

- Both happy and validation-failure paths of the create modal exercised (empty submit → Zod error; valid submit → success toast + close).
- Server-error onError path tested distinct from validation-error path.
- `selectGroup()` helper concentrates the "click → wait for heading" choreography, keeping the test bodies short and focused on assertions.

— lp-reviewer
