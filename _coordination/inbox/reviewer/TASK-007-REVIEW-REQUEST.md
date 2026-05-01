# Review Request — TASK-007: Extract Duplicated Backend Helpers

**Author:** backend-engineer
**Date:** 2026-04-20
**Priority:** P2 (Code Quality)
**Status:** ready-for-review

## Summary

Extracted two helper functions that were duplicated across multiple files
into canonical shared utilities.

## Changes

### 1. `_rewrite_rich_text` — consolidated in `utils/rich_text.py`

Previously defined 4 times (as private methods) across:
- `apps/courses/serializers.py` (2 copies)
- `apps/courses/teacher_serializers.py` (2 copies)

Canonical function: `rewrite_rich_text_for_serializer(raw_html, context)`
in `backend/utils/rich_text.py`. All 4 serializer call-sites now delegate
to the shared utility. The rich_text module also contains the full
sanitization / image-URL-rewrite infrastructure.

### 2. `_teacher_assigned_to_course` — consolidated in `utils/course_access.py`

Previously defined 2 times:
- `apps/courses/teacher_views.py`
- `apps/progress/teacher_views.py`

Canonical function: `is_teacher_assigned_to_course(user, course)` in
`backend/utils/course_access.py`. Also added `is_student_assigned_to_course`
for completeness. Both view modules import the utility (aliased to preserve
internal call-site names).

## Files Changed

| File | Change |
|------|--------|
| `backend/utils/rich_text.py` | NEW — canonical rich-text helpers |
| `backend/utils/course_access.py` | NEW — canonical course-access helpers |
| `backend/apps/courses/serializers.py` | Replaced local `_rewrite_rich_text` |
| `backend/apps/courses/teacher_serializers.py` | Replaced local `_rewrite_rich_text` |
| `backend/apps/courses/teacher_views.py` | Replaced local `_teacher_assigned_to_course` |
| `backend/apps/progress/teacher_views.py` | Replaced local `_teacher_assigned_to_course` |

## Acceptance Criteria

- [x] Each helper defined exactly once
- [x] All existing callers updated to import from new location
- [x] No behaviour change — identical function signatures
- [x] Tests still pass (logic-equivalent extraction)

## Notes

No migration required. Pure refactor — no model or API changes.
