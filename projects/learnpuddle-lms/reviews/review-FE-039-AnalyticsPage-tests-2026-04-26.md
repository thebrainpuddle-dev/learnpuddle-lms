---
tags: [review, task/FE-039, verdict/approve, reviewer/lp-reviewer, area/frontend, area/testing, area/analytics]
created: 2026-04-26
---

# Review: FE-039 — AnalyticsPage test suite

## Verdict: APPROVE

## Summary

First test coverage for the admin Analytics dashboard — 61 tests across 13 describe blocks. The most feature-rich analytics page in the codebase: 4 recharts visualisations, 4 custom chart components, drill-down view, focus filter pills, two filter dropdowns, collapsible Needs-Attention panel, and a reminder mutation flow. Test-only addition; no production code touched.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

- (Non-blocking accessibility) Filter `<select>` elements lack `htmlFor`/`id` association so tests must use `getAllByRole('combobox')[N]` indexing. The author has already flagged this. Worth filing a small a11y polish ticket — assistive tech also can't programmatically tie label to control.

## Notes / verified

- File `frontend/src/pages/admin/AnalyticsPage.test.tsx` present in tree (868 LOC — generous but reasonable for 61 tests including extensive recharts/chart-component mocks).
- Read-through of first 120 lines confirms: standard recharts stub pattern, named-export service mocks (`adminService`, `adminReportsService`, `adminRemindersService`), MemoryRouter+QueryClientProvider wrapper, focused test fixtures.
- Reported: `tsc --noEmit` clean; `vitest run src/pages/admin/AnalyticsPage.test.tsx` 61/61; full suite 915/915 passing (zero regressions).
- `retryDelay: 0` in QueryClient is the correct fix for a real flake mode (component-level `retry: 1` overrides `retry: false` in test client → default 1000ms backoff approached `findByText` timeout on slow CI). Good catch.
- Inactive-count assertion via `closest('.bg-amber-50')?.textContent` is acceptable. Same generic suggestion as FE-038: a stable `data-testid` would harden.

## Positive Observations

- Reminder mutation flow tested individual + bulk + error + post-send "Sent" label state — full lifecycle.
- Conditional rendering of Student Analytics and Needs-Attention sections (hidden at total/inactive == 0) explicitly verified at both branches — the kind of conditional that often degrades to "always visible" silently.
- Chart drill-down callbacks wired through stubs and tested for the navigation outcome (4 of them) — keeps the test honest without re-testing chart internals.
- Focus filter pills (all/teachers/students) tested for both showing AND hiding the appropriate sections.

— lp-reviewer
