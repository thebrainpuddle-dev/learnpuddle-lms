---
tags: [review, task/FE-002, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-19
author: frontend-engineer
branch: maic-sprint-1-presence-rhythm
files:
  - frontend/src/pages/teacher/ProfilePage.tsx (modified)
---

# Review: FE-002 — ProfilePage migrated to React Hook Form + Zod

## Verdict: APPROVE

## Summary
Straightforward refactor from `useState` → `useZodForm`; follows the existing RHF pattern used elsewhere in the codebase. No `any`, no debug code, no behaviour regressions observable from the diff. Closes the last Phase 2 form-migration gap.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **`subjects[]` / `grades[]` via `setValue` + `watch`** — works, but bypasses RHF's field-level subscription, meaning the whole form re-renders on each toggle. Fine for this page's size (≤ ~20 chips) but if the multi-select grows, switch to `Controller` or `useFieldArray`.

2. **Notifications block still uses a separate `notifSaving` state.** Matches the shared-log note ("Notifications section uses separate `notifSaving` state") so this is intentional — the notifications section is a different endpoint. Worth a one-line comment in the file explaining why it's outside the RHF form.

## Positive Observations
- Uses `profileForm.formState.isSubmitting` instead of bespoke `isSaving`, so the submit button's disabled/loading state is derived correctly.
- Password form also converted to RHF.
- `ProfileSchema` constrains `first_name`, `last_name`, `designation`, `department`, `bio`, `subjects[]`, `grades[]` — all the right fields.
- TypeScript check reported clean per author notes.

## Next Actions
- `status/review` → `status/done`
- Consider a small follow-up to add a `notifSaving` explanation comment; not required.
