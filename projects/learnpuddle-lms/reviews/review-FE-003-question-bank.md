---
tags: [review, task/FE-003, verdict/request_changes, reviewer/lp-reviewer]
created: 2026-04-19
author: frontend-engineer
branch: maic-sprint-1-presence-rhythm
files:
  - frontend/src/services/adminQuestionBankService.ts (new)
  - frontend/src/pages/admin/QuestionBankPage.tsx (new)
  - frontend/src/App.tsx (route)
  - frontend/src/components/layout/AdminSidebar.tsx (nav)
---

# Review: FE-003 — Question Bank Management UI

## Verdict: REQUEST_CHANGES

Overall this is strong work: the service layer is typed end-to-end, the modals use RHF + Zod, and the list/detail flow matches the backend contract at `apps/progress/assessment_urls.py` (verified — endpoints exist, all are `@admin_only @tenant_required`). Two issues need addressing before merge: a typed-cast escape hatch and a correctness bug in the form validation that lets empty/invalid choice sets through.

## Critical Issues
None.

## Major Issues

### M1. Validation does not enforce "at least one correct choice" for MCQ/MULTI/TRUE_FALSE
`QuestionSchema` treats `choices` as a plain `z.array(ChoiceSchema).default([])` with no cross-field constraint. A user can save:
- An `MCQ` question with zero correct answers.
- A `MULTI` question with zero correct answers.
- An `MCQ` with fewer than two choices (after removing one).
- A `TRUE_FALSE` whose seeded `is_correct: true` is then toggled off in both rows.

These are silent data-quality bugs — teachers will get unanswerable questions at attempt time. Add a `.superRefine` (or `.refine`) conditional on `question_type`:

```ts
const QuestionSchema = z.object({ /* …current fields… */ })
  .superRefine((data, ctx) => {
    const needs = ['MCQ','MULTI','TRUE_FALSE'].includes(data.question_type);
    if (!needs) return;
    if (data.choices.length < 2) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['choices'],
        message: 'At least 2 choices required.' });
    }
    if (data.choices.some((c) => !c.text.trim())) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['choices'],
        message: 'Choice text cannot be empty.' });
    }
    const correct = data.choices.filter((c) => c.is_correct).length;
    if (correct < 1) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['choices'],
        message: 'Mark at least one correct answer.' });
    }
    if (data.question_type === 'MCQ' && correct > 1) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['choices'],
        message: 'Single-choice questions need exactly one correct answer.' });
    }
  });
```

Also render the top-level `choices` error (currently only per-field errors are shown).

### M2. `as any` escape hatch on the type filter — `QuestionBankPage.tsx:530`
```ts
adminQuestionBankService.listQuestions(bank.id, typeFilter as any || undefined),
```
`typeFilter` is a `string` from an `<select>`. Cast it to the discriminated union properly:

```ts
adminQuestionBankService.listQuestions(
  bank.id,
  (typeFilter as QuestionType) || undefined,
)
```
…or (safer) narrow at assignment time with a type guard. The `any` violates the checklist's "no `any`" rule and the empty-string case currently works only because `'' || undefined` short-circuits — brittle.

## Minor Issues

1. **Two `React.useEffect` blocks with `// eslint-disable-next-line react-hooks/exhaustive-deps`** (L265, L286). The `form` ref is stable; add it to deps and drop the disable, or document why it's intentional. Disabled lint rules tend to stick around and hide real bugs.

2. **TRUE_FALSE seeding effect (L256–266) also fires when opening the modal in edit mode** for a question whose `question_type` already is `TRUE_FALSE`, overwriting the loaded `choices`. Reproduce: open an existing TRUE_FALSE question where the correct answer is "False" — the effect will reset it to `True` correct. Gate the effect on "type actually changed" using `form.formState.dirtyFields.question_type`, or run it only when `!editingQuestion`.

3. **`BankModal` description field accepts `null` from server?** `editingBank.description` is typed as `string` in the service, but if the API ever returns `null` the `defaultValues` would put `null` into a Zod `string().optional()` — runtime validation error on first render. Coerce: `description: editingBank.description ?? ''`.

4. **Duplicate nav entry confusion** — `AdminSidebar.tsx` now has both "Gradebook" and "Assessments" using the same `TableCellsIcon`. Visual ambiguity; pick different icons or combine into one route with tabs.

5. **`deleteMut.mutate` in `ConfirmDialog.onConfirm` doesn't await**, then the target is cleared synchronously. If the delete errors, the toast fires but the UI has already dismissed the dialog — acceptable, but means the user can't retry from the same confirm context. Cosmetic.

## Positive Observations

- End-to-end typing: Zod → RHF → service → backend serializer, no `unknown` cliffs beyond M2.
- `useFieldArray` used correctly for dynamic choices, including single-select logic for MCQ/TRUE_FALSE.
- `CHOICE_TYPES` constant + `needsChoices` derived flag keeps the conditional UI centralised.
- Cache invalidation keys are consistent: both `bankQuestions` and `questionBanks` are invalidated on mutation, so the parent list's `question_count` stays fresh.
- Empty/search/loading states all distinct.
- Good separation: service file is pure, page owns all UI state.
- Backend endpoints verified: `/admin/question-banks/…` all exist with `@admin_only @tenant_required` decorators — no security gap on the API side.

## Next Actions
- Fix M1 (validation) and M2 (`as any`) before merge.
- Minor issues can be squashed into the same fix commit or logged as follow-ups.
- After fixes re-submit for review; expecting APPROVE on next pass.
- Status: keep at `status/in-progress` until M1+M2 resolved.
