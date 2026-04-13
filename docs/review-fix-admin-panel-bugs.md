---
tags: [review, branch/fix-admin-panel-bugs, verdict/request-changes, reviewer/lp-reviewer]
created: 2026-03-25
---

# Review: fix/admin-panel-bugs — Multiple admin panel fixes

## Branch: `fix/admin-panel-bugs`
## Commits: `c7f2571`, `a50e108`, `ec92bbc`, `32f1098`, `446b16b` (5 commits)
## Verdict: REQUEST_CHANGES

## Summary
This branch addresses multiple admin panel bugs across 5 well-separated commits: course serializer validation, teacher creation validation, migration fixes, documentation, and frontend FormData header cleanup. The fixes are directionally correct, but **main has since received improved versions of several of these fixes independently**, making this branch partially stale. The teacher creation validation and migration commits provide unique value not on main.

## Critical Issues

### 1. SECURITY: Bulk import leaks cross-tenant user existence (commit `a50e108`)
**File**: `backend/apps/users/admin_views.py`, lines 231-241

```python
elif existing_user.tenant_id == tenant.id:
    results.append({...message: "Teacher already exists in this school"})
else:
    results.append({...message: "Email is registered with another organization"})
```

This tells an admin whether an email exists in ANOTHER tenant. This is an **information disclosure vulnerability** — a school admin can enumerate which email addresses are registered at other schools by bulk-importing a CSV of target emails and observing the different error messages.

**Fix**: Use a single generic message regardless of which tenant owns the email:
```python
results.append({"row": i, "email": email, "status": "error",
    "message": "Email is already in use"})
```

### 2. Migration depends on deleted `media` app (commit `ec92bbc`)
**File**: `backend/apps/courses/migrations/0005_content_media_asset.py`

```python
dependencies = [
    ("courses", "0004_..."),
    ("media", "0001_initial"),  # ← media app is deleted on other branches
]
```

This migration adds a FK to `media.MediaAsset`, but the `fix/admin-panel-bugs` branch's own diff (checked via `--stat`) shows the entire `apps/media/` module being deleted. If the media app is removed, this migration will fail. This needs coordination — either the media app stays, or this migration must be reverted/squashed.

## Major Issues

### 3. Course serializer fix is stale — main has improved version (commit `c7f2571`)
**File**: `backend/apps/courses/serializers.py`

Branch uses:
```python
self.fields['assigned_teachers'].queryset = User.objects.filter(
    tenant=request.tenant,
).exclude(role__in=['SUPER_ADMIN', 'SCHOOL_ADMIN'])
```

Main now uses:
```python
teachers_qs = User.all_objects.filter(
    tenant=request.tenant,
    is_deleted=False,
).exclude(role__in=['SUPER_ADMIN', 'SCHOOL_ADMIN'])
self.fields['assigned_teachers'].child_relation.queryset = teachers_qs
```

Key differences on main:
- Uses `User.all_objects` to bypass TenantManager (avoids double-filtering)
- Explicitly filters `is_deleted=False` for soft-delete safety
- Sets queryset on `.child_relation` (correct for `many=True` fields with DRF)

The branch version sets `.queryset` directly which **doesn't work** with DRF's `ManyRelatedField` wrapper — it needs `.child_relation.queryset`. This is a **functional bug**.

### 4. Frontend FormData fix duplicates `admiring-pike` branch (commit `446b16b`)
The same files are modified in both branches. `admiring-pike` has the same Content-Type header removal plus additional backend normalization. Merging both will cause conflicts.

### 5. Missing `child_relation` for assigned_groups (commit `c7f2571`)
Same issue as #3 — the branch sets `.queryset` instead of `.child_relation.queryset`:
```python
self.fields['assigned_groups'].queryset = TeacherGroup.objects.all_tenants().filter(...)
```
This won't properly validate in DRF's `PrimaryKeyRelatedField(many=True)`. Main fixed this correctly.

## Minor Issues

### 6. `validate_email` in RegisterTeacherSerializer queries all tenants (commit `a50e108`)
```python
if User.objects.filter(email__iexact=value, is_deleted=False).exists():
```
`User.objects` uses TenantManager which auto-filters by current tenant. But email uniqueness should be global. This query might miss users in other tenants. Should use `User.objects.all_tenants().filter(...)` or `User.all_objects.filter(...)`.

### 7. Thumbnail URL construction in CourseEditorPage is fragile (commit `446b16b`)
```typescript
const backendOrigin = (process.env.REACT_APP_API_URL || 'http://localhost:8000/api')
    .replace(/\/api\/?$/, '');
```
This regex-strips `/api` from the URL to construct a media origin. Fragile — if API URL changes format, this breaks. Better to use a dedicated `REACT_APP_MEDIA_URL` env var or return full URLs from the API.

### 8. `CourseSkipRequest` migration lacks `TenantManager` (commit `ec92bbc`)
The `CourseSkipRequest` model created in the migration has a `tenant` FK but the migration doesn't show the model using `TenantManager`. Needs verification that the model class uses it.

### 9. Good: CLAUDE.md documentation (commit `32f1098`)
The CLAUDE.md addition is valuable — comprehensive development guide. Already on main in refined form.

## Positive Observations

1. **Well-structured commits** — each commit is atomic and focused on one concern
2. **Teacher email validation** is thorough — handles soft-deleted users, case-insensitive matching, email normalization
3. **The `all_tenants()` pattern** for TeacherGroup correctly identifies the double-filtering issue with TenantManager
4. **Migration dependency chain** is correctly ordered (0004 → 0005)
5. **Frontend FormData fix** has excellent commit message explaining the root cause

## Recommendation
This branch is **partially stale**. Recommended path:

1. **Cherry-pick** commit `a50e108` (teacher validation) — unique value, not on main (after fixing the tenant leak in bulk import)
2. **Drop** commit `c7f2571` — superseded by better fix on main
3. **Drop** commit `446b16b` — superseded by `admiring-pike` or already on main
4. **Evaluate** commit `ec92bbc` — only if `apps/media` module still exists
5. **Drop** commit `32f1098` — CLAUDE.md already on main

Alternatively, close this branch and open a focused PR for just the teacher validation improvements.
