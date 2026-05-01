---
tags: [review, task/FE-055, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-27
---

# Review: FE-055 — RemindersPage Test Suite

## Verdict: APPROVE

25 tests, all green per author. Coverage is thorough, mocks are sound, and the
tricky DOM collisions (filter "Read" button vs individual "Read" button vs
"Mark all read") are handled correctly with scoped `within()` queries. No
blockers.

## Summary

New test file `frontend/src/pages/teacher/RemindersPage.test.tsx` (25 tests)
exercises the teacher Reminders notification page across header, loading,
empty states, filter tabs (ALL/UNREAD/READ), list rendering, mark-all-read,
individual mark-read, navigation routing, and refresh button. Cross-checked
test selectors against the component source (`RemindersPage.tsx`) — every
queried text/role/title/data-tour matches the implementation.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

### `allBtn.textContent.toContain('2')` is loose-match (line 200)

```ts
expect(allBtn.textContent).toContain('2');
```

Passes for `"All 2"` *and* for `"All 12"`, `"All 22"`, etc. With the current
fixture (2 reminders) it's correct, but a stricter assertion would catch a
future regression where the count formatting changed:

```ts
expect(allBtn.textContent).toMatch(/\b2\b/);
// or
expect(allBtn.textContent?.replace(/\s+/g, ' ').trim()).toBe('All 2');
```

Same applies to `unreadBtn.textContent.toContain('1')` on line 208. Not
blocking — the fixture size makes it safe today.

### `mockGetNotifications.mockReturnValue(new Promise(() => {}))` (line 137)

The "never resolves" pattern is correct and idiomatic, but leaves the promise
permanently un-fulfilled which can keep React Query in pending state across
test boundaries if QueryClient cache leaks. The `gcTime: 0` config in
`makeClient()` plus a fresh client per render mitigates this, so I don't
expect actual flake. Worth noting in case of future suite-wide leaks.

### Filter scoping pattern is correct but could be a helper

The `within(document.querySelector('[data-tour="teacher-reminders-filters"]')!)`
pattern recurs in 4+ tests. A small `getFilterButton(name: RegExp)` helper at
module scope would deduplicate and prevent a future engineer from forgetting
the scoping (which would silently match the wrong button). Cosmetic only.

## Positive Observations

- **Filter "Read" name collision handled correctly.** When unread reminders
  exist, the DOM contains both a filter-tab "Read" button and an individual
  mark-as-read "Read" button. The tests scope filter clicks with
  `within(filterBar)`, which is the right pattern. The accompanying
  test-comment explaining *why* the scoping is needed (line 174-175) is
  exactly the kind of context that prevents the next engineer from
  "simplifying" the test back into a flake.
- **TanStack Query mutation second-arg gotcha** handled correctly with
  `mockMarkAsRead.mock.calls[0][0]` instead of `toHaveBeenCalledWith('r-1')`.
  Inline comment cites the cause. Future test authors won't hit the same
  trap.
- **Behaviour-not-implementation testing**. Assertions check rendered text,
  navigation calls, and mutation invocations — not internal state, not
  component instance methods, not React Query keys. This is the right
  posture: tests will survive component refactors as long as the user-facing
  contract holds.
- **Complete empty-state matrix**. ALL/UNREAD/READ each have their own
  empty-state copy and the tests verify all three independently. Plus the
  school-admin hint variant for ALL. Easy to forget; covered here.
- **Mock hygiene**. `vi.clearAllMocks()` in `beforeEach` prevents inter-test
  state bleed. Fresh `QueryClient` per render via `makeClient()` prevents
  cache pollution. Both correct.
- **Selector strategy is accessibility-first**: `getByRole('heading',{level:1})`,
  `getByRole('button',{name:.../i})`, `getByTitle('Mark as read')` — these
  selectors are exactly what an assistive-tech user would use, so the tests
  double as a11y regression coverage.
- **Verification was actually run**:
  `npx vitest run src/pages/teacher/RemindersPage.test.tsx → 25/25 passed` —
  with the count stated. No vague "should pass" claims. Matches
  `superpowers-verification-before-completion`.

## Cross-checked against component

Verified each test selector against `RemindersPage.tsx`:

| Test expectation | Component source | OK |
|---|---|---|
| `data-tour="teacher-reminders-filters"` | line 120 | ✅ |
| `"Loading reminders..."` | line 151 | ✅ |
| `"No reminders yet"` / `"No unread reminders"` / `"No read reminders"` | line 156 | ✅ |
| `"When your school admin sends reminders..."` | line 159 | ✅ |
| `title="Mark as read"` | line 201 | ✅ |
| `navigate('/teacher/courses/${course}')` | line 66 | ✅ |
| `navigate('/teacher/assignments')` | line 67 | ✅ |
| `markAsRead` / `markAllAsRead` mutations | lines 46, 51 | ✅ |

## Note on FE-056 (TeacherStudyNotesPage)

Author flagged that FE-056 is written but unverified due to "53+ hung vitest
worker processes from prior session runs". Correct posture — submitting only
what was verified. **Reminder for the FE-056 review**: please include the
verification command output (pass/fail counts) when the system recovers and
the suite is re-run, same as you did here.

## Status

- Review request → **closed, approved**.
- FE-055 → **merge-ready**.
- Three minor improvement suggestions noted above, none blocking.

— lp-reviewer
