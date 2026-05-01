# Frontend Review Request — FE-025, FE-026, FE-027

**From:** frontend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-23
**Priority:** Non-blocking follow-ups from FE-022/023/024 verdicts

---

## Summary

Three non-blocking follow-ups from the 2026-04-23 review verdicts, bundled into one
review request. All three are complete and clean.

---

## FE-025 — `ReminderPayload` discriminated union (#2 + #3)

**Files changed:**
- `frontend/src/services/adminRemindersService.ts`
- `frontend/src/components/reminders/ManualSendSection.tsx`

**What changed:**

1. `reminder_type: string` replaced with a `ReminderType` string-literal union
   (`'COURSE_DEADLINE' | 'ASSIGNMENT_DUE' | 'CUSTOM'`) matching the three values
   the backend `ChoiceField` accepts.

2. `ReminderPayload` is now a discriminated union:
   - `AssignmentDuePayload`: `reminder_type === 'ASSIGNMENT_DUE'` → `assignment_id: string` (required)
   - `NonAssignmentPayload`: all other types → `assignment_id?: never` (prohibited)

3. `ReminderCampaign.reminder_type` upgraded from `string` to `ReminderType`.

4. `ManualSendSection` updated as a consequence:
   - Added `assignmentId` state + assignment picker UI (appears when
     `ASSIGNMENT_DUE` is selected, queries `/reports/assignments/`).
   - Replaced the inline object literals in `previewMutation` and `sendMutation`
     with a single typed `reminderPayload` variable that satisfies the union.
   - Added `isPayloadValid` guard — send/preview buttons disabled and toast-guarded
     when `ASSIGNMENT_DUE` is selected but no assignment has been chosen.
   - `onError` callbacks changed from `error: any` → `error: unknown` with explicit
     cast (bonus `any` sweep on this file).

**Why no test for ManualSendSection:**
The assignment picker is a small UI addition; `ManualSendSection` has no test
file and adding one is out of scope here. The discriminated union itself is
verified by `tsc --noEmit`.

---

## FE-026 — Drop unused `@typescript-eslint/eslint-plugin` + sweep `any` in `ReportDrillDown` (#4 + #5)

**Files changed:**
- `frontend/package.json`
- `frontend/src/components/analytics/ReportDrillDown.tsx`

**What changed:**

1. `@typescript-eslint/eslint-plugin` removed from `devDependencies`. The plugin
   was declared but never registered in `eslint.config.js` (no `plugins:` entry),
   so removing it has zero effect on lint behaviour.

   Note: 45 pre-existing lint errors referencing `react-hooks/exhaustive-deps` and
   `@typescript-eslint/*` rules remain — these come from `// eslint-disable-next-line`
   comments in source files for rules that were never configured in the flat config.
   These errors pre-date FE-026 (they appeared when FE-023 switched the lint command
   from `eslint src --ext .ts,.tsx` to `eslint src/`). They are not caused by or
   worsened by removing the plugin.

2. In `ReportDrillDown.tsx`:
   - `onError: (error: any)` → `onError: (error: unknown)` with typed cast.
   - `rows.map((r: any) => ...)` → `rows: (CourseProgressRow | AssignmentStatusRow)[]`
     with proper union typing; `completed_at`/`submitted_at` accessed via `'completed_at' in r`
     discriminant instead of the loose `r.completed_at || r.submitted_at` cast.
   - Imported `CourseProgressRow` and `AssignmentStatusRow` from `adminReportsService`.

---

## FE-027 — Focused `ChatPanel.test.tsx` (#1)

**Files changed:**
- `frontend/src/components/maic/ChatPanel.test.tsx` (new file)

**What changed:**

7 new tests covering the clear-chat confirm path (production-critical per reviewer):

| Test | Behaviour |
|------|-----------|
| `does NOT render the "Clear chat" button when there are no messages` | Button visibility guard |
| `renders the "Clear chat" button when messages are present` | Button appears with messages |
| `opens the ConfirmDialog without clearing messages when "Clear chat" is clicked` | Dialog opens; no premature wipe |
| `closes the dialog and preserves messages when "Keep messages" is clicked` | Cancel path: messages intact |
| `clears store, sessionStorage, and IndexedDB when the confirm button is clicked` | Confirm path: full wipe |
| `"Clear chat" button disappears from the toolbar after messages are wiped` | UI re-syncs after clear |
| `handles a no-op gracefully when "Clear chat" is called on an already-empty store` | Guard clause verified |

**Mocking strategy:**
- `maicDb.updateClassroomChat` → vi.fn() (avoids IndexedDB setup)
- `maicChatSession.{hydrateChatFromSession,persistChatToSession}` → vi.fn() (spy on clear calls)
- `maicSSE.streamMAIC` → vi.fn() (no real SSE needed for clear tests)
- `useSpeechInput` → stub (speech not relevant to clear path)
- `PromptInput`, `ConversationContainer`, `StreamMarkdown`, `AgentAvatar`, `ChainOfThought`, `CodeBlock` → minimal stubs

**Test pattern note:** Mount effects call `persistChatToSession` when messages > 0,
so each test that needs to assert "no call from button click" does `.mockClear()` after
the initial `waitFor` settle. This is the correct pattern for distinguishing mount-time
effects from user-interaction side-effects.

---

## Verification

```
npm test       — 555 passed (7 new), 2 pre-existing failures (CourseEditorPage hash-scroll, aiCourseGenerator stack overflow)
tsc --noEmit   — 0 errors
npm run lint   — 45 pre-existing errors (unchanged from FE-023 baseline), 0 new errors
```

No git operations performed. All files left unstaged.

— frontend-engineer
