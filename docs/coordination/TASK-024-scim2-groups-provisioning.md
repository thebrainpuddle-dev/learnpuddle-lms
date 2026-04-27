# TASK-024 — SCIM 2.0 Groups Provisioning

**Status:** done  
**Assigned:** backend-engineer  
**Started:** 2026-04-23  
**Phase:** Phase 3 — Enterprise Features  
**Priority:** P1  
**Depends on:** TASK-023 (SCIM 2.0 User Provisioning) — done

---

## Summary

Implement `/scim/v2/Groups` endpoints so that enterprise IdPs (Okta, Azure AD,
OneLogin) can push group membership changes to LearnPuddle automatically.

SCIM Groups map 1-to-1 to `TeacherGroup` objects (same UUID primary key, same
tenant scoping).

---

## Acceptance Criteria

- [ ] `GET /scim/v2/Groups` lists all groups for the authenticated tenant
- [ ] `GET /scim/v2/Groups?filter=displayName eq "..."` returns matching group
- [ ] `POST /scim/v2/Groups` creates a TeacherGroup (201) or 409 if name exists
- [ ] `GET /scim/v2/Groups/{id}` returns group with members array
- [ ] `PUT /scim/v2/Groups/{id}` renames group and replaces member list
- [ ] `PATCH /scim/v2/Groups/{id}` supports add/remove/replace member Operations
- [ ] `DELETE /scim/v2/Groups/{id}` deletes the TeacherGroup (204)
- [ ] All endpoints return 401 for missing/invalid Bearer token
- [ ] Group from tenant A cannot be seen/modified via tenant B's token (404)
- [ ] Members from other tenants are silently ignored in add/set operations
- [ ] `GET /scim/v2/ServiceProviderConfig` advertises `groups.supported=true`
- [ ] All group operations are audit-logged

---

## Files Changed

| File | Description |
|------|-------------|
| `backend/apps/users/tests_scim_groups.py` | 37 TDD tests (written first — RED phase) |
| `backend/apps/users/scim_group_views.py` | SCIM Groups protocol views |
| `backend/apps/users/scim_urls.py` | Added Groups URL patterns |
| `backend/apps/users/scim_views.py` | Updated ServiceProviderConfig (groups + supportedSchemas) |

No migration needed: TeacherGroup model already exists with correct schema.

---

## Design Notes

- **Plain Django views** (not DRF) — same rationale as TASK-023: JWT auth must
  not fire on SCIM requests.
- **No migration**: `TeacherGroup` is pre-existing; no new columns added.
- **Member resolution** via `User.objects.all_tenants().filter(id__in=ids, tenant=tenant)` —
  members from other tenants are silently discarded.
- **Hard delete**: `TeacherGroup.delete()` (not soft delete) — groups have no
  compliance requirement for retention; the audit log captures the deletion.
- **`all_objects` manager used throughout**: bypasses TenantManager thread-local
  context that is None for SCIM requests without a matching Host header.
