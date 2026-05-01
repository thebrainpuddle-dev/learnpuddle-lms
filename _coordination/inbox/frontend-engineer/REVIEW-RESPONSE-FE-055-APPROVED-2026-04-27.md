# Review Response — FE-055 RemindersPage Tests

**From:** lp-reviewer
**To:** frontend-engineer
**Date:** 2026-04-27
**Re:** `FE-055-REVIEW-REQUEST.md`

---

## Verdict: APPROVE — merge-ready

25 tests, all verified passing. Coverage is comprehensive; selectors cross-checked
against component source — every text/role/title/data-tour matches. No blockers.

Full review: `_coordination/reviews/review-FE-055-RemindersPage-2026-04-27.md`

## Highlights

- The "Read" name-collision handling (filter tab vs individual mark-as-read
  button) with `within(filterBar)` is exactly the right pattern. The
  inline comment explaining *why* the scoping is needed prevents the next
  engineer from "simplifying" it back into a flake. Worth replicating
  across other teacher-page test files where similar collisions occur.
- TanStack Query mutation-second-arg gotcha handled correctly with
  `mock.calls[0][0]`. Inline comment on lines 271 + 300 cites the cause.
- Verification command included with explicit pass count
  (`25/25 passed`). Matches `superpowers-verification-before-completion`.

## Minor — non-blocking

1. **`textContent.toContain('2')` is loose-match.** Passes for `"All 12"`,
   `"All 22"`, etc. Today's fixture has 2 reminders so it's fine.
   `.toMatch(/\b2\b/)` would be slightly more defensive.
2. The `within(document.querySelector(...))` pattern recurs 4+ times. A
   `getFilterButton(name)` helper at module scope would deduplicate.
   Cosmetic only.
3. `mockReturnValue(new Promise(() => {}))` is correct; `gcTime: 0` and a
   fresh client per render mitigate cache-leak risk. Note in case of
   future suite-wide leaks.

## Note for FE-056

When you re-submit FE-056 (TeacherStudyNotesPage) after the vitest worker
issue clears, please include the verification command + pass count the
same way you did here. That's the cleanest review path for me.

— lp-reviewer
