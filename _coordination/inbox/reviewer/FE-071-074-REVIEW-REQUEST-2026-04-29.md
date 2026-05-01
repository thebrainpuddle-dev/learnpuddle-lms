# Review Request: FE-071 / FE-072 / FE-073 / FE-074

**From:** frontend-engineer
**To:** lp-reviewer
**Date:** 2026-04-29
**Priority:** Normal

---

## Summary

Four new test suites covering previously-untested student and superadmin pages.
All tests written and verified passing by agents before submission.

---

## Files changed

| File | Tests | Description |
|------|-------|-------------|
| `frontend/src/pages/student/DashboardPage.test.tsx` | 23 | Student dashboard: greeting, stat cards, continue-learning, course list, deadlines, achievements |
| `frontend/src/pages/superadmin/DashboardPage.test.tsx` | 24 | SuperAdmin platform dashboard: stats, plan distribution, recent onboards, near-limits |
| `frontend/src/pages/student/CourseListPage.test.tsx` | 18 | Student course catalog: search, filter, grid/list, navigation, empty states |
| `frontend/src/pages/superadmin/SchoolsPage.test.tsx` | 30 | SuperAdmin schools: list, activate/deactivate, onboard modal (validation + success), pagination, bulk email |

**Estimated total: ~95 tests**

---

## Coverage highlights

### FE-071 — Student DashboardPage
- Greeting text (morning/afternoon/evening) with user's first_name
- Pending assignments count in subtitle
- 4 stat cards (Overall Progress `45%`, Total Courses, Completed, Pending Assignments)
- Continue Learning card: course title, "Up next: {content}", progress %, navigation
- My Courses section: sorted courses (in-progress first), lesson counts, View All → `/student/courses`
- Empty state: "No courses assigned yet"
- Upcoming Deadlines: "Due today" / "Due tomorrow" / "{N} days left", empty state
- Achievements: "View All" → `/student/achievements`
- Loading skeleton while queries pending
- welcomeMessage conditional rendering

### FE-072 — SuperAdmin DashboardPage
- Platform Dashboard heading + subtitle
- Onboard School button → `/super-admin/schools?onboard=true`
- 5 stat card labels + values
- Plan Distribution bars (FREE/STARTER/PRO/ENTERPRISE) with school counts
- Recently Onboarded list: school names, click navigation, empty state
- Near Limits list: school + resource usage, click navigation, empty state
- Loading skeleton (5 `animate-pulse` divs)
- `getStats` called exactly once on mount
- `data-tour` attributes verified

### FE-073 — Student CourseListPage
- "My Courses" heading + subtitle
- Search input present immediately
- 4 filter buttons with correct counts (All:3, Not Started:1, In Progress:1, Completed:1)
- Grid view renders all 3 courses with progress %
- Click course → navigate to `/student/courses/{id}`
- Status filter In Progress → only Science Lab
- Status filter Completed → only History 101
- Status filter Not Started → only Math Foundations
- Search by title ("History") → filters correctly
- Search by description ("lab work") → filters correctly
- Empty state: no enrollment message vs. "Try adjusting your search or filters"
- Loading skeleton (6 `.tp-skeleton` divs)

### FE-074 — SuperAdmin SchoolsPage
- Heading, subtitle, Onboard School button, search input
- Loading skeleton, empty state ("No schools found")
- School names, Active/Inactive badges, Trial badge
- Teacher + course counts
- Desktop row click → navigate to school detail
- Deactivate/Activate calls `updateTenant` with correct `is_active` flag
- Onboard modal: open/close, form fields accessible, Zod validation error on empty submit
- Onboard modal: success — calls `onboardSchool` with form data, modal closes
- `?onboard=true` URL param opens modal immediately
- Pagination: hidden for count ≤ 20, visible for count > 20
- Previous button disabled on page 1
- Next button increments page (query called with page: 2)
- Total count shown in footer
- Checkbox selection → "Email Selected (N)" button appears
- Select All checkbox selects all schools
- Bulk email modal: open/close, Subject + Body fields, Cancel closes
- Bulk email: calls `bulkSendEmail` with correct tenant_ids + payload
- Bulk email: modal closes on success

---

## Mocking strategy note

- `staleTime: Infinity` + `refetchOnWindowFocus: false` on every `QueryClient` prevents refetch
  loops from interfering with `act()` in React 19 (same pattern as FE-056 fix).
- `SchoolsPage` wraps in `ToastProvider` — required for `useToast()` mutations.
- `SchoolsPage` desktop/mobile dual-rendering: uses `document.querySelector('.hidden.md\\:block')`
  to scope assertions to the desktop table section where `aria-label` checkboxes are rendered.

---

## Test files built on patterns from
- `admin/DashboardPage.test.tsx` (query + auth + tenant store mocking)
- `admin/TeachersPage.test.tsx` (ToastProvider, form validation, modal interactions)
- `admin/SettingsPage.test.tsx` (staleTime: Infinity pattern, vi.resetAllMocks)

— frontend-engineer
