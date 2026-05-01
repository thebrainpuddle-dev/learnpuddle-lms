---
tags: [review, task/FE-035, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-25
---

# Review: FE-035 — Follow-up fixes (FE-031/032/033/034 non-blocking items)

## Verdict: APPROVE

## Summary
Six tightly-scoped, single-line follow-ups landing every non-blocking item from
the four most recent verdicts, plus one bonus timer-leak fix that resolves three
flaky tests. Diff stays small, behavior changes match the prior review notes
exactly, and `npx vitest run` reports 660/660 green.

## Changes verified

| # | File | Change | Origin verdict |
|---|------|--------|----------------|
| 1 | `DeadlineAdherenceChart.tsx:78` | `isLoading || isError ? '—' : ...%` on headline stat | FE-034 M1 |
| 2 | `ApprovalTrendsChart.tsx:72,75` | Same `—` guard on stat **and** subtitle now skips `(N total requests)` on error | FE-034 M1 |
| 3 | `QuestionBankPage.tsx:529-533` | Renders `errors.choices.root.message` with `role="alert"` (correct RHF v7 path for FieldArray-level Zod errors) | FE-033 M2 |
| 4 | `QuestionBankPage.test.tsx:590-610` | Replaces `setTimeout(100)` with `waitFor(...)` and asserts the alert text `mcq requires exactly 1 correct choice` is visible *before* asserting the service was not called | FE-033 M1 + M2 |
| 5 | `SettingsPage.tsx:1577-1587` | `navigator.clipboard.writeText().catch(...)` shows a "Copy failed" toast when the Permissions Policy or insecure-context blocks clipboard | FE-032 M2 |
| 6 | `SettingsPage.tsx:1701` | `if (revealToken) return` guard on `createMutation.onSuccess` prevents a rapid double-submit from overwriting the first plaintext token before the admin copies it | FE-032 M1 |
| 7 | `ActivityHeatmap.test.tsx:91-110` | Pin "today" to Wed 2026-04-22 with scoped fake timers + `useRealTimers()` in `finally` | bonus / Saturday flake |

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
None blocking. Two observations for the future, not for this PR:

- **Change #4** asserts the dialog-scoped alert text. Strong. If a second
  `role="alert"` ever lands in the dialog (e.g. for `prompt`), `getByRole('alert')`
  will throw — at that point switch to `findAllByRole('alert')` + a `find`. Not
  needed today.
- **Change #6's** double-submit guard is subtle: if a server returns
  successfully but the network is slow and the user clicks again, the second
  token is created on the server but silently discarded by the client. Today
  the form is hidden after first success (`setShowCreateForm(false)` on the
  prior path) so the path is unreachable; if the modal/form layout ever changes,
  consider also disabling the button while `revealToken` is set.

## Positive Observations

- **The RHF v7 `errors.choices.root.message` choice** is the correct fix.
  FieldArray-level `superRefine` errors with `path: ['choices']` *do* land at
  `errors.choices.root`, not `.message`. The inline comment at the call site
  documents this so the next person doesn't "simplify" it back. Solid.
- **Removing the `setTimeout(100)`** in the QuestionBankPage test is exactly the
  kind of thing that shows up as a 0.1% flake in CI a year later. Replacing
  with a positive DOM assertion (alert visible) closes the gap properly.
- **The ActivityHeatmap timer-leak fix** is the kind of root-cause work I want
  to see more of: the missing `useRealTimers()` was leaking into the *next*
  describe block's `userEvent` and making `CloneTemplateDialog` flaky. Two-bird,
  one-stone — and the `try { ... } finally { vi.useRealTimers() }` pattern
  belongs in the docs as the canonical recipe.
- **Static guards on derived stats** (`isLoading || isError ? '—' : ...`)
  match how the rest of the analytics charts already render. No new pattern,
  no surprise.

## Verification (claimed)
- `npx tsc --noEmit` → 0 errors
- `npx vitest run` → 660/660 passed; the 3 prior failures (QuestionBankPage
  choices, ActivityHeatmap Saturday flake, CloneTemplateDialog timer leak) all
  resolved.

I spot-checked the diff against the four prior verdicts (`review-FE-031` …
`review-FE-034-2026-04-24.md`) and every non-blocking M-item is addressed.
Cleared to merge.

— lp-reviewer
