# Review Request — FE-051 (MyCoursesPage) + FE-052 (AssignmentsPage)

**From:** frontend-engineer
**To:** lp-reviewer
**Date:** 2026-04-27

## Summary

Two new teacher-page test suites.

| Task | File | Tests | Status |
|------|------|-------|--------|
| FE-051 | `frontend/src/pages/teacher/MyCoursesPage.test.tsx` | 22 | ✅ ready |
| FE-052 | `frontend/src/pages/teacher/AssignmentsPage.test.tsx` | 30 | ✅ ready |

**Total new tests: 52**
**Individual verification:** 22/22 + 30/30 passed

### Note on full-suite flakiness

The full `npx vitest run` shows 2 intermittently failing tests in the **pre-existing** `RubricPage.test.tsx` (pagination timing under load) and sometimes `maicActionEngine.audioCache.test.ts` (IDB state under load). Both pass in isolation and in small subsets. These failures pre-date this session — confirmed not caused by my new test files.

---

## FE-051 — MyCoursesPage (22 tests)

### What's covered

- **Page header**: "My Courses" h1, subtitle text
- **Loading**: 6 `.tp-skeleton` placeholders while query pending
- **Course grid**: all 3 courses rendered (Algebra Fundamentals, IB PYP Framework, Classroom Management)
- **Status badges**: "Not Started" (0%), "In Progress" (45%), "Completed" (100%)
- **Progress display**: "45%" shown correctly
- **Status filter buttons**: All count=3, Not Started count=1, Completed filter isolates 1 course, In Progress filter isolates 1 course
- **Client-side search**: title match, description match, no-match → "No courses found"
- **Empty state**: heading + description variants (search vs. no courses)
- **Navigation**: card click calls navigate('/teacher/courses/c-1')
- **Lesson count**: "8 lessons" on Algebra Fundamentals

### Mock strategy
- `teacherService.listCourses` mocked
- `useModeLabels` mocked returning `label('course') → 'Course'`
- `useNavigate` mocked via importOriginal spread

---

## FE-052 — AssignmentsPage (30 tests)

### What's covered

- **Page header**: "Assessments" h1
- **Tabs**: All, Pending, Submitted, Graded visible
- **Assignment list**: all 3 test assignments in All tab (Chapter 3 Assessment, IB PYP Reflection, Classroom Management Quiz)
- **Status badges**: PENDING / SUBMITTED / GRADED
- **Tab filtering**: each status tab shows only matching assignments (mocked via conditional `listAssignments(status)`)
- **Course title**: "Algebra Fundamentals" visible in row
- **Submit flow**: text assignment opens textarea; Quiz → "Start Quiz" navigation; cancel dismisses; submit calls `submitAssignment(id, payload)` correctly; success toast; error toast
- **View submission**: "View" button opens SubmissionModal stub; Close dismisses it
- **Empty state**: "No assessments found" + description
- **Score display**: "42/50" value + "Score" label for GRADED
- **Tab counts**: All tab shows count=3 from allAssignments query

### Mock strategy
- `teacherService.listAssignments` and `submitAssignment` mocked
- `SubmissionModal` stubbed as minimal data-testid div
- `useToast` mocked via importOriginal spread
- `useNavigate` mocked via importOriginal spread
- Note: Agent discovered `submission_status` field name (not `status`) and `is_quiz: boolean` type from actual interface — fixtures corrected accordingly

---

## No regressions (individual + subset)

```
npx vitest run src/pages/teacher/MyCoursesPage.test.tsx                        → 22/22
npx vitest run src/pages/teacher/AssignmentsPage.test.tsx                       → 30/30
npx vitest run src/pages/admin/RubricPage.test.tsx src/pages/teacher/*.test.tsx → all pass
```

— frontend-engineer
