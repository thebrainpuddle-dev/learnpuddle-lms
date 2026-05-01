# QA Review Request — academics app tests (zero-coverage → 50 tests)

**From:** qa-tester
**To:** reviewer
**Date:** 2026-04-28
**File:** `backend/apps/academics/tests.py` (NEW — 50 tests, 10 classes)

---

## Summary

`apps/academics` had **zero test coverage** — no test file existed at all.
This file creates a comprehensive test suite covering the full REST API surface
for academic structure management.

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestAcademicsAuthGuards` | 5 | 401 unauthenticated; 403 TEACHER; admin gates |
| `TestGradeBandCRUD` | 9 | Create/list/detail/404/patch/delete; duplicate-name 400; delete-with-grades guard |
| `TestGradeCRUD` | 5 | Create/list/filter-by-band/patch/delete |
| `TestSectionCRUD` | 5 | Create/list/filter-by-grade/patch/delete |
| `TestSubjectCRUD` | 6 | Create/duplicate-code 400/list/search/patch/detail |
| `TestTeachingAssignmentCRUD` | 4 | Create/list/filter-by-teacher/delete |
| `TestAcademicsCrossTenantIsolation` | 4 | GET/PATCH/DELETE → 404 + no mutation; list isolation |
| `TestSchoolOverview` | 3 | 200 with keys; nested grade data; teacher 403 |
| `TestSectionDetailViews` | 5 | Students/teachers/courses views; teacher access; 404 |
| `TestPromotionValidation` | 4 | Missing year 400; non-list IDs 400; >5000 IDs 400; preview 200 |

**Total: 50 tests, 10 classes**

Docker run deferred (same `pythonjsonlogger` sandbox blocker as all prior sessions).
Command when Docker available:
```bash
docker compose exec web pytest backend/apps/academics/tests.py -v
# Expected: 50 passed
```

---

## Static Verification (all PASS)

### Imports verified

| Import | Location | Status |
|--------|----------|--------|
| `GradeBand`, `Grade`, `Section`, `Subject`, `TeachingAssignment` | `apps/academics/models.py` | ✅ all 5 classes |
| `GradeBand.objects.create(tenant, name, short_code)` | models.py:6 | ✅ |
| `Grade.objects.create(tenant, grade_band, name, short_code)` | models.py:52 | ✅ |
| `Section.objects.create(tenant, grade, name, academic_year)` | models.py:85 | ✅ |
| `Subject.objects.create(tenant, name, code)` | models.py:122 | ✅ |
| `TeachingAssignment.objects.create(tenant, teacher, subject, academic_year)` | models.py:160 | ✅ |

### URLs verified against admin_urls.py + config/urls.py

Root: `path('academics/', include('apps.academics.admin_urls'))` at `/api/v1/`

| Test URL | admin_urls.py name | Status |
|----------|--------------------|--------|
| `/api/v1/academics/grade-bands/` | `grade_band_list` | ✅ |
| `/api/v1/academics/grade-bands/<uuid>/` | `grade_band_detail` | ✅ |
| `/api/v1/academics/grades/` | `grade_list` | ✅ |
| `/api/v1/academics/grades/<uuid>/` | not named but present | ✅ |
| `/api/v1/academics/sections/` | `section_list` | ✅ |
| `/api/v1/academics/sections/<uuid>/` | `section_detail` | ✅ |
| `/api/v1/academics/sections/<uuid>/students/` | `section_students` | ✅ |
| `/api/v1/academics/sections/<uuid>/teachers/` | `section_teachers` | ✅ |
| `/api/v1/academics/sections/<uuid>/courses/` | `section_courses` | ✅ |
| `/api/v1/academics/subjects/` | `subject_list` | ✅ |
| `/api/v1/academics/subjects/<uuid>/` | not named but present | ✅ |
| `/api/v1/academics/teaching-assignments/` | `ta_list` | ✅ |
| `/api/v1/academics/teaching-assignments/<uuid>/` | `ta_detail` | ✅ |
| `/api/v1/academics/school-overview/` | `school_overview` | ✅ |
| `/api/v1/academics/promotion/preview/` | `promotion_preview` | ✅ |
| `/api/v1/academics/promotion/execute/` | `promotion_execute` | ✅ |

### Key behavior verified

#### Delete guard — GradeBand
`grade_band_detail` checks `band.grades.exists()` before deleting.
`test_delete_grade_band_with_grades_returns_400` creates one Grade under the
band, then DELETE → 400. Error response has `'error'` key. Band row survives. ✅

#### Duplicate uniqueness guards
- `GradeBandSerializer.validate_name` checks `(tenant, name)` → 400 ✅
- `SubjectSerializer.validate_code` checks `(tenant, code)` → 400 ✅
- `TeachingAssignmentCreateSerializer.validate` checks `(tenant, teacher, subject, academic_year)` → 400 ✅

#### Cross-tenant isolation
`get_object_or_404(GradeBand, pk=band_id, tenant=request.tenant)` — another
tenant's `band_id` produces `Http404` → 404. No mutation on PATCH/DELETE.
List filtered by `GradeBand.objects.filter(tenant=request.tenant)`. ✅

#### School overview correctness
`get_promotion_preview` returns `[]` for empty tenant (early exit on
`if not grades: return []`). `promotion_preview` wraps in `total_students` and
`current_academic_year` keys. ✅

#### Promotion validation guards verified against admin_views.py
1. `if not new_academic_year:` → 400, error contains "new_academic_year" ✅
2. `if not isinstance(excluded_ids, list) ...` → 400 ✅
3. `if len(excluded_ids) > 5000 ...` → 400, error contains "5000" ✅

#### TeachingAssignment serializer queryset
`TeachingAssignmentCreateSerializer.__init__` scopes the `teacher` queryset to
`role__in=['TEACHER', 'HOD', 'IB_COORDINATOR']`. Tests use `role='TEACHER'`. ✅

#### Section detail views — @teacher_or_admin
`section_students`, `section_teachers`, `section_courses` all use
`@teacher_or_admin` (not `@admin_only`). Tests verify teachers get 200.
Test `test_school_overview_teacher_cannot_access` verifies `school_overview`
(which uses `@admin_only`) returns 403 for teachers. ✅

---

## Known Gaps (non-blocking)

1. **Grade/Section delete with students guard** — `grade_detail` and
   `section_detail` block deletion when `students` related set is non-empty.
   Testing this requires creating User objects with `grade_fk`/`section_fk`
   fields set; deferred for a future session.

2. **CSV import endpoint** — `section_import_students` (POST with MultiPart)
   and the `@check_tenant_limit('students')` decorator require additional
   billing/plan fixture setup. Deferred.

3. **Student add/transfer** — `section_add_student` and `transfer_student`
   require `grade_fk`/`section_fk` on User and `check_tenant_limit`. Deferred.

4. **TeachingAssignment duplicate validation** — serializer-level 400 when
   the same (teacher, subject, academic_year) combination is created twice is
   not directly tested. Low risk (unique_together DB constraint also guards it).

5. **Attendance endpoints** — `attendance_urls.admin_urlpatterns` is merged
   into `admin_urls.py` but not tested here. Separate test class needed.

---

## Behavioral Contracts Pinned

1. **Unauthenticated → 401** across all academics endpoints.
2. **TEACHER → 403** on all `@admin_only` endpoints.
3. **Duplicate grade band name → 400** (serializer-level validation, not DB).
4. **Delete-with-children guard**: grade band with grades → 400, row survives.
5. **Cross-tenant 404** (not 403) — no enumeration leak.
6. **List endpoints scoped to own tenant** — other tenants' objects not visible.
7. **School overview structure** — `school_name`, `grade_bands`, `academic_year`
   always present, even for empty tenant.
8. **Promotion year guard** — missing `new_academic_year` → 400 before any mutation.
9. **Promotion IDs type guard** — non-list → 400 before any mutation.
10. **Promotion size guard** — >5000 IDs → 400 before any mutation.

— qa-tester
