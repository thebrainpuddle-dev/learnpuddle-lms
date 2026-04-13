# TASK-006: Decompose CourseEditorPage (2,894 lines)

**Priority:** P2 (Maintainability)
**Phase:** 2
**Status:** todo
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

- [ ] No single file exceeds 400 lines
- [ ] All existing functionality preserved
- [ ] TypeScript types properly shared
- [ ] Custom hooks are independently testable
- [ ] No circular dependencies
- [ ] Build succeeds: `npm run build`
