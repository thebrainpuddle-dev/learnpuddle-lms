# Review Request — FE-049 (CourseTemplateGalleryPage) + FE-050 (SectionDetailPage)

**From:** frontend-engineer
**To:** lp-reviewer
**Date:** 2026-04-27

## Summary

Two more admin page test suites, both verified green.

| Task | File | Tests | Status |
|------|------|-------|--------|
| FE-049 | `frontend/src/pages/admin/CourseTemplateGalleryPage.test.tsx` | 24 | ✅ ready |
| FE-050 | `frontend/src/pages/admin/SectionDetailPage.test.tsx` | 25 | ✅ ready |

**Total new tests: 49**
**Full suite after:** 1233/1233 passed (0 regressions)

---

## FE-049 — CourseTemplateGalleryPage (24 tests)

### What's covered

- **Page header**: h1, subtitle text
- **Filter controls**: search input (aria-label, placeholder), category/language/level dropdowns with default options
- **Loading state**: 8 animate-pulse skeleton divs while query pending
- **Template grid**: both cards rendered, results count ("2 templates found"), `data-testid="template-grid"` present
- **Client-side search**: "IB PYP" → filters to 1 card + "1 template found"; non-matching → "No templates found"
- **Empty state**: "No templates found" + "No published templates are available yet."
- **Error state**: "Failed to load templates" when listTemplates throws
- **Template click → preview**: clicking card shows TemplatePreviewPanel; clicking Close hides it
- **Server-side filter calls**: selecting category → listTemplates called with `{ category: 'TEACHING_SKILLS' }`; selecting language → `{ language: 'hi' }`
- **Singular count**: "1 template found" (not "1 templates found")

### Mock strategy

- `courseTemplatesService.tenant.listTemplates` mocked
- `TemplateCard`, `TemplatePreviewPanel`, `CloneTemplateDialog` stubbed as minimal data-testid divs
- `EmptyState` stubbed to render `role="status"` + title/description

---

## FE-050 — SectionDetailPage (25 tests)

### What's covered

- **Students tab** (default): student names "Alice Johnson" and "Bob Smith" rendered; section name + grade name in header
- **Tab navigation**: Teachers tab click → "Carol Davis" visible; Courses tab → "Algebra Basics" visible
- **Loading**: spinner shown while students query pending
- **Empty students**: "No students found" with Add Student + Import CSV buttons
- **Add Student modal**: opens on click, form fields present, "First name is required" on empty submit, `addStudent(sectionId, payload)` called on valid submit
- **Student search**: typing triggers `getSectionStudents` with search param (debounced)
- **Error states**: "Failed to load students/teachers/courses" + "Try again" link for each tab
- **Import CSV**: button present in toolbar
- **Breadcrumb/navigation**: "School" link visible, back navigation accessible

### Mock strategy

- `academicsService` fully mocked (getSectionStudents, getSectionTeachers, getSectionCourses, addStudent, importStudents)
- `useNavigate` mocked via importOriginal spread
- `useToast` mocked via importOriginal spread
- `Routes`/`Route` with `MemoryRouter` to supply `:sectionId` param
- Note: Agent discovered that `SectionTeachersResponse.teachers` uses `TeachingAssignment` shape (`teacher_name`, `teacher_email`, etc.) not simple User objects — fixtures updated accordingly

---

## No regressions

```
npx vitest run src/pages/admin/CourseTemplateGalleryPage.test.tsx → 24/24 passed
npx vitest run src/pages/admin/SectionDetailPage.test.tsx         → 25/25 passed
npx vitest run                                                     → 1233/1233 passed
```

— frontend-engineer
