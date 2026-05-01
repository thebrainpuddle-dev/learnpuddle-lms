# Review Request: FE-085 / FE-086

**From:** frontend-engineer
**To:** lp-reviewer
**Date:** 2026-04-29
**Priority:** Normal

---

## Summary

Four new test suites covering the remaining AI Classroom and quiz pages. All tests written and verified passing.

---

## Files changed

| File | Tests | Description |
|------|-------|-------------|
| `frontend/src/pages/student/StudentMAICCreatePage.test.tsx` | 8 | AI Classroom creation wizard shell |
| `frontend/src/pages/student/StudentChatPage.test.tsx` | 12 | Student chatbot conversation page |
| `frontend/src/pages/student/MAICBrowsePage.test.tsx` | 14 | AI Classroom browse/search grid |
| `frontend/src/pages/student/QuizPage.test.tsx` | 44 | Full quiz session (honor code → active → results) |

**Total: ~88 tests**

---

## Coverage highlights

### FE-085a — StudentMAICCreatePage (8 tests)
- "Create AI Classroom" heading visible
- Back button navigates to `/student/ai-classroom`
- `StudentGenerationWizard` stubbed (complex wizard, isolated from page-level tests)
- `onComplete` callback navigates to `/student/ai-classroom/<id>` on wizard completion

### FE-085b — StudentChatPage (12 tests)
- Loading spinner during fetch
- Back link renders and navigates correctly
- Chatbot name displayed in header; 404 state handled
- Conversations sidebar renders conversation list
- Selecting a conversation changes active chat
- "New Conversation" button visible and functional
- Sidebar toggle (mobile)
- `ChatbotChat` child stubbed to isolate page logic

### FE-085c — MAICBrowsePage (14 tests)
- "AI Classroom" heading + subtitle
- "Create" button visible
- Tabs (My Classrooms / Shared / Archived)
- Search input filters classroom cards
- Classroom cards render title + description + click → navigate to `/student/ai-classroom/:id`
- Status badges (active / archived) with correct CSS
- Delete mutation called on delete button click
- Empty state: "No classrooms yet" when API returns `[]`
- Loading spinner during fetch

### FE-086 — QuizPage (44 tests — comprehensive)
- **Loading skeleton**: `animate-pulse` divs present while query pending
- **Not found state**: "Quiz not found" when data returns null
- **Honor code gate**: Banner text + "I agree — start quiz" button (plain button, NO checkbox prerequisite)
- **Active quiz**:
  - All questions shown simultaneously (no Next/Previous pagination)
  - Progress bar: 0% before any answer, 25% after one answer in 4-question quiz
  - MCQ: radio-style option buttons; clicking selects the option
  - True/False: two option buttons (True / False)
  - Short answer: textarea input
  - Essay: textarea input
- **ConfirmDialog on submit**:
  - Opens when "Submit Quiz" button clicked
  - `cancelLabel="Keep editing"` (cancel button)
  - `confirmLabel="Submit"` (confirm button)
  - Cancel closes dialog without submitting
- **Submit mutation**:
  - Calls `submitQuiz(assignmentId, { answers: [...] })` with correct payload
  - Success → toast + navigate to results
  - Error → error toast
- **Results view**: Score, correct count, feedback visible after submission

---

## Key discoveries (implementation notes)

- `useParams()` returns `{ assignmentId }` not `quizId` — component uses `assignmentId` throughout
- No honor code checkbox — just a plain "I agree — start quiz" button with informational text
- All questions rendered simultaneously — full question list always visible
- `ConfirmDialog` uses `cancelLabel="Keep editing"` and `confirmLabel="Submit"` (not default labels)

---

## Notes for reviewer

- All 4 files follow the `staleTime: Infinity + refetchOnWindowFocus: false + retry: false + vi.resetAllMocks()` pattern
- `StudentGenerationWizard` and `ChatbotChat` are stubbed via `vi.mock()` — complex child components with their own test files
- `QuizPage.test.tsx` wraps in `ToastProvider` (page calls `useToast()` on submit)

— frontend-engineer
