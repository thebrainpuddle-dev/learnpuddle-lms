---
tags: [review, task/FE-038, verdict/approve, reviewer/lp-reviewer, area/frontend, area/testing]
created: 2026-04-26
---

# Review: FE-038 — CoursesPage test suite

## Verdict: APPROVE

## Summary

First test coverage for the admin CoursesPage (683 LOC, previously 0 tests) — the highest-surface-area untested admin page. 31 tests across 10 describe blocks. Test-only addition; no production code touched.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
None.

## Notes / verified

- File `frontend/src/pages/admin/CoursesPage.test.tsx` present in tree (355 LOC).
- Reported: `tsc --noEmit` clean; `vitest run src/pages/admin/CoursesPage.test.tsx` 31/31. Pre-existing failures (`maicDb.quota`, `JsonDiffView` hook timeout) unrelated and pre-date this PR.
- Mocking `../../config/api` directly is the correct pattern when the page bypasses the service layer (no service class exists for courses CRUD on this page).
- Bulk-button vs row-button disambiguation via `screen.getByText('selected').closest('div[class*="fixed"]')` then `within(...)` is creative but works. A cleaner long-term fix would be a `data-testid` on the BulkActionsBar fixed container — file as a future polish, not a blocker.
- "Draft" badge vs `<option>Draft</option>` resolved via `tagName === 'SPAN' && className.includes('rounded-full')` — fragile to Tailwind class changes, but pragmatic. Same future-polish note: a stable `data-role` or `data-status` attribute on status badges would harden these.
- `vi.resetAllMocks()` per repo ESLint rule — correct.

## Positive Observations

- Role-gated UI (HOD hides Publish buttons) explicitly asserted — exactly the kind of permissions regression that historically gets missed in feature work.
- Both view modes (table + Kanban) covered, including the toggle round-trip.
- Pagination dual-render (mobile + desktop both in jsdom) handled via `getAllByRole(...).length >= 1`.

## Follow-up suggestions (non-blocking)

- Consider proposing a small refactor adding `data-testid="bulk-actions-bar"` and `data-status="draft|published"` on row badges, which would simplify several tests and make them resilient to styling churn. File as a polish ticket; do not block this merge.

— lp-reviewer
