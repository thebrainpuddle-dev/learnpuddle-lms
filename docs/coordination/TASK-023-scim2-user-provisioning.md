# TASK-023: SCIM 2.0 User Provisioning

**Priority:** P1 (Enterprise Feature)
**Phase:** 3
**Status:** done
**Assigned:** backend-engineer
**Estimated:** 3-4 hours
**Created:** 2026-04-23

## Context

LearnPuddle already has SAML 2.0 SSO for authentication. The natural enterprise
complement is **SCIM 2.0 provisioning** so customers' Okta / Azure AD / OneLogin
identity providers can automatically:

- **Create** user accounts when a new employee is hired
- **Update** user attributes (name, department, role) from HR systems
- **Deactivate** (soft-delete) accounts when an employee leaves

Without SCIM, IT admins must manually manage user accounts in LearnPuddle even
when their IdP already has authoritative user data. This is a table-stakes
feature for Fortune-500 and school-district enterprise deals.

## Scope (MVP — Users endpoint only)

**In scope:**
- `GET  /scim/v2/Users` — list users (pagination + filter by userName)
- `POST /scim/v2/Users` — provision (create) a new user
- `GET  /scim/v2/Users/{id}` — get user by SCIM ID
- `PUT  /scim/v2/Users/{id}` — replace user attributes
- `PATCH /scim/v2/Users/{id}` — partial update via SCIM Operations
- `DELETE /scim/v2/Users/{id}` — deprovision (deactivate, not hard-delete)
- `GET  /scim/v2/ServiceProviderConfig` — advertise supported capabilities
- Admin API to generate/revoke SCIM tokens: `/api/v1/admin/sso/scim-tokens/`

**Out of scope (future):**
- `/scim/v2/Groups` — group provisioning
- `/scim/v2/Schemas` / `/scim/v2/ResourceTypes`
- Bulk operations (SCIM §3.7)

## Standards

- **RFC 7642** — SCIM Concepts
- **RFC 7643** — SCIM Core Schema
- **RFC 7644** — SCIM Protocol

## SCIM Field Mapping

| SCIM attribute | LearnPuddle field | Notes |
|---|---|---|
| `id` | `str(user.id)` | UUID, primary key |
| `externalId` | `employee_id` | IdP-assigned ID |
| `userName` | `email` | Unique identifier |
| `name.givenName` | `first_name` | |
| `name.familyName` | `last_name` | |
| `displayName` | `first_name + " " + last_name` | |
| `active` | `is_active and not is_deleted` | |
| `emails[0].value` | `email` | primary=true, type="work" |
| `urn:learnpuddle:1.0:User.role` | `role` | Custom extension |
| `urn:learnpuddle:1.0:User.department` | `department` | Custom extension |
| `meta.resourceType` | `"User"` | Constant |
| `meta.created` | `date_joined` | |
| `meta.lastModified` | `updated_at` | |
| `meta.location` | `/scim/v2/Users/{id}` | |

## Authentication

SCIM uses per-tenant **Bearer tokens** (not JWT):
- Tenant admin generates a named token via `POST /api/v1/admin/sso/scim-tokens/`
- Token stored hashed (SHA-256) in `SCIMToken` model
- SCIM requests authenticate via `Authorization: Bearer <raw_token>`
- Token lookup: hash incoming token, find matching `SCIMToken`, get tenant

## Models

### `SCIMToken` (in `apps/users/scim_models.py` or tenants)

```python
class SCIMToken(models.Model):
    id = UUIDField(primary_key=True)
    tenant = ForeignKey('tenants.Tenant', on_delete=CASCADE)
    name = CharField(max_length=100)       # e.g. "Okta production"
    token_hash = CharField(max_length=64)  # SHA-256 hex digest
    created_by = ForeignKey('users.User', ...)
    created_at = DateTimeField(auto_now_add=True)
    last_used_at = DateTimeField(null=True)
    is_active = BooleanField(default=True)
```

## Files to Create

- `backend/apps/users/scim_models.py` — `SCIMToken` model
- `backend/apps/users/scim_views.py` — SCIM protocol views
- `backend/apps/users/scim_urls.py` — URL patterns
- `backend/apps/users/scim_admin_views.py` — Token management API
- `backend/apps/users/scim_admin_urls.py` — Admin URL patterns
- `backend/apps/users/tests_scim.py` — Comprehensive test suite (TDD)
- `backend/apps/users/migrations/0012_scim_token.py` — Migration

## Acceptance Criteria

- [x] `POST /scim/v2/Users` creates a TEACHER-role user in the correct tenant
- [x] `PATCH /scim/v2/Users/{id}` with `active=false` deactivates the user
- [x] `DELETE /scim/v2/Users/{id}` deactivates (not hard-deletes) the user
- [x] `GET /scim/v2/Users?filter=userName eq "..."` returns matching user
- [x] All endpoints return 401 for missing/invalid Bearer token
- [x] A token from tenant A cannot see/modify tenant B's users (404)
- [x] All provisioning actions are audit-logged
- [x] `GET /scim/v2/ServiceProviderConfig` returns correct capabilities JSON
