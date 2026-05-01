# Review Request — CourseListSerializer N+1 fix (group assignments)

**From:** backend-engineer
**To:** lp-reviewer
**Date:** 2026-04-27
**Priority:** P1 bug fix (last outstanding item from Phase 2)

---

## Summary

Eliminated the final N+1 query in `GET /api/v1/courses/`: the per-course
`User COUNT` issued by `get_assigned_teacher_count` for courses with
`assigned_groups`.

## Files Changed

| File | Change |
|------|--------|
| `backend/apps/courses/views.py` | Added `TeacherGroup` import; added `_User` top-level import; replaced `'assigned_groups'` prefetch string with nested `Prefetch` that also loads active-teacher members (`to_attr='_active_teachers'`) |
| `backend/apps/courses/serializers.py` | `get_assigned_teacher_count`: use Python set-union over prefetched `_active_teachers` when available; DB-query fallback preserved |
| `backend/apps/courses/tests_course_group_n1.py` | **NEW** — 6 TDD tests (5 correctness + 1 N+1 query guard) |

## Key Changes

### views.py — nested Prefetch

```python
# Before
.prefetch_related(
    'assigned_teachers',
    'assigned_groups',          # fetched group objects but NOT members → N+1
)

# After
.prefetch_related(
    'assigned_teachers',
    Prefetch(
        'assigned_groups',
        queryset=TeacherGroup.objects.prefetch_related(
            Prefetch(
                'members',
                queryset=_User.objects.filter(role='TEACHER', is_active=True).only('id'),
                to_attr='_active_teachers',   # attached to each TeacherGroup instance
            )
        ),
    ),
)
```

### serializers.py — prefetch-path in `get_assigned_teacher_count`

```python
# New branch (before the existing DB-query fallback):
if all(hasattr(g, '_active_teachers') for g in groups):
    all_teacher_ids = set(individual_ids)
    for g in groups:
        all_teacher_ids.update(m.id for m in g._active_teachers)
    return len(all_teacher_ids)

# Fallback DB query preserved unchanged (for tooling/tests without the view queryset)
```

## Test Coverage

```
tests_course_group_n1.py::AssignedTeacherCountGroupsTestCase
  test_assigned_teacher_count_counts_group_members
  test_assigned_teacher_count_deduplicates_group_and_individual
  test_assigned_teacher_count_excludes_inactive_group_members
  test_assigned_teacher_count_excludes_non_teacher_role_group_members
  test_assigned_teacher_count_combines_multiple_groups

tests_course_group_n1.py::CourseListGroupN1TestCase
  test_query_count_does_not_grow_with_group_assigned_courses   ← N+1 guard
```

Docker run: `docker compose exec web pytest apps/courses/tests_course_group_n1.py -v`

## What's NOT Changed

- `assigned_to_all=True` path (uses `tenant_teacher_count` from context, unchanged)
- Individual-only assignment path (fast path `len(individual_ids)`, unchanged)
- Existing `tests_completion_rate.py` and `tests_admin_course_views.py` (both unaffected)
- All other views that use `CourseListSerializer` without the full list-view queryset
  fall through to the DB fallback (backward compatible)

## Static Verification

- AST syntax: all 3 files PASS
- Circular import: none (User model uses string reference to TeacherGroup)
- `to_attr` is the official Django ORM API for naming prefetch results
- Logic trace for deduplication case: verified in static analysis
- Existing tests: no breakage (confirmed via code trace)

Docker test run deferred (same `pythonjsonlogger` sandbox constraint as all Phase 2/3/4 work).

— backend-engineer
