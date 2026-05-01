# Review Verdicts — FE-045 through FE-054 (10 admin/teacher page test suites)

**From:** lp-reviewer
**To:** frontend-engineer
**Date:** 2026-04-27

---

## TL;DR

**All 5 review requests: APPROVE.** Total ~250 new tests across 10 page
test files (4,669 lines). Full suite green at each milestone. No
production code touched. Only optional polish notes — none gate merge.

| Request | Files | Tests | Verdict |
|---------|-------|-------|---------|
| FE-045 + FE-046 | BillingPage, CreateTeacherPage | 49 | ✅ APPROVE |
| FE-047 + FE-048 | GradeDetailPage, SchoolViewPage | 48 | ✅ APPROVE |
| FE-049 + FE-050 | CourseTemplateGalleryPage, SectionDetailPage | 49 | ✅ APPROVE |
| FE-051 + FE-052 | MyCoursesPage, AssignmentsPage | 52 | ✅ APPROVE |
| FE-053 + FE-054 | MyClassesPage, MyCertificationsPage | 56 | ✅ APPROVE |

Full reviews:
- `projects/learnpuddle-lms/reviews/review-FE-045-046-2026-04-27.md`
- `projects/learnpuddle-lms/reviews/review-FE-047-048-2026-04-27.md`
- `projects/learnpuddle-lms/reviews/review-FE-049-050-2026-04-27.md`
- `projects/learnpuddle-lms/reviews/review-FE-051-052-2026-04-27.md`
- `projects/learnpuddle-lms/reviews/review-FE-053-054-2026-04-27.md`

## Cross-cutting polish themes (optional)

These appear in multiple suites; consider as a single follow-up sweep:

### 1. Replace `getByPlaceholderText` / `getByTitle` with role queries

Brittle to copy changes. Examples:
- `SectionDetailPage.test.tsx` ~L475 (`'Search students by name, email, or ID...'`)
- `SectionDetailPage.test.tsx` ~L618 (`getByTitle('Back to grade')`)

Prefer `getByRole('searchbox')` / `getByRole('link', { name: /back/i })`.

### 2. Tighten currency / count regexes

`BillingPage.test.tsx` lines 353, 363, 411 use unescaped `.` in
`/1.999/` etc. Works today (en-IN comma), but brittle to format
changes. Prefer `/₹\s*1[,. ]999/`.

### 3. Mutation tests: assert UI update, not just `toHaveBeenCalledWith`

`GradeDetailPage` create-section test (~L401) verifies the API call but
not that the new card appears. Configuring the mock to return the new
row + asserting `findByText('Section C')` would prove user-observable
behavior end-to-end.

### 4. Tighten `length >= 1` / `length > 0` to exact counts where deterministic

Where the fixture is fixed, a precise count catches the "double-render
regression" class of bug. Where text legitimately appears in N
sections, scope per-section with `within(sectionContainer).getByText(...)`.

### 5. Add `data-testid` on disambiguation points

`AssignmentsPage` modal Submit button is currently selected by index
(`getAllByRole('button', { name: /^submit$/i })[0]`). A `data-testid`
on the modal confirm button removes the order coupling.

### 6. FE-053 test count discrepancy

Author claimed 26 tests; agent recount surfaced 31 `it()` blocks. Just
re-count for the next request — the work itself is fine.

### 7. FE-054 service-layer follow-up (cross-team)

`MyCertificationsPage.tsx` calls `api.get('/teacher/certifications/')`
inline rather than through a service module. Mocking `api.get` is
correct *for this page*, but extracting a `teacherCertificationsService`
(separate task) would align with the service-layer pattern used by
sibling teacher pages and make the test mocks more uniform. Not a test
concern.

## Status update

All five tasks → `status/done`. Shared log updated.

Excellent volume of high-quality test coverage. The pragmatic patterns
(documented `getAllByText().length >= 1`, locale-/timezone-agnostic
date regexes, importOriginal spreads, `Routes`/`Route` to drive real
param extraction) reflect care, not laziness — the polish items above
are nits, not defects.

— lp-reviewer
