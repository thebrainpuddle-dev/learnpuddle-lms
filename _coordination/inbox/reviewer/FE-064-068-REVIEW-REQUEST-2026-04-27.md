# Review Request — FE-064 through FE-068 (5 page test suites)

**From:** frontend-engineer
**To:** reviewer
**Date:** 2026-04-27
**Files:** 5 new test files for previously untested admin/teacher pages

---

## Summary

5 new test files totalling 86 tests across the ReportBuilderEditorPage,
ReportBuilderDetailPage, MAICLibraryPage, QuizPlayerPage, and ChatbotBuilderPage.
No production code changed — only new test files added.

**Verification command:**
```bash
cd frontend && npx vitest run \
  src/pages/admin/ReportBuilderEditorPage.test.tsx \
  src/pages/admin/ReportBuilderDetailPage.test.tsx \
  src/pages/teacher/MAICLibraryPage.test.tsx \
  src/pages/teacher/QuizPlayerPage.test.tsx \
  src/pages/teacher/ChatbotBuilderPage.test.tsx \
  --reporter=verbose
```

**Result: 86/86 passed**

---

## FE-064 — ReportBuilderEditorPage.test.tsx (14 tests)

Tests for the Admin Report Builder create/edit form.

**Coverage:**
- Create mode: "New report" heading, Basics section header
- Name input renders with placeholder; description textarea; data source select with schema options
- Zod validation: "Name is required" shown on empty submit
- Back button (ArrowLeft) and Cancel button navigate to `/admin/reports/builder`
- `createDefinition` called with correct name on valid submit
- On success, navigates to `/admin/reports/builder/:id`
- Edit mode: loading state ("Loading report…", data-testid="editor-loading")
- Edit mode: "Edit report" heading after definition loads
- Edit mode: name input hydrated with existing definition name
- Edit mode: `updateDefinition` called (not create) on submit

**Mocking strategy:**
- `reportBuilderService` (getDefinition, createDefinition, updateDefinition) mocked
- `useReportBuilderStore` → static schema with 2 data sources
- `FilterBuilder`, `GroupByChips`, `AggregateBuilder` → stubs
- `useToast` → stub via `vi.mock('../../components/common/Toast')`
- `useNavigate` mocked via importOriginal spread
- Route params via `MemoryRouter initialEntries` + `Routes`/`Route`

---

## FE-065 — ReportBuilderDetailPage.test.tsx (21 tests)

Tests for the Admin Report Builder detail page (4 tabs: Overview/Preview/History/Schedules).

**Coverage:**
- Loading state (data-testid="detail-loading")
- Error state ("Report not found or you don't have access.")
- Header: report name (h1), data source badge, Edit/Run now/Export CSV buttons
- Back button navigates to `/admin/reports/builder`
- Edit button navigates to `/admin/reports/builder/:id/edit`
- Overview tab (default): description text, "None" for empty filters/group-by/aggregates
- Overview tab: filter code block rendered when `filters_json` present
- Overview tab: aggregate code rendered when `aggregates_json` present
- Preview tab: "Click Run now to preview results." prompt (textContent check)
- Preview tab: Run now button calls `runDefinition`
- Schedules tab: empty state "No schedules yet."
- Schedules tab: New schedule button visible
- Schedules tab: schedule cadence/time rendered (weekly, at 8:00 UTC)
- Schedules tab: recipient count rendered ("2 recipients")
- Schedules tab: delete button opens ConfirmDialog
- Schedules tab: confirming delete calls `deleteSchedule('def-1', 'sch-1')`
- Schedules tab: enable toggle calls `updateSchedule` with `{ enabled: false }`

**Mocking strategy:**
- `reportBuilderService` (getDefinition, listRuns, listSchedules, runDefinition, deleteSchedule, updateSchedule) mocked
- `PreviewTable`, `RunHistoryTable`, `ScheduleForm` → stubs
- `ConfirmDialog` → stub with Confirm/Cancel buttons
- `useToast` stubbed; `useNavigate` via importOriginal; route params via MemoryRouter
- Tab switching via real @headlessui/react TabGroup + `userEvent.click(tab)`

**Note:** Preview tab text "Click **Run now** to preview results." is split by a `<strong>` element. Test asserts against `previewPanel.textContent` directly.

---

## FE-066 — MAICLibraryPage.test.tsx (16 tests)

Tests for the Teacher AI Classroom library page.

**Coverage:**
- Loading spinner (animate-spin class)
- "AI Classroom" heading
- Empty state ("No classrooms yet", "Create your first AI Classroom")
- Grid: classroom title, status badge (READY, DRAFT), description, scene count, minutes
- New Classroom button navigates to `/teacher/ai-classroom/new`
- Card click navigates to `/teacher/ai-classroom/:id`
- Status filter select: All/Draft/Ready/Archived options
- Search input placeholder "Search classrooms..."
- Delete button opens ConfirmDialog ("Delete Classroom" title)
- Confirming delete calls `deleteClassroom('cls-1')`
- Assign button opens SectionAssignModal ("Assign Sections" h3 heading)

**Mocking strategy:**
- `maicApi` (listClassrooms, deleteClassroom, updateClassroom) and `chatbotApi` (mySections) mocked via `vi.mock('../../services/openmaicService')`
- `ConfirmDialog` → stub with Confirm/Cancel buttons
- `useNavigate` via importOriginal; `usePageTitle` stubbed

---

## FE-067 — QuizPlayerPage.test.tsx (16 tests)

Tests for the Teacher Quiz Player page.

**Coverage:**
- Bootstrapping state: Loading spinner shown while `startAttempt` pending
- No questions state: "No questions available." (startAttempt resolves with empty questions, store.start no-op)
- Live quiz: question prompt (data-testid="quiz-prompt"), "Single Choice" type label
- Live quiz: MCQ choices (Nucleus, Mitochondria, Ribosome) rendered
- Live quiz: question counter "Question 1 of 1" and "Question 2 of 2"
- Live quiz: Previous button disabled on first question
- Live quiz: Submit Quiz button shown on last question; Next button shown otherwise
- MCQ choice click calls `store.setAnswer('q1', 'c2')`
- Submit Quiz button calls `submitAttempt`
- ResultView: "You passed!" heading when `passed=true`
- ResultView: "Not quite there" when `passed=false`
- ResultView: score display "(80%)"
- ResultView: Done button calls `store.clear()` and navigates to `/teacher/assignments`

**Mocking strategy:**
- `assessmentService` (startAttempt, submitAttempt) mocked
- `useQuizAttemptStore` → dynamic `mockStore` object mutated per test; "reuse" path triggered by pre-populating `attemptId`, `contentId`, `questions` matching route `:contentId`
- `useToast`, `Loading` → partial mock of `../../components/common`
- `useNavigate` via importOriginal; route params via MemoryRouter + Routes + Route

---

## FE-068 — ChatbotBuilderPage.test.tsx (19 tests)

Tests for the Teacher AI Tutor (Chatbot) Builder page.

**Coverage:**
- Create mode: "Create Tutor" heading, name input, welcome message textarea
- Create mode: "Save the tutor first to start adding sources" placeholder (no KnowledgeUploader)
- Create mode: no Test Chat button before first save
- Create mode: validation error when name empty (no API call)
- Create mode: `chatbotApi.create` called with correct name on Save
- Create mode: navigates to `/teacher/chatbots/:id` (replace:true) after successful create
- Create mode: Back to Tutors and Cancel buttons navigate to `/teacher/chatbots`
- Create mode: section picker renders grade/section buttons when sections available
- Create mode: "No sections selected" warning shown when sections available but none selected
- Edit mode: loading spinner while `chatbotApi.detail` loads
- Edit mode: "Edit Tutor" heading after load
- Edit mode: name input hydrated with chatbot name
- Edit mode: welcome message textarea hydrated
- Edit mode: KnowledgeUploader rendered (chatbotId known)
- Edit mode: Test Chat button shown (chatbotId set from params)
- Edit mode: `chatbotApi.update` called (not create) on Save

**Mocking strategy:**
- `chatbotApi` (mySections, detail, create, update) mocked via `vi.mock('../../services/openmaicService')`
- `GuardrailConfig`, `KnowledgeUploader`, `ChatbotChat` → stubs
- `useToast` via partial mock of `../../components/common`
- `useNavigate` via importOriginal; route params via MemoryRouter + Routes + Route

---

## Cross-cutting quality notes

- All tests use `importOriginal` spread for `useNavigate` mock
- `makeClient()` helper creates fresh `QueryClient` per test (`gcTime: 0, retry: false`)
- Tab switching tests use real `@headlessui/react` TabGroup + `userEvent.click(tab)` so actual
  tab panel mounting/unmounting behavior is exercised
- `QuizPlayerPage` uses a mutable `mockStore` object pattern (pre-populated for "reuse" path)
  rather than mocking `startAttempt` resolution — faster and avoids async bootstrapping noise
- `ReportBuilderDetailPage` Preview tab assertion uses `panel.textContent` to handle text
  split across `<strong>Run now</strong>`

— frontend-engineer
