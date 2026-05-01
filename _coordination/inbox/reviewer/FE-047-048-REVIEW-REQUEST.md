# Review Request — FE-047 (GradeDetailPage tests) + FE-048 (SchoolViewPage tests)

**From:** frontend-engineer
**To:** lp-reviewer
**Date:** 2026-04-27

## Summary

Two new admin page test suites for the School academic structure hierarchy (Level 1 overview + Level 2 grade detail).

| Task | File | Tests | Status |
|------|------|-------|--------|
| FE-047 | `frontend/src/pages/admin/GradeDetailPage.test.tsx` | 27 | ✅ ready |
| FE-048 | `frontend/src/pages/admin/SchoolViewPage.test.tsx` | 21 | ✅ ready |

**Total new tests: 48**
**Full suite after:** 1184/1184 passed (0 regressions)

---

## FE-047 — GradeDetailPage (27 tests)

### What's covered

- **Loading state**: animate-pulse skeleton while both queries pending
- **Breadcrumb**: "School" link to /admin/school, grade name span
- **Header**: grade name h1, "{N} sections · {N} students" subtitle, back button navigation
- **Section cards**: renders Section A/B, teacher name (first name or "--" if unassigned), student count
- **Empty state**: "No sections for this grade", "Create First Section" button
- **Add Section modal**: opens on "Add Section" click, "Section Name" field required, academic year pre-filled, `createSection` called with correct payload
- **Edit Section**: Actions dropdown → "Edit" option → "Edit Section" modal with name pre-filled
- **Delete Section**: Actions dropdown → "Delete" → confirm dialog → `deleteSection(id)` called
- **Error state**: "Failed to load sections" + Retry button when sections query throws
- **Grade not found**: when gradeId doesn't match any band
- **Import CSV button**: disabled when sections=[]

### Mock strategy

- `academicsService` fully module-mocked (getSchoolOverview, getSections, createSection, updateSection, deleteSection, importStudents)
- `useNavigate` mocked via `importOriginal` spread
- `useToast` mocked via `importOriginal` spread
- TanStack Query with `retry: false` + `gcTime: 0`
- `Routes`/`Route` used with `MemoryRouter` to supply the `:gradeId` param

---

## FE-048 — SchoolViewPage (21 tests)

### What's covered

- **Loading state**: animate-pulse skeleton while query pending
- **Header**: school name h1, academic year badge, Settings button (aria-label)
- **Grade bands**: band headings, grade count sub-labels
- **Grade cards**: all 3 grades rendered, student count on Grade 5 card
- **Navigation**: grade card → `/admin/school/grade/:id`, settings button → `/admin/settings`
- **Empty state**: "No academic structure configured" + "Configure Academic Structure" CTA navigates to settings
- **Error state**: "Failed to load school data" + "Try Again" retry button

### Mock strategy

- `academicsService.getSchoolOverview` module-mocked
- `useNavigate` mocked via `importOriginal` spread
- TanStack Query with `retry: false`

---

## No regressions

```
npx vitest run src/pages/admin/GradeDetailPage.test.tsx → 27/27 passed
npx vitest run src/pages/admin/SchoolViewPage.test.tsx   → 21/21 passed
npx vitest run                                           → 1184/1184 passed
```

— frontend-engineer
