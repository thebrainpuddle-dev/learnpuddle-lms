# Review Request — TASK-023: SCIM 2.0 User Provisioning

**From:** backend-engineer  
**To:** reviewer  
**Date:** 2026-04-23  
**Priority:** P1 (Enterprise Feature)

## What was built

Full SCIM 2.0 user provisioning implementation (RFC 7643 / RFC 7644), enabling
Okta / Azure AD / OneLogin to auto-manage users in LearnPuddle tenants.

## Files to review

| File | Lines | Role |
|------|-------|------|
| `backend/apps/users/tests_scim.py` | ~860 | 42 tests across 10 test classes |
| `backend/apps/users/scim_models.py` | ~100 | `SCIMToken` model |
| `backend/apps/users/migrations/0012_scim_token.py` | ~83 | DB migration |
| `backend/apps/users/scim_views.py` | ~365 | SCIM protocol views |
| `backend/apps/users/scim_urls.py` | ~30 | URL patterns |
| `backend/apps/users/scim_admin_views.py` | ~100 | Admin token management |
| `backend/apps/users/scim_admin_urls.py` | ~20 | Admin URL patterns |
| `backend/config/urls.py` | +5 lines | URL mount points |

## Key design choices for review

1. **Plain Django views (not DRF) for `/scim/v2/`**  
   DRF's JWT `JWTAuthentication` backend would reject SCIM Bearer tokens as invalid
   JWTs. Plain views with `@csrf_exempt` + manual `_authenticate_scim()` keep the
   auth paths cleanly separate.

2. **Tenant isolation without TenantMiddleware context**  
   SCIM requests typically don't carry the tenant subdomain in the Host header
   (IdPs send requests to a fixed endpoint). All queries use
   `User.objects.all_tenants().filter(tenant=scim_token.tenant)` to bypass the
   thread-local tenant context and scope directly to the token's tenant.

3. **Soft deprovision only**  
   `DELETE /scim/v2/Users/{id}` sets `is_active=False`; `is_deleted` is never
   touched. This preserves audit trail and allows re-provisioning the same user
   via PUT `active=true` without creating a duplicate row.

4. **Global email uniqueness check on provision**  
   `User.email` is `unique=True` across all tenants. The POST handler checks
   `User.objects.all_tenants().filter(email__iexact=userName)` to return a 409
   before hitting the DB constraint.

5. **Test bug fixes (own-code)**  
   Two bugs found in the TDD RED-phase tests I wrote:
   - `_scim_headers()` returned `content_type` which caused a duplicate-keyword
     `TypeError` on `c.post(…, content_type=…, **_scim_headers(…))` calls →
     removed `content_type` from the helper dict.
   - `_make_admin_client()` built `HTTP_HOST=f"{subdomain}.lms.test"` but the
     `conftest.py` autouse fixture sets `PLATFORM_DOMAIN="lms.com"` →
     changed to `.lms.com` so `TenantMiddleware` resolves the correct tenant.

## Acceptance criteria checklist

- [x] `POST /scim/v2/Users` creates a TEACHER-role user in the correct tenant
- [x] `PATCH /scim/v2/Users/{id}` with `active=false` deactivates the user
- [x] `DELETE /scim/v2/Users/{id}` deactivates (not hard-deletes) the user
- [x] `GET /scim/v2/Users?filter=userName eq "..."` returns matching user
- [x] All endpoints return 401 for missing/invalid Bearer token
- [x] Token from tenant A cannot see/modify tenant B's users (404)
- [x] All provisioning actions are audit-logged
- [x] `GET /scim/v2/ServiceProviderConfig` returns correct capabilities JSON

## Out of scope (future tasks)

- `/scim/v2/Groups` — group provisioning
- Bulk operations (SCIM §3.7)
- `/scim/v2/Schemas` and `/scim/v2/ResourceTypes`

— backend-engineer
