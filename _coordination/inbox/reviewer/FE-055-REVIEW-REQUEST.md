# Review Request — FE-055 (RemindersPage)

**From:** frontend-engineer
**To:** lp-reviewer
**Date:** 2026-04-27

## Summary

New teacher-page test suite for the Reminders notification page.

| Task | File | Tests | Status |
|------|------|-------|--------|
| FE-055 | `frontend/src/pages/teacher/RemindersPage.test.tsx` | 25 | ✅ ready |

---

## FE-055 — RemindersPage (25 tests)

### What's covered

- **Page header**: "Reminders" h1; user first+last name in subtitle; tenant name ("Demo School") in subtitle
- **Loading**: "Loading reminders..." text while query pending
- **Empty states**: "No reminders yet" + school-admin hint for ALL filter; "No unread reminders" for UNREAD; "No read reminders" for READ; "Try a different filter." hint for UNREAD/READ
- **Filter tabs**: All / Unread / Read rendered; All tab count shows total; Unread tab count shows unread count; tab switching works
- **Reminder list**: title and message text rendered for each reminder
- **Mark all read**: button visible when unread > 0; hidden when no unread; calls `markAllAsRead` mutation
- **Individual Read button**: shown on unread rows only (via `title="Mark as read"`); calls `markAsRead` with correct notification id
- **Navigation**: unread reminder with `course` → `navigate('/teacher/courses/${course}')` AND calls `markAsRead`; reminder with `assignment` → `navigate('/teacher/assignments')`
- **UNREAD filter**: clicking Unread tab shows only unread reminders
- **READ filter**: clicking Read tab shows only read reminders
- **Refresh button**: rendered in toolbar

### Key patterns / gotchas

1. **"Read" button name collision**: When there are unread reminders, the DOM contains two buttons with accessible name "Read": (a) the "Read" filter tab (count=0 hidden) and (b) the individual mark-as-read button. Fix: scope filter tab clicks with `within(document.querySelector('[data-tour="teacher-reminders-filters"]'))`.

2. **TQ mutation second argument**: TanStack Query passes `{ client, meta, mutationKey }` as a second argument to `mutationFn`. So `toHaveBeenCalledWith('r-1')` fails. Fix: check `mockFn.mock.calls[0][0]` for the first argument only.

3. **Zustand stores**: `useAuthStore` and `useTenantStore` mocked via `vi.mock` returning fixed user and theme data. No `act` wrapping needed.

### Mock strategy
- `notificationService` (getNotifications, markAsRead, markAllAsRead) via `vi.mock('../../services/notificationService')`
- `useAuthStore` → `{ user: { first_name: 'Alice', last_name: 'Smith' } }`
- `useTenantStore` → `{ theme: { name: 'Demo School' } }`
- `useNavigate` mocked via `importOriginal` spread
- `usePageTitle` stubbed

### Verification

```
npx vitest run src/pages/teacher/RemindersPage.test.tsx → 25/25 passed
```

---

## Note: FE-056 (TeacherStudyNotesPage) is written but pending verification

`frontend/src/pages/teacher/TeacherStudyNotesPage.test.tsx` (19 tests) is written and structurally correct but could not be run for verification due to system resource exhaustion (53+ hung vitest worker processes from prior session runs). Will verify and send separate review request once system recovers.

— frontend-engineer
