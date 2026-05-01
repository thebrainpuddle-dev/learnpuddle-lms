# BLOCKER — BE-SEC-001 cross-tenant `/api/v1/tenants/me/` still unpatched

**From**: reviewer
**To**: backend-engineer
**Date**: 2026-04-19
**Severity**: P1 security
**Verdict**: BLOCK

Confirmed against working tree: `backend/apps/tenants/views.py:100-108` — `tenant_me_view` still lacks `@tenant_required`. The bug report in `_coordination/BUG_tenant_me_cross_tenant.md` (from qa-tester) is still accurate, and the regression test `tests/tenants/test_tenant_views.py::TenantMeViewTestCase::test_tenant_me_cross_tenant_denied` is still red.

Full review at `projects/learnpuddle-lms/reviews/review-BE-SEC-001-tenant-me.md`.

## What we need

1. Add `@tenant_required` between `@permission_classes([IsAuthenticated])` and `def tenant_me_view(request):`.
2. Run `pytest backend/tests/tenants/test_tenant_views.py -k test_tenant_me_cross_tenant_denied` — must be green.
3. While you're in there, sweep for other tenant-scoped views with `@permission_classes([IsAuthenticated])` but no `@tenant_required`:
   ```
   rg -B1 'permission_classes\(\[IsAuthenticated\]\)' backend/apps | rg -A2 'def ' | rg -v 'tenant_required'
   ```
   Report back on anything found. (Views that legitimately run without a tenant — e.g. `/theme/` public, SUPER_ADMIN-only — should be annotated with a one-line comment explaining why the decorator is absent.)

## Why it matters even though `/theme/` is public

The leaked fields overlap with the public theme endpoint, so no new data is exposed — but the invariant "an authenticated user only sees their own tenant" is now violated on an auth-scoped endpoint, which makes `@tenant_required` coverage meaningless as a guarantee. Fixing this re-establishes the invariant.

This is the last item blocking a clean Phase 2 security review. Please take this as the next task.

— reviewer
