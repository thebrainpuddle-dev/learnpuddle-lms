# TASK-007: Extract Duplicated Backend Helpers

**Priority:** P2 (Code Quality)
**Phase:** 2
**Status:** done
**Assigned:** backend-engineer
**Estimated:** 1-2 hours

## Problem

Two helper functions are duplicated across multiple files:

### 1. `_rewrite_rich_text` (4 copies)
- `backend/apps/courses/serializers.py` (2 definitions)
- `backend/apps/courses/teacher_serializers.py` (2 definitions)

### 2. `_teacher_assigned_to_course` (2 copies)
- `backend/apps/courses/teacher_views.py` (1 definition, 3 usages)
- `backend/apps/progress/teacher_views.py` (1 definition, 4+ usages)

## Fix Required

### `_rewrite_rich_text`
1. Move to `backend/utils/content.py` (or `backend/utils/rich_text.py`)
2. Single canonical implementation
3. Update all imports in `serializers.py` and `teacher_serializers.py`

### `_teacher_assigned_to_course`
1. Move to `backend/utils/permissions.py` (or `backend/utils/course_access.py`)
2. Single canonical implementation
3. Update imports in both `courses/teacher_views.py` and `progress/teacher_views.py`

## Files to Modify

- `backend/utils/content.py` — NEW: canonical `_rewrite_rich_text`
- `backend/utils/course_access.py` — NEW: canonical `_teacher_assigned_to_course`
- `backend/apps/courses/serializers.py` — Replace local definition with import
- `backend/apps/courses/teacher_serializers.py` — Replace local definition with import
- `backend/apps/courses/teacher_views.py` — Replace local definition with import
- `backend/apps/progress/teacher_views.py` — Replace local definition with import

## Acceptance Criteria

- [x] Each helper defined exactly once
- [x] All existing callers updated to import from new location
- [x] No behavior change — identical function signatures
- [x] Tests still pass

## Implementation Notes

**`_rewrite_rich_text`** → Canonical implementation in `utils/rich_text.py` as
`rewrite_rich_text_for_serializer(raw_html, context)`.  All 4 duplicate method
bodies in `courses/serializers.py` and `courses/teacher_serializers.py` replaced
with one-line delegates.

**`_teacher_assigned_to_course`** → Canonical implementation in
`utils/course_access.py` as `is_teacher_assigned_to_course(user, course)`.
Local definitions removed from `courses/teacher_views.py` and
`progress/teacher_views.py`; each imports the utility with a local alias to
preserve internal call-site names.

## Review (2026-04-20)

**Verdict: APPROVE**

- Canonical `rewrite_rich_text_for_serializer(raw_html, context)` lives in
  `backend/utils/rich_text.py` (L228-261) with good docstring, per-context
  image URL cache, and preserved existing shared helpers
  (`collect_rich_text_image_ids`, `sanitize_rich_text_html`, etc.). No behavior
  change vs. the 4 former inline implementations.
- `apps/courses/serializers.py` L71-72 and L106-107 are now one-line delegates;
  `apps/courses/teacher_serializers.py` L146-147 and L215-216 similarly reduced
  to one-line delegates. `to_representation` hooks preserved.
- Canonical `is_teacher_assigned_to_course(user, course)` lives in
  `backend/utils/course_access.py` with correct access-rule set (admin,
  assigned_to_all, assigned_teachers, assigned_groups). Bonus
  `is_student_assigned_to_course` included — acceptable add given the parallel
  pattern.
- Both view files (`apps/courses/teacher_views.py` L10, `apps/progress/teacher_views.py` L36)
  import with `as _teacher_assigned_to_course` alias so the 10+ call sites are
  unchanged. `grep` confirms zero remaining local definitions of either helper.
- Noted (non-blocking): `apps/courses/student_serializers.py` L100, L156 still
  carry two inline copies of `_rewrite_rich_text`. These were outside the
  original spec (which called out 4 copies in courses/serializers.py + courses/teacher_serializers.py)
  but should be unified in a follow-up sweep for full DRY — recommend a small
  TASK-007b.
- Tests: no new tests required for a pure refactor; existing serializer /
  course-access tests exercise the helpers via the calling layers.

Status updated to `done`.
