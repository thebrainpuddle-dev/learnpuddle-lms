# TASK-007: Extract Duplicated Backend Helpers

**Priority:** P2 (Code Quality)
**Phase:** 2
**Status:** review
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
