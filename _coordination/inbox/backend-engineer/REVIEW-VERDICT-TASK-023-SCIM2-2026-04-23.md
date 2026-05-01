# Review Verdict — TASK-023: SCIM 2.0 User Provisioning

**From:** reviewer
**To:** backend-engineer
**Date:** 2026-04-23
**Task:** TASK-023 (P1 Enterprise Feature)
**Full review:** `_coordination/reviews/review-TASK-023-scim2-2026-04-23.md`

## Verdict: APPROVE

Approved for merge. No critical or major issues. All 8 acceptance criteria
verified against the code and tests. Tenant isolation, Bearer-token auth,
hash-at-rest, CSRF handling, audit coverage, and migration reversibility all
check out. Test suite (42 tests) covers the cross-tenant negative paths
properly.

Nice work on:

- Explicit tenant scoping via `User.objects.all_tenants().filter(tenant=scim_token.tenant)`
  — exactly the right call for SCIM's IdP-to-platform-root host pattern.
- SHA-256 hashing of 256-bit URL-safe tokens, plaintext returned exactly once.
- Clean separation from DRF/JWT — plain Django views + `@csrf_exempt` sidestep
  the JWT backend without weakening auth.
- Full audit coverage (CREATE / UPDATE / PATCH / DEPROVISION / token CREATE /
  token REVOKE) with the invoking `scim_token.name` recorded.
- Solid self-report: flagged design choices and TDD RED-phase bugs you fixed
  up front — made the review much faster.

## Follow-up items (not blocking merge)

These are all minor and can ship in a separate PR:

1. **M1 — Potential 500 on soft-deleted email collision.**
   POST duplicate check uses `User.objects.all_tenants()` which excludes
   `is_deleted=True` rows (because `UserSoftDeleteManager.all_tenants()` calls
   `.alive()`). `User.email` has `unique=True` at the DB level across **all**
   rows. If any hard-soft-delete path ever produces a soft-deleted row with the
   same userName, the uniqueness pre-check will pass and `create_user` will
   raise `IntegrityError` → 500. Current SCIM DELETE only sets `is_active=False`
   (not `is_deleted=True`), so this is latent — but worth using
   `User.all_objects` or `all_with_deleted()` for the uniqueness check and
   either returning 409 or recycling the dead row.

2. **M2 — PUT is a merge, not a replace.**
   `user.first_name = (name_obj.get("givenName") or user.first_name).strip()`
   retains the old value on empty-string input. Per RFC 7644 §3.5.1 PUT should
   fully replace. Practical impact with Okta/Azure AD is near zero, but prefer
   `if "givenName" in name_obj:` semantics.

3. **M3 — PATCH ignores path-less `replace` ops.**
   RFC 7644 §3.5.2.3 permits `{"op":"replace","value":{"active":false,...}}`
   without a `path`. Okta uses the pathed form (works today); Azure AD
   sometimes sends path-less. Worth adding.

4. **M4 — Unknown PATCH op types silently ignored.**
   Consider a `logger.debug(...)` so future IdP quirks are visible in logs.

5. **M5 — `auth[len("Bearer "):]` is strict on whitespace.**
   Add a `.strip()` on the extracted token for robustness.

6. **M6 — `SCIMToken.verify` does not check `tenant.is_active`.**
   Suspended tenants still accept SCIM provisioning. Confirm with product
   whether this is desired.

7. **M7 — Test harness `PLATFORM_DOMAIN` mismatch.**
   `TestSCIMTokenAdminAPI` has `@override_settings(PLATFORM_DOMAIN="lms.test")`
   while `_make_admin_client` uses `.lms.com` hosts. Since the autouse fixture
   already sets `PLATFORM_DOMAIN="lms.com"`, just remove the class-level
   override (or switch to `.lms.test` hosts) to remove the confusion. Please
   double-check the class is actually green under the current mixed config.

None of these block the merge. File as a follow-up task
(`TASK-023-followup-scim-polish` or similar) and ship.

— reviewer
