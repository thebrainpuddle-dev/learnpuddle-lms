# Review Request — FE-038 (CoursesPage test suite)

**From:** frontend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-25

## What was built

`frontend/src/pages/admin/CoursesPage.test.tsx` — first test coverage for the
Admin Courses management page (683 LOC, 0 tests before this PR).

## Why this matters

CoursesPage is used by every school admin on every session. It has the most surface
area of any untested admin page: two view modes (table + Kanban board), full CRUD
(create/edit/delete/duplicate), publish toggle, bulk operations with confirmation,
server-side search + two filters, pagination, and mode-label column headers.

## Test summary (31 tests, 10 describe blocks)

| Describe | # | Key assertions |
|----------|---|----------------|
| page render states | 5 | Loading; empty-state without/with search; 500 error + Retry; 401 session-expired |
| table view — course list | 6 | Titles, Draft/Published/Mandatory badges, "All Teachers" assignment, mode-label `Course`/`Assignment` column headers |
| search and filters | 3 | `api.get` receives `search=`, `is_published=true`, `is_mandatory=true` |
| navigation | 2 | Create → `/admin/courses/new`; Edit icon → `/admin/courses/:id/edit` |
| delete course | 3 | Modal opens; Cancel closes without call; Confirm → `api.delete` + toast |
| publish / unpublish | 3 | SCHOOL_ADMIN sees buttons; Publish fires `api.patch`; HOD role hides buttons |
| duplicate course | 1 | `api.post('/courses/c-1/duplicate/')` + navigate to new course |
| view toggle | 2 | Board → Draft/Published Kanban headings; Table → column headers restored |
| bulk selection + actions | 4 | Checkbox → BulkActionsBar; Select All; Bulk Publish → `api.post('/courses/bulk-action/')`; Bulk Delete → Headless UI dialog |
| pagination | 2 | `data.next` → Next buttons; `data.previous` → Previous buttons |

## Verification

```
npx tsc --noEmit                                       → 0 errors (exit 0)
npx vitest run src/pages/admin/CoursesPage.test.tsx    → 31/31 passed
```

Full suite: 31 new tests green, zero regressions introduced. Pre-existing failures
(`maicDb.quota.test.ts` 27 and `JsonDiffView.test.tsx` hook-timeout) are unaffected
and were present before this work.

## Design decisions worth noting

1. **`api` mock (not service mock)**: CoursesPage calls `api.get/post/patch/delete`
   directly — no service class exists. Mocked `../../config/api` with `vi.mock`.
2. **Bulk button ambiguity**: Row-level icon buttons share accessible name with
   BulkActionsBar text buttons (`title="Publish"` / `title="Delete"` on icon buttons
   vs text "Publish" / "Delete" on bar buttons). Resolved by scoping via
   `screen.getByText('selected').closest('div[class*="fixed"]')` + `within()`.
3. **"Draft" in option vs badge**: `getByText('Draft')` matches both the filter
   `<option>Draft</option>` and the row badge span. Fixed with `getAllByText` +
   `.find(el => el.tagName === 'SPAN' && el.className.includes('rounded-full'))`.
4. **Dual pagination buttons**: Mobile + desktop pagination both render in jsdom
   (CSS display:none/flex not applied). Tests use `getAllByRole(...).length >=1`.
5. `vi.resetAllMocks()` in `beforeEach` per ESLint rule (not `clearAllMocks`).

## File

`frontend/src/pages/admin/CoursesPage.test.tsx` (new file, 355 LOC)

— frontend-engineer
