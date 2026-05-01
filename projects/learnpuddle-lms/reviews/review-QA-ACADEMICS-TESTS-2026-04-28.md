---
tags: [review, task/QA-ACADEMICS-TESTS, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-28
---

# Review: QA-ACADEMICS-TESTS — academics app coverage from zero → 50 tests

## Verdict: APPROVE

## Summary
Comprehensive net-new test suite for the previously untested `apps/academics` app. 50 tests across 10 classes covering auth/role guards, CRUD across all five academics models, cross-tenant isolation, school overview, section detail views, and promotion validation. Tests are behavior-focused (HTTP-level), pin tenant isolation properly (404 not 403), and the author's static verification matches the codebase. Gaps are documented and reasonable.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **`test_promotion_with_non_list_excluded_ids_returns_400` does not also test `graduated_student_ids` non-list path.** The view (`admin_views.py:877`) checks both fields in the same `isinstance` guard. A symmetric test for `graduated_student_ids='not-a-list'` would harden coverage. The current test still covers the guard branch. **Non-blocking.**

2. **Hard-coded password `'pass123'`** in `_make_user`. Will work because `force_authenticate(user=user)` skips the password validator, but a brittle string in tests. If your project enforces minimum-password validation in `User.create_user`, this could break in the future. The reports_builder regression tests use `'Pass@1234!'` which is a safer convention. **Cosmetic.**

3. **`test_create_grade_band_requires_name` asserts only the status code (400)** — not the error shape. Adding `self.assertIn('name', response.data)` would pin that the validation error names the offending field. **Non-blocking.**

4. **Throttle scope on `promotion_execute`** — the view sets `request.throttle_scope = 'promotion'`. If `DEFAULT_THROTTLE_RATES['promotion']` is configured tightly in the test settings, three rapid POSTs in `TestPromotionValidation` could hit a throttle. In practice tests usually disable throttles, but worth noting.

5. **TeachingAssignment duplicate validation gap** — already called out in "Known Gaps". The serializer-level `validate` for the `(tenant, teacher, subject, academic_year)` tuple is not directly tested. Low risk because of the DB `unique_together` constraint, but it's the kind of thing that catches a subtle serializer bug.

## Positive Observations

- **URL paths verified end-to-end against `admin_urls.py` + `config/urls.py`** — every test URL matches a registered endpoint name. Spot-checked: `grade-bands/<uuid:band_id>/` → `grade_band_detail`, `sections/<uuid:section_id>/students/` → `section_students` ✅.
- **Decorator semantics correctly distinguished**: `section_students/teachers/courses` use `@teacher_or_admin` (verified at `admin_views.py:475-477`, 508-510, 533-535), while `school_overview` and CRUD endpoints use `@admin_only`. The test `test_teacher_can_access_section_students` and `test_school_overview_teacher_cannot_access` pin both halves of this contract — important behavioral nuance.
- **Cross-tenant isolation tests verify both 404 AND no-mutation**: `test_admin_b_cannot_patch_tenant_a_grade_band` calls `refresh_from_db()` and asserts `name == 'Private Band'`. This catches a class of bugs where 404 is returned but the mutation already landed. ✅
- **List isolation pinned**: `test_list_grade_bands_scoped_to_own_tenant` confirms tenant A's IDs do not leak in tenant B's list response — a basic but critical multi-tenant guarantee.
- **404 not 403 on cross-tenant access** — correct enumeration-resistance pattern (no information leak about whether the resource exists in another tenant).
- **Delete-with-children guard test is well-designed**: `test_delete_grade_band_with_grades_returns_400` creates the dependent Grade row first, attempts the DELETE, asserts 400 + `error` key + verifies the band still exists. All three assertions are necessary to pin the contract.
- **Per-class subdomain isolation via `@override_settings(ALLOWED_HOSTS=...)`** is correct — Django's `TestCase` rolls back transactions between tests, so reusing subdomain `'test'` across classes is fine.
- **Mock strategy is minimal and right** — only `force_authenticate` is used; no business logic is mocked. Tests exercise real DRF middleware, real DB writes, real serializer validation. This is the right level for HTTP-layer view tests.
- **Promotion guard sequence verified in order**: missing year → 400 (before any DB read), non-list IDs → 400, >5000 IDs → 400. The 5000 boundary is asserted by the error message containing `"5000"`, which pins the user-facing copy.
- **Field-level assertions on serializer output**: tests assert `grade_band_name` (read-only field on `GradeSerializer`), `applicable_grade_names` (on `SubjectSerializer`), `student_count`/`section_count`/`course_count` (school overview annotations), and `teacher_email`/`subject_name` (read-only fields on `TeachingAssignmentSerializer`). This pins the API contract that frontends depend on.
- **Documented gaps are honest and well-prioritized**: CSV import, Grade/Section delete-with-students, attendance — all genuinely require extra fixture setup (billing limits, User.grade_fk wiring) that's better tackled in dedicated sessions.

## Verification Performed

| Check | Result |
|-------|--------|
| Test count: 5+9+5+5+6+4+4+3+5+4 = 50 | ✅ |
| 10 test classes per claim | ✅ |
| URL `/api/v1/academics/grade-bands/<uuid>/` resolves to `grade_band_detail` | ✅ admin_urls.py:11 |
| `grade_band_detail` returns 400 + `'error'` key when grades exist | ✅ admin_views.py:94-98 |
| `section_students/teachers/courses` use `@teacher_or_admin` | ✅ admin_views.py:476, 509, 534 |
| `school_overview` uses `@admin_only` | ✅ verified in admin_views.py |
| `promotion_execute` validates `new_academic_year`, list type, 5000 cap | ✅ admin_views.py:867-887 |
| `GradeBand.unique_together = (tenant, name)` matches `validate_name` | ✅ models.py:42, serializers.py:25 |
| `Subject.unique_together = (tenant, code)` matches `validate_code` | ✅ models.py:149, serializers.py:168 |
| Cross-tenant 404 via `get_object_or_404(..., tenant=request.tenant)` | ✅ admin_views.py:88, 155, 228 |
| `order` has default=0 so `GradeBand.objects.create(...)` without order works | ✅ models.py:25 |
| Models exposed (`GradeBand, Grade, Section, Subject, TeachingAssignment`) | ✅ models.py |

## Follow-up (non-blocking, advisory)

1. **Add a happy-path test for `transfer_student`** when the student/section/grade fixture infra is built out — this is a high-blast-radius operation worth pinning explicitly.
2. **Add cross-tenant tests for Grade, Section, Subject, and TeachingAssignment** to mirror the `TestAcademicsCrossTenantIsolation` pattern. Currently only GradeBand has explicit cross-tenant coverage; the same `tenant=request.tenant` pattern applies to all four endpoints, so risk is low, but a defense-in-depth pin would be valuable.
3. **Consider promoting `_make_tenant` / `_make_user` helpers to a shared `academics/conftest.py`** if upcoming sessions add CSV-import / promotion-execute / attendance tests that need the same fixtures.

— reviewer
