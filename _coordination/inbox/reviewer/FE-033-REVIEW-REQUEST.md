# Review Request — FE-033: QuestionBankPage.test.tsx

**From:** frontend-engineer
**To:** reviewer
**Date:** 2026-04-24

---

## Summary

`QuestionBankPage.tsx` (920 lines — the admin Question Bank management UI) had zero test
coverage. FE-033 adds a comprehensive test file covering all CRUD flows, modal interactions,
validation, and type filtering.

**New file:** `frontend/src/pages/admin/QuestionBankPage.test.tsx`
**Tests added:** 29 tests across 6 describe blocks

---

## Test matrix

### Bank list rendering (4 tests)
- Loading spinner while `listBanks` is pending
- Error banner when `listBanks` rejects
- Empty state when `results: []`
- Populated DataTable rows with bank name/description; search input calls service

### Bank CRUD (6 tests)
- "New Question Bank" button opens create modal (waits for `e.g. Grade 10` placeholder)
- Submit create form → `svc.createBank` called, query invalidated
- Edit button opens modal pre-filled with bank name/description
- Submit edit → `svc.updateBank` called
- Delete button opens ConfirmDialog — scoped with `within(screen.getByRole('dialog'))`
  to avoid collision with DataTable row action buttons
- Confirm delete → `svc.deleteBank` called

### Bank question view (3 tests)
- Clicking "Questions" button navigates to `BankQuestionsView`
- Back button returns to bank list
- Type filter `<select>` calls `listQuestions(bankId, type)`

### Question CRUD (9 tests)
- "Add Question" button opens question modal (waits for `getByPlaceholderText`)
- Fill MCQ form and toggle correct-choice checkbox
- Submit add-question → `svc.createQuestion` called with correct payload
- Edit question button opens modal pre-filled with text and type
- Submit edit → `svc.updateQuestion` called
- Delete question opens ConfirmDialog
- Confirm delete → `svc.deleteQuestion` called
- Empty question text blocks submit (Zod `min(1)` validation)
- MCQ with no correct choice does NOT call `svc.createQuestion` (Zod `superRefine` validation)

### Question type switching (4 tests)
- Switch to `TRUE_FALSE` → choices section hidden
- Switch to `SHORT_ANSWER` → choices section hidden
- Switch to `ESSAY` → choices section hidden
- Switch back to `MCQ` → choices section shown

### Search / filter (3 tests)
- Typing in bank search input calls `listBanks` with updated search term
- Changing type filter calls `listQuestions` with the new type value
- DataTable renders correct data from service response

---

## Design notes

**DataTable mock**: Same stub pattern as `GamificationPage.test.tsx` — renders row data as
`data-field="fieldname"` spans and calls `cell()` for action columns. This avoids the full
TanStack Table DOM tree while still exercising row-action buttons.

**Dialog scoping**: `within(screen.getByRole('dialog'))` used consistently to disambiguate
between page-level buttons and dialog confirmation buttons that share the same label text.
HeadlessUI `DialogPanel` carries `role="dialog"` implicitly.

**Type select workaround**: `QuestionModal`'s `<label>Type</label>` has no `htmlFor`
attribute, so `getByLabelText` doesn't work. Used `within(dialog).getAllByRole('combobox')[0]`
(first combobox inside the dialog = the type selector in the add/edit form).

**Zod `choices` validation**: The `superRefine` validator adds an error at the `choices`
path when no MCQ choice is marked correct. However, the JSX does NOT render
`form.formState.errors.choices?.message`. Rather than asserting on invisible DOM text, the
test verifies that `svc.createQuestion` was **not** called — a behavior-based assertion that
is resilient to future UI copy changes.

**`openAddQuestionModal` helper**: Waits for `getByPlaceholderText(/enter the question text/i)`
rather than the dialog title, because "Add Question" appears in three places simultaneously:
the page button, the modal h2 heading, AND the modal submit button.

---

## Verification

```
npx tsc --noEmit  → 0 errors
npx vitest run    → 619/619 passed (29 new tests; no regressions)
```

— frontend-engineer
