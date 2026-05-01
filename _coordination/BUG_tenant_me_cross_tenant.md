# BUG: Cross-Tenant Info Leak on GET /api/v1/tenants/me/

**From**: qa-tester  
**To**: backend-engineer  
**Date**: 2026-04-19  
**Severity**: P1 Security — Cross-Tenant Information Disclosure  

---

## Summary

`tenant_me_view` in `apps/tenants/views.py` is **missing the `@tenant_required` decorator**.  
A user from Tenant A can hit Tenant B's `/api/v1/tenants/me/` endpoint and receive Tenant B's details (name, branding colors, subdomain, logo URL).

## Steps to Reproduce

```python
# Teacher from school A authenticates and then requests school B's /me/
import requests
token = login("teacher@schoola.com", "Password1!")  # valid teacher, Tenant A
r = requests.get(
    "https://schoolb.learnpuddle.com/api/v1/tenants/me/",
    headers={"Authorization": f"Bearer {token}"},
)
# Returns 200 with Tenant B's name, colors, logo — expected 403
```

## Root Cause

`apps/tenants/views.py` line 100-108:

```python
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def tenant_me_view(request):                        # ← Missing @tenant_required
    tenant = getattr(request, "tenant", None) or get_tenant_from_request(request)
    serializer = TenantThemeSerializer(tenant, context={"request": request})
    return Response(serializer.data, status=status.HTTP_200_OK)
```

Compare to `tenant_config_view` (line 111) which correctly has `@tenant_required`.

## Fix

Add `@tenant_required` after `@permission_classes`:

```python
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@tenant_required                                   # ← ADD THIS
def tenant_me_view(request):
    ...
```

The `@tenant_required` decorator (in `utils/decorators.py`) already enforces:
- Tenant context must exist
- `request.user.tenant_id != resolved_tenant.id` → raises `PermissionDenied` (403)

## Test

The failing test `tests/tenants/test_tenant_views.py::TenantMeViewTestCase::test_tenant_me_cross_tenant_denied` is the regression test for this fix. It is currently marked with a clear comment explaining the bug. Once you add `@tenant_required`, this test will pass automatically.

## Impact

Without this fix, any authenticated user (teacher at any school) can enumerate branding details for any other school in the platform by iterating subdomain guesses. The data exposed includes: school name, primary_color, secondary_color, logo_url, subdomain. Not catastrophic (same data is on the public `/api/v1/tenants/theme/` endpoint) but it violates the multi-tenant isolation invariant.
