# Review Request — N+1 Fix Follow-up: ACTIVE_TEACHER_FILTERS + test

**From:** backend-engineer
**To:** lp-reviewer
**Date:** 2026-04-28
**Re:** Non-blocking follow-ups from `BE-N1-COURSE-GROUP-FIX-VERDICT-2026-04-27.md`

---

## Summary

Addressed all four non-blocking reviewer observations from the N+1 fix approval:

| Obs | Item | Status |
|-----|------|--------|
| 1 | Extract `ACTIVE_TEACHER_FILTERS` constant | ✅ Done |
| 2 | Move `logger` below imports in `serializers.py` (PEP 8) | ✅ Done |
| 3 | Explicit test for individual-only fast-path | ✅ Done |
| 4 | Clarifying comment on strict `==` in N+1 guard | ✅ Done |

## Files Changed

| File | Change |
|------|--------|
| `backend/apps/courses/serializers.py` | Added `ACTIVE_TEACHER_FILTERS` constant; moved `logger` after imports; fallback DB query uses `**ACTIVE_TEACHER_FILTERS` |
| `backend/apps/courses/views.py` | Import `ACTIVE_TEACHER_FILTERS` from `.serializers`; Prefetch uses `**ACTIVE_TEACHER_FILTERS` |
| `backend/apps/courses/tests_course_group_n1.py` | New test `test_assigned_teacher_count_individual_only_no_groups`; N+1 guard comment |

## Key Details

### ACTIVE_TEACHER_FILTERS constant (Obs 1)

```python
# serializers.py — module level (single source of truth)
ACTIVE_TEACHER_FILTERS = {"role": "TEACHER", "is_active": True}

# views.py — Prefetch queryset
queryset=_User.objects.filter(**ACTIVE_TEACHER_FILTERS).only('id'),

# serializers.py — DB fallback
User.objects.filter(tenant=obj.tenant, **ACTIVE_TEACHER_FILTERS)
```

The two previously-divergent hardcoded predicates now reference the same constant.

### Logger placement (Obs 2)

Before:
```python
import logging
from rest_framework import serializers
logger = logging.getLogger(__name__)  # ← between imports — PEP 8 violation
from django.db import transaction
...
```

After:
```python
import logging
from django.db import transaction
from django.db.models import Q
from rest_framework import serializers
from .models import ...
...
logger = logging.getLogger(__name__)  # ← correctly after all imports
ACTIVE_TEACHER_FILTERS = {...}
```

### New test (Obs 3)

```python
def test_assigned_teacher_count_individual_only_no_groups(self):
    """Pins the fast-path: if not groups: return len(individual_ids)"""
    t1 = _make_user(f"ind1@...", self.tenant)
    t2 = _make_user(f"ind2@...", self.tenant)
    t3 = _make_user(f"ind3@...", self.tenant)
    course = _make_course(self.tenant, self.admin)
    course.assigned_teachers.add(t1, t2, t3)  # NO assigned_groups
    data = self._get_course_data(course.id)
    self.assertEqual(data["assigned_teacher_count"], 3, ...)
```

### N+1 guard comment (Obs 4)

Added 5-line comment above the `assertEqual` in `CourseListGroupN1TestCase`
explaining that the strict equality is intentional and that future engineers
should look here if they add any per-result query.

## Backward Compatibility

- No model/migration changes
- No API changes
- `ACTIVE_TEACHER_FILTERS` is a new public name in `serializers.py` — additive only
- Serializer behaviour: identical (same predicate, now via constant)

## Static Verification

- AST syntax: all 3 files PASS
- 20-item static checklist verified (PASS on all items)
- Docker run: deferred — same `pythonjsonlogger` sandbox constraint

This is a polish/refactor diff. No behavior change — only one new test that
pins existing behavior.

— backend-engineer
