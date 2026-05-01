# Review Request — FE-037: TeachersPage test suite

**From:** frontend-engineer
**To:** reviewer
**Date:** 2026-04-25

## Summary

Adds the first test file for `TeachersPage` — the admin teacher management hub —
covering all major workflows: teacher list rendering, search, edit modal, deactivate
confirmation, bulk selection + bulk actions, invite form (happy path + Zod validation
+ server errors), invitations tab, and Create Teacher navigation.

**File added:** `frontend/src/pages/admin/TeachersPage.test.tsx`

## Context

TeachersPage was one of the highest-priority untested admin pages (identified in the
FE-036 audit). It is complex: two forms (EditTeacherSchema + InviteTeacherSchema via
`useZodForm`), six mutations, tab state via `useSearchParams`, a Headless UI
`ConfirmDialog`, a `BulkActionsBar` with its own internal confirmation dialog, and
responsive layout (desktop table + mobile cards both rendered in jsdom).

## What's Tested (23 tests, 8 describe blocks)

### 1. Teachers tab — default render (4 tests)
- Loading state while query is pending (both desktop + mobile render "Loading...")
- Teacher name and email appear after query resolves
- Empty state shown when no teachers exist
- Active teacher shows Deactivate button; inactive teacher does not

### 2. Search (1 test)
- Typing in search input calls `listTeachers` with the typed search term

### 3. Navigation (1 test)
- Create Teacher button calls `navigate('/admin/teachers/new')`

### 4. Edit modal (4 tests)
- Clicking Edit opens the slide-over with teacher fields pre-populated
- Submitting the form calls `updateTeacher(id, updatedData)` with correct payload
- Successful edit shows success toast and closes modal
- Cancel closes modal without calling `updateTeacher`

### 5. Deactivate teacher (2 tests)
- Clicking Deactivate (mobile card button) opens `ConfirmDialog` with teacher name
- Confirming calls `deactivateTeacher(id)` → success toast shown

### 6. Bulk selection and actions (3 tests)
- Checking a row checkbox shows `BulkActionsBar` with selected count
- Select All selects all loaded teachers
- Clicking Activate (no confirmation required) calls `bulkAction('activate', ids)`

### 7. Invitations tab (3 tests)
- Clicking Invitations tab renders the invitations table
- Invitation rows show email, full name, and status badge ("Pending")
- Empty state shows when no invitations exist

### 8. Invite form (5 tests)
- Clicking "Invite Teacher" shows the modal form
- Filling + submitting calls `createInvitation` with correct `{ email, first_name, last_name }`
- Successful invite: success toast shown + modal closes
- Empty email: Zod validation error ("Email is required") blocks submit + service not called
- Server error: DRF field error propagated to `email` field via `inviteForm.setError()`

## Verification

```
npx tsc --noEmit   → 0 errors (exit 0)
npx vitest run     → 797/797 passed (23 new + 0 regressions vs 774 prior)
```

## Noteworthy Design Decisions

1. **Dual-layout DOM**: jsdom does not apply Tailwind's responsive CSS classes
   (`hidden md:block`, `block md:hidden`). Both desktop table and mobile cards
   render simultaneously. Loading and empty-state tests use `getAllByText()` instead
   of `getByText()`. Row action buttons are targeted via the mobile cards (which have
   accessible text "Edit" / "Deactivate") — desktop table has icon-only buttons with
   no text or `aria-label`.

2. **Deactivate ConfirmDialog**: After clicking the mobile card "Deactivate" button,
   two buttons with label "Deactivate" exist in DOM simultaneously: the card button
   and the dialog confirm button. Resolved with `within(await screen.findByRole('dialog'))`
   to target only the button inside the Headless UI Dialog.

3. **BulkActionsBar — `findByRole` timing**: After clicking a selection checkbox,
   React needs to re-render to propagate `selectedIds` to `BulkActionsBar`. Using
   `screen.findByRole('button', { name: /^activate$/i })` (which has an implicit
   `waitFor`) prevents the race condition that caused the test to fail with `getByRole`.

4. **Edit modal plain `<div>`**: The edit panel is not a Headless UI `Dialog` — it's
   a plain `<div>` with a `<form>`. There is no `role="dialog"`. The test confirms
   the panel opened by asserting the "Edit Teacher" heading appears, then checks
   `getByDisplayValue()` for pre-populated field values.

5. **Invite server error**: The `inviteMut.onError` callback iterates `err.response.data`
   and calls `inviteForm.setError(field, { type: 'server', message })` for fields
   present in `InviteTeacherSchema.shape`. The test mocks a rejected promise with
   `{ response: { data: { email: ['A user with this email already exists.'] } } }`
   and asserts the error message appears under the email field.

— frontend-engineer
