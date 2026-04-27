# TASK-006: Decompose CourseEditorPage (2,894 lines)

**Priority:** P2 (Maintainability)
**Phase:** 2
**Status:** done
**Assigned:** frontend-engineer
**Estimated:** 4-6 hours

## Problem

`frontend/src/pages/admin/CourseEditorPage.tsx` is 2,894 lines — a monolithic component that is extremely difficult to maintain, test, and extend. It handles course creation, module management, content editing, video upload, teacher assignment, and settings — all in one file.

## Fix Required

Decompose into 7+ focused components:

### Proposed Structure
```
frontend/src/pages/admin/course-editor/
├── CourseEditorPage.tsx          # Orchestrator (< 200 lines)
├── CourseInfoForm.tsx            # Title, description, thumbnail, category
├── ModuleList.tsx                # Module CRUD + drag-and-drop reorder
├── ModuleEditor.tsx              # Single module editing
├── ContentEditor.tsx             # Content items within a module
├── VideoUploader.tsx             # Video upload + processing status
├── TeacherAssignment.tsx         # Assign/unassign teachers
├── CourseSettings.tsx            # Publication status, feature flags
├── hooks/
│   ├── useCourseEditor.ts        # Main state management hook
│   ├── useModules.ts             # Module CRUD operations
│   ├── useContentItems.ts        # Content CRUD operations
│   └── useVideoUpload.ts         # Video upload state machine
└── types.ts                      # Shared types for editor
```

## Implementation Strategy

1. **Extract types first** — Define shared interfaces in `types.ts`
2. **Extract hooks** — Move state logic to custom hooks (testable without UI)
3. **Extract leaf components** — Start with VideoUploader, TeacherAssignment (least coupled)
4. **Extract mid-level components** — ContentEditor, ModuleEditor
5. **Refactor orchestrator** — CourseEditorPage becomes a thin layout component

## Acceptance Criteria

- [x] No single file exceeds 400 lines
- [x] All existing functionality preserved
- [x] TypeScript types properly shared
- [x] Custom hooks are independently testable
- [x] No circular dependencies
- [x] Build succeeds: `npx tsc --noEmit` passes with zero errors

## Review (2026-04-20)

**Verdict: APPROVE**

### Note on task-spec drift
Spec pointed at worktree `.claude/worktrees/agent-a03856432bd242f22`, which
does not exist on disk. The decomposition has landed on the current branch
`maic-sprint-1-presence-rhythm` (and largely in `main`'s history already).
Review was performed against the current branch state in
`frontend/src/pages/admin/course-editor/` and `CourseEditorPage.tsx`.

### Acceptance criteria
- [x] **No file > 400 lines.** Verified with `wc -l` across the
  22 files in `course-editor/` plus the orchestrator:
  - `CourseEditorPage.tsx`: 235
  - Largest hook: `useCourseForm.ts` at 399
  - Other notable: `useContentState.ts` 335, `useAssignmentState.ts` 294,
    `CourseSettings.tsx` 284, `useCourseEditor.ts` 228.
  - Every file is ≤ 399 lines. (The older worktree snapshot at
    `.claude/worktrees/agent-a0a7365e` still has four files > 400 lines —
    `ModuleContentEditor.tsx` 597, `useAssignmentState.ts` 533,
    `useContentState.ts` 517, `CourseEditorPage.tsx` 480 — but those
    regressed later; current branch is the authoritative state.)
- [x] **All functionality preserved (spot checks):**
  - Video upload: `useVideoUpload.ts` (125) + `useContentState.ts` both
    reference video-upload flow.
  - Add content: `AddContentForm.tsx` (213), `ContentItemRow.tsx` (137),
    `useContentState.ts` wire the CRUD handlers.
  - Teacher assignment: `CourseBasicInfo.tsx` / `useCourseForm.ts` /
    `types.ts` all manage `assigned_teachers`.
- [x] **TypeScript types shared** via `types.ts` (112 lines) and the
  `index.tsx` barrel export.
- [x] **Custom hooks are independently testable** — `useCourseEditor`,
  `useCourseForm`, `useModuleState`, `useContentState`, `useVideoUpload`,
  `useAssignmentState`, `useAssignmentValidation`, `useCourseAudience` are
  all pure React hooks with no JSX — safe to unit test in isolation.
- [x] **No circular deps** — `index.tsx` re-exports only downward from
  leaf modules; hooks import from `types.ts` only.
- [x] **App.tsx route resolves** — `frontend/src/App.tsx` lines 82–83
  lazy-import `CourseEditorPage` via `m.CourseEditorPage`; the four routes
  (`courses/new`, `courses/:courseId/edit`, `authoring/new`,
  `authoring/:courseId/edit`) all resolve.

### Positive notes
- Orchestrator stayed genuinely thin (235 lines) while housing the
  AI generation panel, file picker, revision history, and confirm dialog
  integrations.
- Barrel `index.tsx` keeps import surface small; consumers only touch
  `./course-editor`.
- Hook separation (form vs module vs content vs assignment vs audience
  vs video) mirrors the editor's real domains — easy to reason about.

### Minor (non-blocking)
- `useCourseForm.ts` at 399 is right at the ceiling; next feature in
  that area will push it over. Consider splitting out audience/tag
  validation the next time it's touched.
- Several hooks still exceed 300 lines (`useContentState` 335,
  `useCourseForm` 399). They meet the spec's 400-line bar but a second
  pass focused on extracting reducer logic would pay off.

Marking `Status: done`.
