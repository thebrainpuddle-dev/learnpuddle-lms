---
tags: [review, task/BE-SEC-001, verdict/approve, reviewer/lp-reviewer, security]
created: 2026-04-19
severity: P1
round: r2
files:
  - backend/apps/tenants/views.py (L95-109)
  - backend/utils/decorators.py (L8-31)
  - backend/tests/tenants/test_tenant_views.py (L174-192)
---

# Review: BE-SEC-001 r2 — Cross-Tenant Info Leak on GET /api/v1/tenants/me/

## Verdict: APPROVE

The fix is correctly applied and the sweep claim in the backend-engineer's shared-log entry is substantially verified. One minor annotation-completeness nit noted below; it is not a security issue and should not block merge.

## Verification

### 1. Primary fix — `tenant_me_view`
`backend/apps/tenants/views.py:95-109` now reads:

```python
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@tenant_required
def tenant_me_view(request):
    """Return current tenant branding+feature payload for logged-in user."""
    serializer = TenantThemeSerializer(request.tenant, context={"request": request})
    return Response(serializer.data, status=status.HTTP_200_OK)
```

- Decorator is between `@permission_classes([IsAuthenticated])` and the `def` — correct DRF stacking (permission_classes wraps outermost; tenant_required runs after auth is resolved and can safely read `request.user`).
- Import at line 9: `from utils.decorators import admin_only, tenant_required` — confirmed.
- Body simplified to use `request.tenant` directly. Safe because `@tenant_required` in `utils/decorators.py:8-31` either sets `request.tenant` or raises `PermissionDenied("Tenant context required")` before the view runs, so the attribute is guaranteed non-None on entry.

### 2. Decorator semantics (`utils/decorators.py:8-31`)
```python
def tenant_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        tenant = get_current_tenant()
        if tenant is None:
            raise PermissionDenied("Tenant context required")
        request.tenant = tenant
        if (
            request.user.is_authenticated
            and request.user.role != 'SUPER_ADMIN'
            and request.user.tenant_id != tenant.id
        ):
            raise PermissionDenied("Access denied: User does not belong to this tenant")
        return view_func(request, *args, **kwargs)
    return wrapper
```
- Cross-tenant user on resolved-tenant path → `PermissionDenied` → DRF default handler → HTTP 403.
- `SUPER_ADMIN` bypass preserved (by design).
- Missing tenant context → 403, not 500. Correct.

### 3. Regression test shape
`backend/tests/tenants/test_tenant_views.py:174-192` `test_tenant_me_cross_tenant_denied` asserts `r.status_code == 403` after logging in as a Tenant-A user and hitting Tenant-B's `/api/v1/tenants/me/`. This is exactly what `PermissionDenied` surfaces. Test will flip green with the fix. (Sandbox could not execute `pytest`; static trace is unambiguous.)

### 4. Sweep — `@permission_classes([IsAuthenticated])` without `@tenant_required`
Re-ran a static scan across `backend/apps/**/*.py`. The backend-engineer's table is accurate: user-self views (`apps/users/views.py`, `apps/users/twofa_views.py`, `apps/users/sso_views.py`) and `apps/ops/views.py` (`@super_admin_only`) all either operate on `request.user`'s own record or are platform-level — legitimate absences, and explanatory comments have been added.

**One miss flagged — non-blocking:**
`backend/apps/courses/maic_views.py:1492-1498` — `maic_list_voices` has `@permission_classes([IsAuthenticated])` but neither `@tenant_required` nor a "No @tenant_required:" comment. The body returns only the static `AZURE_IN_VOICES` constant — there is no tenant-scoped data access and therefore no leak — but this view was missed by the sweep annotation commitment. Suggest either adding `@tenant_required` (cheap and consistent) or a one-line comment explaining "returns static voice catalog; no tenant-scoped data." Not a blocker.

## Risk Assessment
- Cross-tenant isolation invariant restored on `/api/v1/tenants/me/`.
- No schema/migration impact.
- No behavior change for correctly-scoped users.
- SUPER_ADMIN can still cross tenants via subdomain (existing documented behaviour).

## Next Actions
- Merge; mark BE-SEC-001 `status/done`.
- Optional follow-up: annotate or tenant-gate `maic_list_voices` for sweep hygiene.
