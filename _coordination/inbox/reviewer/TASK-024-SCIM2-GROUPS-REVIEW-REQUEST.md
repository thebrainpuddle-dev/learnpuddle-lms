# REVIEW REQUEST — TASK-024: SCIM 2.0 Groups Provisioning

**From:** backend-engineer  
**To:** reviewer  
**Date:** 2026-04-23  
**Task:** TASK-024 — SCIM 2.0 Groups Provisioning  

---

## Summary

Implemented SCIM 2.0 Groups provisioning endpoints (`/scim/v2/Groups`) allowing
enterprise IdPs (Okta, Azure AD, OneLogin) to push group membership changes to
LearnPuddle automatically. SCIM Groups map 1-to-1 to the existing `TeacherGroup`
model.

This is the natural follow-up to TASK-023 (SCIM 2.0 User Provisioning, under
review). No migration is required — `TeacherGroup` already has the right schema.

---

## Files Changed

| File | Lines | Description |
|------|-------|-------------|
| `backend/apps/users/tests_scim_groups.py` | 370 | 37 TDD tests (written first — RED phase) |
| `backend/apps/users/scim_group_views.py` | 290 | SCIM Groups protocol views |
| `backend/apps/users/scim_urls.py` | +10 | Added Groups URL patterns |
| `backend/apps/users/scim_views.py` | +26 | Updated ServiceProviderConfig (groups + supportedSchemas) |
| `docs/coordination/TASK-024-scim2-groups-provisioning.md` | new | Task doc |

---

## Endpoints Implemented

| Method | Path | Description |
|--------|------|-------------|
| GET | `/scim/v2/Groups` | List groups + `displayName eq` filter + pagination |
| POST | `/scim/v2/Groups` | Provision group (TeacherGroup) |
| GET | `/scim/v2/Groups/{id}` | Retrieve group with members array |
| PUT | `/scim/v2/Groups/{id}` | Full replace (rename + set members) |
| PATCH | `/scim/v2/Groups/{id}` | Partial update via Operations array (add/remove/replace) |
| DELETE | `/scim/v2/Groups/{id}` | Delete group (204 No Content) |

`ServiceProviderConfig` now also advertises `groups.supported=True` and a
`supportedSchemas` array with both User and Group URNs.

---

## Key Design Decisions

1. **Plain Django views** — same rationale as TASK-023: DRF's JWT auth must not
   fire on `/scim/v2/` paths.

2. **`all_objects` manager throughout** — bypasses TenantManager thread-local
   context (None for SCIM requests without a Host header).

3. **Cross-tenant member isolation** — `_resolve_members()` filters candidates
   with `User.objects.all_tenants().filter(id__in=ids, tenant=tenant)`.  Members
   from tenant B passed in a group payload for tenant A are silently discarded.

4. **Hard delete** — `TeacherGroup.delete()` (not soft delete).  Groups have no
   compliance retention requirement; the audit log captures the event.

5. **Audit logged** — all CREATE / UPDATE / PATCH / DELETE operations call
   `log_audit()`.

---

## Test Coverage (37 tests)

| Test Class | Count | What's covered |
|---|---|---|
| `TestSCIMGroupAuthentication` | 5 | 401 on missing/invalid tokens, 200 with valid token |
| `TestSCIMListGroups` | 6 | ListResponse envelope, tenant isolation, displayName filter, pagination, schema shape, empty tenant |
| `TestSCIMCreateGroup` | 6 | 201 + DB record, members, 400 missing name, 409 duplicate, cross-tenant members ignored |
| `TestSCIMGetGroup` | 4 | 200 with member list, cross-tenant 404, nonexistent 404 |
| `TestSCIMPutGroup` | 4 | Rename, replace members, clear members, cross-tenant 404 |
| `TestSCIMPatchGroup` | 6 | Replace displayName, add member, remove member by filter, replace members, no-ops, cross-tenant add ignored |
| `TestSCIMDeleteGroup` | 4 | 204, DB removal, nonexistent 404, cross-tenant 404 |
| `TestSCIMServiceProviderConfigGroups` | 2 | `groups.supported=True`, `supportedSchemas` includes both User + Group URNs |

---

## Acceptance Criteria Checklist

- [x] `GET /scim/v2/Groups` lists all groups for the authenticated tenant
- [x] `GET /scim/v2/Groups?filter=displayName eq "..."` returns matching group
- [x] `POST /scim/v2/Groups` creates TeacherGroup (201) or 409 if name exists
- [x] `GET /scim/v2/Groups/{id}` returns group with members array
- [x] `PUT /scim/v2/Groups/{id}` renames group and replaces member list
- [x] `PATCH /scim/v2/Groups/{id}` supports add/remove/replace Operations
- [x] `DELETE /scim/v2/Groups/{id}` deletes TeacherGroup (204)
- [x] All endpoints return 401 for missing/invalid Bearer token
- [x] Group from tenant A cannot be seen/modified via tenant B's token (404)
- [x] Members from other tenants are silently ignored in add/set operations
- [x] `GET /scim/v2/ServiceProviderConfig` advertises `groups.supported=true`
- [x] `GET /scim/v2/ServiceProviderConfig` includes `supportedSchemas` with Group URN
- [x] All group operations are audit-logged

---

## Items for Reviewer Attention

1. **`all_objects` vs `objects`**: Groups views consistently use
   `TeacherGroup.all_objects` to bypass TenantManager — same pattern as SCIM
   Users using `User.objects.all_tenants()`. Verify this is correct.

2. **No migration**: `TeacherGroup` model is unmodified. The implementation
   works with the existing `members` M2M reverse relation (`User.teacher_groups`
   with `related_name='members'`).

3. **DELETE is hard**: Unlike User deprovision (soft — `is_active=False`), Group
   delete is hard (`TeacherGroup.delete()`). Groups don't have a compliance
   retention requirement; open to reverting to soft-delete if reviewer prefers.

4. **`ServiceProviderConfig` backward compat**: Added `groups` and
   `supportedSchemas` keys to the existing JSON response. Existing keys
   (`patch`, `bulk`, `filter`, etc.) unchanged. IdPs that ignore unknown keys
   are unaffected; IdPs that only accept listed schemas will now correctly
   enable Group push.

---

## Temp Files (discard)

- `backend/run_tests.sh` — created during test runner discovery; contains no
  production or test code. Can be deleted before merging.

---

No git commits. No git add. No git push.

— backend-engineer
