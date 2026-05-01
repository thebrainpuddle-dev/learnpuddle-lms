# Review Request: FE-075 / FE-076 / FE-077

**From:** frontend-engineer
**To:** lp-reviewer
**Date:** 2026-04-29
**Priority:** Normal

---

## Summary

Three new test suites for remaining untested student/superadmin pages. All tests written and verified passing by agents.

---

## Files changed

| File | Tests | Description |
|------|-------|-------------|
| `frontend/src/pages/student/ProfilePage.test.tsx` | 22 | Student profile view + edit form |
| `frontend/src/pages/student/AchievementsPage.test.tsx` | 49 | Gamification dashboard (points, streaks, badges) |
| `frontend/src/pages/superadmin/DemoBookingsPage.test.tsx` | 30 | SuperAdmin demo bookings list + create/email modals |

**Total: ~101 tests**

---

## Coverage highlights

### FE-075 — Student ProfilePage (no TanStack Query — uses direct `api.patch`)
- "My Profile" heading + subtitle
- Avatar initials fallback (`"AC"` from Alice Chen)
- Avatar `<img>` rendered when `profile_picture_url` is set
- Student ID display (and "Not assigned" when null)
- Account section: email, role "Student"
- Form pre-fill: First Name input = "Alice", Last Name = "Chen", bio textarea = "I love science!"
- `api.patch('/users/auth/me/', {...})` called with correct payload on form submit
- `setUser` called with response data on success
- Success and error toasts triggered correctly
- All 5 Student Details labels: Student ID, Grade, Section, Parent Email, Enrollment Date
- No QueryClient needed (page uses direct axios, not TanStack Query)

### FE-076 — Student AchievementsPage (49 tests — most comprehensive page)
- Hero Stats: Total Points value, "N badges unlocked" plural/singular
- Hero Stats: Current Streak days + target + "1 day" singular
- Hero Stats: Next Badge card (badge name, "All badges unlocked!" when none locked)
- Points Breakdown: section heading + all 5 item labels + their point values
- Streak Tracker: heading, Target Progress label, %, "X days to target", "Target reached!", 7-day calendar headers (M T W T F S S)
- Badges Grid: section heading, all badge names, "Unlocked" count, locked badge indicator, progress percentages, progress bar widths
- Loading skeleton: `animate-pulse` divs present, content absent while loading
- Error state: error message text, Retry button, calls `refetch` on Retry click
- Query key: `['studentGamification']` verified
- Heading visible in all states (loading/error/empty)

### FE-077 — SuperAdmin DemoBookingsPage
- "Demo Bookings" heading + subtitle
- "+ Add Booking" button, search input, status filter `<select>` with all 4 options
- Loading skeleton (animate-pulse)
- Empty state: "No demo bookings yet" + Cal.com hint
- Booking list: names, emails, formatted dates, Manual/Cal.com source badges, envelope icon buttons
- Status badge CSS classes verified: blue (scheduled), green (completed), slate (cancelled), red (no_show)
- Inline status select `onChange` calls `updateDemoBooking` with new status
- Create Booking modal: opens on button click, all form fields (Name, Email, Company, Phone, Scheduled At, Notes), Zod validation errors on empty/invalid submit, `createDemoBooking` called with correct payload, modal closes on success, modal closes on Cancel
- Send Email modal: opens with correct heading ("Send Email to {name}"), Subject + Body fields, `sendDemoBookingEmail` called with payload, closes on success, closes on Cancel, second booking opens correct modal

---

## Notes for reviewer

- FE-076 has 49 tests because AchievementsPage is a rich gamification page (590 lines). The agent generated high-quality detailed test coverage.
- FE-077 DemoBookingsPage uses inline `<select>` per booking row for status changes — tests use `fireEvent.change` / `userEvent.selectOptions` to simulate this.
- FE-075 ProfilePage uses direct `api.patch` (not TanStack Query), so no `QueryClientProvider` wrapper needed.
- All three files follow the established `staleTime: Infinity + refetchOnWindowFocus: false + retry: false + vi.resetAllMocks()` pattern.

— frontend-engineer
