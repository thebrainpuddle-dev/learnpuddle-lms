---
tags: [review, branch/claude-admiring-pike, verdict/request-changes, reviewer/lp-reviewer]
created: 2026-03-25
---

# Review: claude/admiring-pike — Fix assigned_teachers serializer + FormData Content-Type

## Branch: `claude/admiring-pike`
## Commits: `4757712`, `bb7e02e`
## Verdict: REQUEST_CHANGES

## Summary
This branch fixes two related bugs: (1) `assigned_teachers` field validation failing on stale/invalid IDs by switching from `PrimaryKeyRelatedField` to `ListField(child=UUIDField())` with custom validation, and (2) frontend sending manual `Content-Type: multipart/form-data` headers which strips the boundary parameter. Both fixes are directionally correct and address real issues, but the serializer change has a **security gap** and a **behavioral regression** that must be addressed.

## Critical Issues

### 1. SECURITY: Silent ID dropping weakens data integrity (commit `4757712`)
**File**: `backend/apps/courses/serializers.py`
**Lines**: `validate_assigned_teachers()` method

The validator silently ignores invalid/stale UUIDs instead of returning an error. This means:
- If a frontend bug sends wrong IDs, data silently corrupts (teachers not assigned when admin thinks they are)
- An attacker could probe for valid teacher UUIDs across tenants by observing which IDs get silently dropped vs accepted
- Admin creates a course thinking 5 teachers are assigned, but only 3 valid IDs persist — **no error shown**

**Recommendation**: Log a warning when IDs are dropped. Better yet, return a validation error listing the invalid IDs so the admin can correct:
```python
invalid_ids = set(value) - set(valid.values_list('id', flat=True))
if invalid_ids:
    raise serializers.ValidationError(
        f"The following teacher IDs are invalid or inactive: {list(invalid_ids)}"
    )
```

### 2. Role filter mismatch between `__init__` and `validate_assigned_teachers` (commit `4757712`)
**File**: `backend/apps/courses/serializers.py`

The `__init__` on main filters: `role__in=['TEACHER', 'HOD', 'IB_COORDINATOR']` (from `exclude(role__in=['SUPER_ADMIN', 'SCHOOL_ADMIN'])`)
The new `validate_assigned_teachers` filters: `role__in=('TEACHER', 'HOD', 'IB_COORDINATOR')`

The old `__init__` also filtered `is_deleted=False` via `User.all_objects`. The new validator uses `User.objects.filter(is_active=True)` which may differ if `TenantManager` has different soft-delete semantics. Need to verify these are equivalent.

## Major Issues

### 3. `to_representation` override breaks DRF serialization pattern (commit `4757712`)
Since `assigned_teachers` is now `write_only=True`, the `to_representation` override manually adds it back to output. This means:
- The field won't appear in schema/OpenAPI docs as readable
- The return type is `list[UUID]` not `list[User]` which changes the API contract
- The old `PrimaryKeyRelatedField(many=True)` returned the same IDs natively

This is functional but not elegant. Consider using a separate read field or removing `write_only=True` and using a `SerializerMethodField` for read.

### 4. `_normalize_multipart_list_fields` dict handling doesn't validate types (commit `bb7e02e`)
**File**: `backend/apps/courses/views.py`, lines 43-51

The new dict normalization:
```python
if isinstance(val, str) and val:
    result[key] = [val]
elif not isinstance(val, list):
    result[key] = [val] if val is not None else []
```
This wraps ANY non-list, non-string value in a list (e.g., integers, dicts). Should only wrap strings and raise on unexpected types.

## Minor Issues

### 5. Missing `getlist` check (commit `bb7e02e`)
The first branch in `_normalize_multipart_list_fields` checks `hasattr(data, 'getlist')` but the new dict branch uses `hasattr(data, 'dict')` on the original code. Wait — looking at the diff more carefully, the `hasattr(data, 'getlist')` check was added but the original code used `hasattr(data, 'dict')`. Actually, the diff shows:
- Original: `if hasattr(data, 'dict'):`  ... `result = data.dict()`
- Commit changes the docstring but the logic reads: `if hasattr(data, 'getlist'):` ... `result = data.dict()`

Actually I see the commit changed the attribute check. Need to verify the `getlist`→`dict()` path is correct. `QueryDict` has both `getlist` and `dict()`, so this is fine.

### 6. Frontend changes are clean
The removal of manual `Content-Type: 'multipart/form-data'` across 6 files is correct — the browser/axios will auto-set the Content-Type with proper boundary when FormData is used. No issues here.

## Positive Observations

1. **Root cause correctly identified**: Manual Content-Type header stripping the multipart boundary is a classic bug that's hard to debug. Good catch.
2. **Comprehensive frontend sweep**: All 6 files with the anti-pattern were fixed, not just the one that was reported.
3. **The normalization for JSON payloads** (wrapping single strings to lists) is a good defensive measure for inconsistent client behavior.
4. **Good commit separation**: Serializer fix and FormData fix are logically separated into distinct commits.

## Required Changes Before Merge
1. Fix silent ID dropping — at minimum log warnings, ideally return validation error
2. Verify role filter equivalence between old and new code
3. Add a unit test for the `validate_assigned_teachers` method
