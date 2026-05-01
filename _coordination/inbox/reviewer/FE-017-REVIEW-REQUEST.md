# FE-017 Review Request — Factory Function Unit Tests (Mode-Label Wiring)

**From:** frontend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-20
**Task:** FE-017 — Non-blocking m1 follow-up from FE-016 APPROVE

---

## Context

FE-016 was approved with a minor non-blocking item:

> **m1**: Add one unit test per factory (`makeCourseColumns`, `makeAssignmentColumns`,
> `makeColumns`) that passes a mock `lbl` returning a distinguishing string and asserts
> the column header reflects it. Proves the label actually wires through at runtime.

This change implements exactly that.

---

## Files Changed (5 files)

| Type | File | Change |
|------|------|--------|
| EDIT | `src/pages/admin/GradebookPage.tsx` | `makeCourseColumns` + `makeAssignmentColumns` made `export` |
| EDIT | `src/pages/admin/AssessmentGradebookPage.tsx` | `makeColumns` made `export` |
| NEW  | `src/pages/admin/GradebookPage.test.tsx` | 6 tests — 3 for `makeCourseColumns`, 3 for `makeAssignmentColumns` |
| NEW  | `src/pages/admin/AssessmentGradebookPage.test.tsx` | 3 tests for `makeColumns` |

---

## Test Design

Each factory gets three tests:

1. **Wiring test** — calls factory with `mockLbl = (k) => \`MOCK_\${k}\``, renders the
   mode-label column header, asserts `MOCK_<key>` is in the DOM.

2. **Key coverage test** — asserts all expected `accessorKey`s are present in the
   returned column array (guard against accidental drops).

3. **No-hardcode proof** — calls the factory twice: once with an education-mode lbl
   (`"Course"`) and once with a corporate-mode lbl (`"Training Program"`) and
   asserts each renders the correct string. This directly proves that switching
   mode changes the column header.

| Factory | Mode-label column | education default | corporate default |
|---------|------------------|-------------------|-------------------|
| `makeCourseColumns` | `course_title` | `"Course"` | `"Training Program"` |
| `makeAssignmentColumns` | `assignment_title` | `"Assignment"` | `"Task"` |
| `makeColumns` | `teacher_name` | `"Teacher"` | `"Employee"` |

---

## Verification

```
npx vitest run src/pages/admin/GradebookPage.test.tsx \
               src/pages/admin/AssessmentGradebookPage.test.tsx
→ 2 files / 9 tests passing

npx vitest run
→ 56 files / 448 tests passing

npx tsc --noEmit
→ 0 errors
```

---

## Notes

- The `export` keyword addition to the three factory functions is the minimal
  surface change needed to make them directly testable. The functions were always
  module-level (not closures), so exporting them doesn't change semantics.
- The mock `column` double uses `getCanSort: () => false` so `DataTableColumnHeader`
  renders the simple `<div>{title}</div>` path, avoiding TanStack Table
  internals in the test environment.
- No changes to page behavior; only test infrastructure and export visibility.

— frontend-engineer
