---
tags: [review, task/FE-017, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-21
---

# Review: FE-017 — Factory Function Unit Tests (Mode-Label Wiring)

## Verdict: APPROVE

## Summary

Non-blocking m1 follow-up from FE-016 APPROVE is cleanly addressed. Three
factories (`makeCourseColumns`, `makeAssignmentColumns`, `makeColumns`) are now
exported and covered by 9 unit tests that prove the mode-label prop threads
through to the rendered column header text. Tests pass, tsc is clean.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

### m1 — Dead code in `GradebookPage.test.tsx` (non-blocking)

`GradebookPage.test.tsx` defines a top-level `mockColumn()` helper at lines 24–30
that is never called anywhere in the file — the tests actually instantiate an
inline `fakeColumn` object in `renderHeader()` (lines 55–59) and inside the
no-hardcode-proof tests (lines 88–104). The unused helper also carries
somewhat gnarly type acrobatics (nested `extends never ? never :` conditionals)
that would be awkward to maintain.

**Fix:** Delete the unused `mockColumn()` function. The inline `fakeColumn`
already does the same work, and `AssessmentGradebookPage.test.tsx` uses a clean
`fakeColumn()` helper — moving to the same pattern in `GradebookPage.test.tsx`
(promote the inline object into a shared helper at module scope) would reduce
duplication across the three renderer blocks and the no-hardcode tests.

### m2 — Duplicate inline column doubles (non-blocking)

Inside the "does not hard-code" tests, the column double literal
`{ getCanSort: () => false, getIsSorted: () => false, toggleSorting: vi.fn() }`
is repeated twice per factory (once per mode). Hoisting into `fakeColumn()`
(as already exists in `AssessmentGradebookPage.test.tsx`) would DRY these up.

Neither m1 nor m2 blocks merge — they are cosmetic cleanups only.

## Positive Observations

- **Minimal surface change.** Exporting the factories is the smallest possible
  change — no behavioural changes, no runtime impact, no signature changes.
- **Mode-distinguishing tests are the strongest proof.** The third test for
  each factory (education vs. corporate lbl → different header text) directly
  proves what the m1 comment from FE-016 asked for: that switching mode
  actually changes the header, not just that the label function is called.
- **Key-coverage tests guard against accidental drops.** Asserting each
  expected `accessorKey` is present prevents silent column regressions.
- **AssessmentGradebookPage.test.tsx is the cleaner file** — use it as the
  template when cleaning up m1/m2 in GradebookPage.test.tsx.
- **`getCanSort: () => false` trick is elegant** — avoids dragging in TanStack
  Table internals (row/table/etc.) to render the header.

## Verification Performed

- `npx vitest run src/pages/admin/GradebookPage.test.tsx src/pages/admin/AssessmentGradebookPage.test.tsx`
  → 2 files / 9 tests passing ✅
- `npx tsc --noEmit` → 0 errors ✅
- Confirmed `export function makeCourseColumns`, `export function makeAssignmentColumns`,
  and `export function makeColumns` are present in the production files with
  unchanged bodies (only `export` keyword added, no semantics changed).
- Confirmed `lbl('course')`, `lbl('assignment')`, and `lbl('learner')` are the
  actual keys wired into the production factories — matching the test assertions.

— lp-reviewer
