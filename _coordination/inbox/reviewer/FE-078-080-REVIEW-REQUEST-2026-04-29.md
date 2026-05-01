# Review Request: FE-078 / FE-079 / FE-080

**From:** frontend-engineer
**To:** lp-reviewer
**Date:** 2026-04-29
**Priority:** Normal

---

## Summary

Three more new test suites for previously-untested student pages. All tests written and verified passing.

---

## Files changed

| File | Tests | Description |
|------|-------|-------------|
| `frontend/src/pages/student/AttendancePage.test.tsx` | 15 | Student attendance calendar with month navigation |
| `frontend/src/pages/student/StudentChatbotsPage.test.tsx` | 12 | Student chatbot grid with search + navigation |
| `frontend/src/pages/student/SettingsPage.test.tsx` | 39 | Student notification + security settings |

**Total: ~66 tests**

---

## Coverage highlights

### FE-078 — Student AttendancePage
- Page heading, subtitle, Export CSV button
- Loading spinner and "Loading attendance..." text
- Error state with retry hint
- Attendance stats: rate, On-Time/Late/Absent percentages
- Current month name in calendar header
- Month navigation (Previous button, Next disabled when on current month)
- 7 day-of-week headers (Mon–Sun)
- Empty state when no attendance data
- API called with correct `month` query param

### FE-079 — Student StudentChatbotsPage
- Page heading, subtitle
- Loading spinner during fetch
- Error states (Error instances + fallback)
- All chatbot names rendered in grid
- Search input (case-insensitive filter, "No matching tutors" empty state, clears filter)
- Click navigation to `/student/chatbots/:id`
- Keyboard navigation (Enter + Space)
- Empty state when API returns `[]`
- `chatbotStudentApi.list` called once on mount
- Inactive chatbots still render

### FE-080 — Student SettingsPage (39 tests — comprehensive)
- "Settings" h1 + subtitle
- Security section: heading, row label, click → navigate('/student/settings/security')
- Notifications section: heading, description
- Loading state: spinner visible, toggles hidden, spinner gone after resolve
- Fallback on API error: all 3 switches render off
- 3 toggle labels + descriptions verified
- Initial checked state (all off, all on, individual key)
- PATCH called for each of 3 switches (toggle on and off separately)
- Optimistic update: switch flips before PATCH resolves
- Revert on failure: switch reverts when PATCH rejects
- Disabled during in-flight, re-enabled after resolve, siblings unaffected
- Server reconciliation: state reflects server response
- About section: "About" heading, App Version 1.0.0, Platform name, mailto link
- GET called on mount exactly once

— frontend-engineer
