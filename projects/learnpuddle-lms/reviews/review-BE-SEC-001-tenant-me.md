---
tags: [review, task/BE-SEC-001, verdict/block, reviewer/lp-reviewer, security]
created: 2026-04-19
severity: P1
files:
  - backend/apps/tenants/views.py (L100-108)
---

# Review: BE-SEC-001 — Cross-Tenant Info Leak on GET /api/v1/tenants/me/

## Verdict: BLOCK — UNFIXED AS OF 2026-04-19

## Summary
qa-tester filed this P1 in `_coordination/BUG_tenant_me_cross_tenant.md` on 2026-04-19. I verified the fix has **not** been applied: `apps/tenants/views.py:100-108` still lacks `@tenant_required`. The failing regression test `tests/tenants/test_tenant_views.py::TenantMeViewTestCase::test_tenant_me_cross_tenant_denied` remains red.

## Current state of `tenant_me_view`
```python
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def tenant_me_view(request):                     # ← @tenant_required MISSING
    tenant = getattr(request, "tenant", None) or get_tenant_from_request(request)
    serializer = TenantThemeSerializer(tenant, context={"request": request})
    return Response(serializer.data, status=status.HTTP_200_OK)
```

Compare to sibling view four lines below:
```python
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@tenant_required                                 # ← correct pattern
def tenant_config_view(request):
    ...
```

## Impact (confirmed)
Any authenticated teacher on Tenant A can hit Tenant B's `/api/v1/tenants/me/` and receive B's name, branding, logo URL, and subdomain. Violates multi-tenant isolation invariant even though the fields overlap with the public `/theme/` endpoint — the invariant, not the data sensitivity, is the bug.

## Required fix
Single decorator addition, already specified in the bug report. No schema changes, no migration. Regression test is already authored — will flip green automatically.

## Blockers for approval
1. Apply `@tenant_required` on `tenant_me_view`.
2. `pytest backend/tests/tenants/test_tenant_views.py::TenantMeViewTestCase::test_tenant_me_cross_tenant_denied` must pass.
3. Confirm no other `@permission_classes([IsAuthenticated])` views on tenant-scoped data are missing `@tenant_required` — grep pattern:
   ```
   rg -B1 'permission_classes\(\[IsAuthenticated\]\)' backend/apps | rg -A2 'def ' | rg -v 'tenant_required'
   ```

## Next Actions
- Assign to backend-engineer via `_coordination/inbox/backend-engineer/`.
- Keep `status/review` until fix lands and test is green.
