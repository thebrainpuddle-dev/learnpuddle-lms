# Review Request — SCIM Cross-Tenant Email Enum Fix + TASK-024 Follow-ups

**From:** backend-engineer
**To:** reviewer
**Date:** 2026-04-23
**Related tasks:** TASK-023 close-out (FOLLOWUP-SCIM-CROSS-TENANT-EMAIL-ENUM),
  TASK-024 non-blocking follow-ups

---

## Summary

Two independent changesets landed together. Both are small and targeted.

---

## Changeset 1 — SCIM Cross-Tenant Email Enumeration (security follow-up)

**File:** `backend/apps/users/scim_views.py`

**What changed:**

Added `import logging` / `logger = logging.getLogger(__name__)` at module level.

Replaced the single-tier global uniqueness check in the POST handler (the old
check returned 409 regardless of which tenant the email belonged to) with the
two-tier check you specified:

```python
# 1) In-tenant collision → 409 uniqueness (SCIM-spec required)
if User.objects.all_tenants().filter(
    tenant=tenant, email__iexact=user_name
).exists():
    return _scim_error(409, f"User with userName '{user_name}' already exists.", "uniqueness")

# 2) Cross-tenant collision → generic 400, no enumeration leak
if User.objects.all_tenants().filter(email__iexact=user_name).exists():
    logger.warning(
        "scim_post: cross-tenant email collision token_tenant=%s email=%s",
        tenant.id, user_name,
    )
    return _scim_error(400, "Email unavailable.", "invalidValue")
```

The email string does not appear in the 400 response body. DB constraint
unchanged.

**Regression tests:** `backend/apps/users/tests_scim_cross_tenant.py`

Class `TestPostCrossTenantEmailEnumeration` (CT-16, 7 test methods):
- Same-tenant POST → 409 uniqueness (existing path still works)
- Cross-tenant POST → 400 invalidValue, email absent from body, warning logged,
  no user created in caller's tenant

---

## Changeset 2 — TASK-024 Group Provisioning Follow-ups

**File:** `backend/apps/users/scim_group_views.py`

Addressed all 5 non-blocking items from your `REVIEW-VERDICT-TASK-024-2026-04-23.md`:

| # | Item | Change |
|---|------|--------|
| 1 | `replace displayName` accepts empty string | Guard added → 400 invalidValue |
| 2 | Use `re.search` over `re.match` for `_MEMBER_FILTER_RE` | `.match(path)` → `.search(path)` |
| 3 | PATCH audit log op/path detail | Added `"ops": [{"op":…, "path":…}]` to changes dict |
| 4 | Drop `group.refresh_from_db()` after `members.set()` | Removed from POST, PUT, PATCH |
| 5 | Hoist local `TeacherGroup` imports | `from apps.courses.models import TeacherGroup` now at module top; 2 local imports removed |

---

## Note

`backend/run_tests.sh` (temp file flagged in TASK-024 review) could not be
deleted by the agent sandbox. Please delete manually: `rm backend/run_tests.sh`.

---

Please verify:
1. Two-tier uniqueness logic in `scim_views.py` matches the exact spec from the
   follow-up note.
2. CT-16 test assertions (especially `caplog` test and no-email-in-body test).
3. TASK-024 follow-up completeness.

— backend-engineer
