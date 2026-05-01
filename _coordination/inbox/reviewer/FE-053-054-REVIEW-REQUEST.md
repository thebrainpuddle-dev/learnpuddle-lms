# Review Request — FE-053 (MyClassesPage) + FE-054 (MyCertificationsPage)

**From:** frontend-engineer
**To:** lp-reviewer
**Date:** 2026-04-27

## Summary

Two more teacher-page test suites, both verified green individually and in multi-file regression run.

| Task | File | Tests | Status |
|------|------|-------|--------|
| FE-053 | `frontend/src/pages/teacher/MyClassesPage.test.tsx` | 26 | ✅ ready |
| FE-054 | `frontend/src/pages/teacher/MyCertificationsPage.test.tsx` | 30 | ✅ ready |

**Total new tests: 56**

---

## FE-053 — MyClassesPage (26 tests)

### What's covered

- **Page header**: "My Classes" h1
- **Academic year badge**: shown when `data.academic_year` is set; hidden when blank
- **Loading**: animate-pulse skeleton cards present while query is pending
- **Error**: "Failed to load your classes. Please try again." error div
- **Empty state**: "No teaching assignments" h3 + description; no stats rendered
- **Subject groups**: h2 heading (subject name), subject code monospace badge, department badge (shown/hidden when null), multiple groups rendered
- **Section cards**: grade·section name text, grade_band_name subtitle (optional), student count singular/plural, course count singular/plural
- **Class Teacher badge**: shown for `is_class_teacher: true`; absent for false
- **Navigation**: SectionCard is a `<button>` — click → `navigate('/teacher/my-classes/section/{id}')` for both distinct sections
- **Stats**: "Total Sections" / "Total Section" (singular), "Subjects" / "Subject" (singular); stats hidden when assignments=[]

### Mock strategy
- `academicsService.getMyClasses` mocked via `vi.mock('../../services/academicsService')`
- `useNavigate` mocked via `importOriginal` spread
- `usePageTitle` stubbed

---

## FE-054 — MyCertificationsPage (30 tests)

### What's covered

- **Page header**: "My Certifications & PD" h1, subtitle text
- **Loading**: animate-pulse skeleton elements
- **Error**: "Failed to load certifications" + "Please try refreshing the page."
- **Summary cards** (4): Compliance "75%" (computed from required_met/required_total); "Valid Certifications" with completed count; "Expiring Soon" + "Within 90 days"; "Action Needed" (missing_count + expired). Note: SummaryCard uses CSS `uppercase` class — DOM text is title-case ("Compliance", "Valid Certifications", etc.), not all-caps
- **Required Certifications**: section h2, display_name list, "Valid" status badge, "Not Started" badge
- **Missing / Action Required**: shown when missing.length > 0; cert name in action list; "not_started" reason → "Not yet completed"; "expired" reason → "Certificate has expired, renewal required"; section hidden when missing=[]
- **All Certifications list**: section h2, `certification_type_display` names, provider, "Expired" status badge
- **Expand/collapse**: click cert `<button>` → expands to show "Completed"/"Expires" labels, cert URL link (`href` assertion), notes; click again collapses
- **Empty certifications**: "No certifications recorded yet." + "Contact your admin to add your PD records."

### Mock strategy
- `api.get` mocked via `vi.mock('../../config/api', () => ({ default: { get: vi.fn() } }))` — MyCertificationsPage calls `api.get('/teacher/certifications/')` directly, not via a service module
- `usePageTitle` stubbed
- No `useNavigate` needed (page has no navigation)

---

## Regression check

```
npx vitest run src/pages/teacher/MyClassesPage.test.tsx                                                → 26/26 passed
npx vitest run src/pages/teacher/MyCertificationsPage.test.tsx                                         → 30/30 passed
npx vitest run src/pages/teacher/MyClassesPage.test.tsx src/pages/teacher/MyCertificationsPage.test.tsx src/pages/teacher/MyCoursesPage.test.tsx src/pages/teacher/AssignmentsPage.test.tsx → 108/108 passed
```

— frontend-engineer
