# Review Request — FE-040 (StudentsPage test suite)

**From:** frontend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-26

## What was built

`frontend/src/pages/admin/StudentsPage.test.tsx` — first test coverage for the
Admin Students management page, one of the most feature-dense admin pages in the
codebase.

## Why this matters

StudentsPage is used by every school admin to enroll students, manage accounts,
track invitations, and run bulk actions. It had zero test coverage despite
implementing 3 Zod schemas (CreateStudentSchema, EditStudentSchema,
InviteStudentSchema), 3 modals (create/edit/invite), 2 tabs (Students/Invitations),
a dual desktop+mobile responsive layout, BulkActionsBar with
Activate/Deactivate/Delete, a ConfirmDialog for deletes, CSV import, and a
tenant usage quota display.

## Test summary (51 tests, 13 describe blocks)

| Describe | # | Key assertions |
|----------|---|----------------|
| loading state | 1 | Loading text while query pending |
| page header | 3 | "Students" h1; Add Student button; CSV Import button |
| student table | 8 | Names; emails; student_id / dash fallback; grade badge; active Yes/No; empty state; result count |
| tab navigation | 4 | Students/Invitations tabs; default=Students; switch shows Invite Student; hides Add Student |
| search | 2 | Input renders; type → re-fetch with `search` param |
| filters | 3 | Filters button; toggle reveals grade/section dropdowns; grade select → re-fetch with `grade_level` |
| create student modal | 6 | Opens; fields present; Cancel closes; empty submit → Zod validation errors; success → service + toast + closed; server error → error toast |
| edit student modal | 4 | Pencil opens; pre-populates first_name; Cancel closes; Save → updateStudent + success toast |
| delete student | 3 | XCircle opens ConfirmDialog; within(dialog) confirm → deleteStudent; Cancel → no delete |
| bulk selection | 4 | Select All checkbox; per-row checkbox; one selected → "selected" text; Select All → count badge |
| bulk actions | 3 | Activate → bulkAction('activate'); success toast; Deactivate → bulkAction('deactivate') |
| invitations tab | 8 | Emails; status badges; invited_by name; empty message; Invite modal opens/closes; successful invite → toast; missing email → validation error |
| usage quota | 1 | Shows "12/100 used" when tenant provides quota |

## Verification

```
npx tsc --noEmit                                          → 0 errors (exit 0)
npx vitest run src/pages/admin/StudentsPage.test.tsx     → 51/51 passed
npx vitest run                                            → 966/966 passed (zero regressions)
```

## Design decisions worth noting

1. **Dual desktop+mobile rendering**: jsdom does not process Tailwind CSS, so
   both the `hidden md:block` desktop table and the `md:hidden` mobile card
   layout render simultaneously. Tests use `getAllByText(...).length >= 1` for
   multiply-rendered content and a `getStudentTableRow()` helper that targets
   the desktop-table `<td>` (first in DOM order via `getAllByText(name)[0]`) and
   traverses to `closest('tr')`.

2. **ConfirmDialog "Remove" ambiguity**: After clicking the row's XCircle button
   (accessible name "Remove"), the ConfirmDialog opens with its own "Remove"
   confirm button. Both match `/^Remove$/i`. Fixed by waiting for
   `getByRole('dialog')` and scoping the confirm button to `within(dialog)`.

3. **BulkActionsBar split DOM nodes**: BulkActionsBar renders the selection
   count as `<span>{selectedCount}</span>` followed by `<span>selected</span>`
   as separate elements. `findByText(/2 selected/i)` cannot match across sibling
   elements. Tests assert `getByText('selected')` + `getAllByText('2').length >= 1`
   separately.

4. **Activate/Deactivate regex ambiguity**: `/Activate/i` is a substring of
   "Deactivate". BulkActionsBar exposes both actions. Tests use exact match
   `/^Activate$/i` and `/^Deactivate$/i` to prevent substring collision.

5. **Filter selects are properly associated** (unlike AnalyticsPage): The
   grade/section `<select>` elements have matching `htmlFor`/`id` pairs, so
   `getByLabelText(/Grade Level/i)` works correctly. No index workaround needed.

6. **`retryDelay: 0` in QueryClient**: StudentsPage does not override `retry`
   at the component level, so `retry: false` in the test QueryClient is
   sufficient. Included `retryDelay: 0` defensively (same pattern as FE-039).

## File

`frontend/src/pages/admin/StudentsPage.test.tsx` (new file, ~360 LOC)

— frontend-engineer
