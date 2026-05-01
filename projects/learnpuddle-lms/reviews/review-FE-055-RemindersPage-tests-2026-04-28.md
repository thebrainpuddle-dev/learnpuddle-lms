---
tags: [review, task/FE-055, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-28
---

# Review: FE-055 — Teacher RemindersPage tests (25 tests)

## Verdict: APPROVE

## Summary
Test-only addition for `frontend/src/pages/teacher/RemindersPage.tsx`. 25 well-scoped
tests cover header (user/tenant), loading, the three filter empty-states, filter
tabs and counts, list rendering, "Mark all read" visibility/behavior, individual
mark-read button (with the documented "Read" accessible-name collision properly
handled via filter-bar scoping), course/assignment navigation, and refresh button
presence. Selectors map cleanly to the component source.

## Verification

| Check | Result |
|---|---|
| Engineer pass count claim | 25/25 (per request) |
| Reviewer static cross-check vs `RemindersPage.tsx` | All assertions map to component lines 84 (h1), 86 (subtitle), 100–104 (Mark all read), 119–146 (filter tabs with `data-tour="teacher-reminders-filters"`), 151 (loading), 156–160 (empty-state copy per filter), 183 (title), 189 (message), 196–205 (individual `title="Mark as read"` button), 64–69 (`handleClick` navigation rules) |
| `Read` accessible-name collision handling | Confirmed — filter-bar `[data-tour="teacher-reminders-filters"]` scoping is used wherever both buttons could be in the tree (lines 175–176, 187–192, 198–199, 332–333) |
| TanStack Query mutation second-arg gotcha | Correctly addressed — uses `mockMarkAsRead.mock.calls[0][0]` instead of `toHaveBeenCalledWith('r-1')` (lines 272, 301) |
| Reviewer local vitest re-run | **Not completed** — system-wide vitest worker exhaustion called out in `QA-FRONTEND-SUITE-RUN-2026-04-27.md`. Engineer attestation + selector verification stand in. The full-suite QA run on 2026-04-27 reports the recently-added teacher-page test files (310 tests across 8 files including this one's neighbors) all pass; no concerning signal. |

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **Refresh button click is not exercised.** Line 340–344 only asserts the button
   is rendered — it doesn't click and verify `refetch` runs (or that
   `unreadReminderCount` / `notificationUnreadCount` are invalidated, lines 59–60
   of the component). A 3-line click + `mockGetNotifications` re-call assertion
   would lock that branch in. Non-blocking.

2. **`handleClick` fallback branch is uncovered.** Line 68 of the component —
   `else navigate('/teacher/courses')` for a reminder with neither `course` nor
   `assignment` — has no test. Easy to add a third fixture and one assertion.
   Non-blocking.

3. **`Updated X ago` timestamp branch uncovered.** Line 90–94 of the component
   conditionally renders the relative time when `dataUpdatedAt > 0`. Not tested.
   Low value (date-fns formatting), but the conditional itself is unproven.

4. **`markAsRead` / `markAllAsRead` failure paths not tested.** No assertion that
   the UI stays sane on mutation rejection. The component has no error UI today
   so this is a coverage gap rather than a bug — flag for when error UX lands.

5. **`User` undefined / empty `theme.name` branches not tested.** Component uses
   optional chaining (`user?.first_name`, `theme.name ?` ...) but the tests
   always supply both. If `useAuthStore` ever returns `{ user: null }` during the
   page's lifetime, a regression here would slip through. Minor.

## Positive Observations

- **Filter-bar scoping for the "Read" collision** (lines 175, 187, 332) is
  exactly the right fix for the documented two-button accessible-name overlap.
  Done consistently every place the collision could matter, not just where it
  immediately broke.

- **TanStack Query second-arg pattern** is correctly captured via
  `mock.calls[0][0]` rather than `toHaveBeenCalledWith('r-1')`. This is the
  same gotcha that has bitten earlier teacher-page suites; nice that it's
  documented inline (comments at lines 271, 300).

- **Three distinct empty-state assertions** (`No reminders yet`, `No unread
  reminders`, `No read reminders`) plus the school-admin hint copy match the
  component's three-way conditional precisely (lines 156–159 of source).

- **Loading test uses an unresolved promise** rather than racing the resolution
  — the right pattern for proving the loading branch renders synchronously
  before any data arrives.

- **Per-test `QueryClient` with `gcTime: 0, retry: false`** — same pattern as
  the rest of the teacher-page suite, prevents cross-test cache leakage.

- **Mock strategy is minimal and load-bearing**: only mocks the boundary
  (`notificationService`, stores, `useNavigate`, `usePageTitle`). The component
  itself runs through the real React/TQ render cycle.

- **Filter-tab count assertions** (`allBtn.textContent.toContain('2')`,
  unread `1`) are robust against the count-formatting whitespace in the
  component (lines 138–143), which an exact-text assertion would have made
  fragile.

## Closing

Approve as-is. The minor items above are coverage nice-to-haves; none block.
FE-055 may be moved to `status/done` for the test-suite scope.

— lp-reviewer
