# Review Request — Analytics TDD Tests + SCIM Groups PATCH Follow-ups

**From:** qa-tester
**To:** reviewer
**Date:** 2026-04-24
**Re:** Two test deliverables this session

---

## 1. TDD tests for FE-034 analytics backend endpoints

**New file:** `backend/tests/reports/test_analytics_views.py`

FE-034 (shipped 2026-04-24) wired three analytics chart components to backend
APIs that don't yet exist. These tests define the full HTTP contract so the
backend-engineer can implement the views TDD-style.

### Contract defined

| Endpoint | Contract |
|----------|---------|
| `GET /api/v1/reports/analytics/deadline-adherence/` | Returns `[{period, adherencePercent, totalTeachers, onTime, late}]`; admin-only; optional start/end params; tenant-isolated |
| `GET /api/v1/reports/analytics/approval-trends/` | Returns `[{period, approved, rejected, pending}]`; admin-only; optional start/end params; tenant-isolated |
| `GET /api/v1/reports/analytics/course-effectiveness/` | Returns `[{courseId, courseName, completionRate, avgScore, enrolledCount}]`; admin-only; tenant-isolated; unpublished courses excluded |

### Test count: 35 across 9 classes

| Class | Tests |
|-------|-------|
| `TestDeadlineAdherenceAuth` | 3 |
| `TestDeadlineAdherenceResponseShape` | 3 |
| `TestDeadlineAdherenceData` | 5 |
| `TestApprovalTrendsAuth` | 3 |
| `TestApprovalTrendsResponseShape` | 3 |
| `TestApprovalTrendsData` | 5 |
| `TestCourseEffectivenessAuth` | 3 |
| `TestCourseEffectivenessResponseShape` | 3 |
| `TestCourseEffectivenessData` | 7 |

### Key design decisions

- All tests use self-contained helpers (no dependency on conftest fixtures
  for tenant/user creation) — same pattern as `tests_scim_cross_tenant.py`.
- `TeacherProgress.all_objects.create(...)` used throughout to bypass
  TenantManager contextvar (same approach used in `tests_completion_rate.py`
  which you approved on 2026-04-22).
- `QuizSubmission.all_objects.create(...)` similarly bypasses TenantManager.
- The `_quiz` helper creates an `Assignment` first, then a `Quiz` via
  `Quiz.all_objects.create(tenant=..., assignment=...)` — correct because
  `Quiz` requires a OneToOneField to `Assignment`.
- Tenant isolation tests: one tenant creates data, second admin verifies
  empty result — identical pattern to approved tests.
- Unpublished courses excluded: checked specifically since the engagement
  heatmap precedent filters `is_published=True` courses.
- All tests will return **404** until backend-engineer implements the views
  (correctly TDD-failing state — backend notified).

### One known ambiguity: `ApprovalTrendsPoint.rejected`

The `AssignmentSubmission` model has `PENDING / SUBMITTED / GRADED` status
choices (no explicit `REJECTED`). The test `test_graded_submission_counted_as_approved`
asserts GRADED (score > 0) = approved. No assumption is made about what maps
to "rejected" — tests only assert `rejected >= 0` (non-negative). The
backend-engineer should clarify whether rejected maps to: (a) GRADED with
score below passing_score, (b) a new status value, or (c) something else.
The test for shape only checks the key exists and is an int.

---

## 2. SCIM Groups PATCH follow-ups (TASK-024)

**File modified:** `backend/apps/users/tests_scim_groups.py`

Added class `TestSCIMPatchGroupFollowups` at the end of the file with
7 new test methods. These cover the TASK-024 non-blocking follow-up items
that backend-engineer implemented after the initial TDD tests shipped:

| Test | Verifies |
|------|---------|
| `test_patch_replace_displayname_empty_string_returns_400` | Empty `""` displayName → 400 scimType=invalidValue |
| `test_patch_replace_displayname_whitespace_only_returns_400` | `"   "` displayName → 400 scimType=invalidValue |
| `test_patch_replace_displayname_preserves_group_name_on_empty` | Group name unchanged after 400 rejection |
| `test_patch_audit_log_records_scim_group_patch_action` | AuditLog row written with action='SCIM_GROUP_PATCH' |
| `test_patch_audit_log_includes_ops_detail` | `changes.ops` is a list with `{op, path}` entries |
| `test_patch_audit_log_op_count_matches_operations` | `changes.op_count` == `len(Operations)` in payload |
| `test_patch_remove_member_with_padded_path_still_removes` | `re.search` fix: padded path like `"  members[value eq '...']  "` still removes member |

**Total tests in `tests_scim_groups.py`: 37 → 44**

---

## Static verification

- Import paths confirmed against actual model files.
- Model fields confirmed (`Quiz.assignment` OneToOneField, `QuizSubmission.score`,
  `TeacherProgress.completed_at`, etc.).
- `AuditLog.objects.filter(action=..., target_id=...)` confirmed against
  `AuditLog` model and `log_audit()` function in `utils/audit.py`.
- Docker not available in agent sandbox; CI will be first live run.

---

— qa-tester
