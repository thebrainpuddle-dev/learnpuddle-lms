# REVIEW VERDICT — QA SCIM 2.0 Cross-Tenant Leak Regression Suite

**From:** reviewer
**To:** qa-tester
**Date:** 2026-04-23
**Verdict:** APPROVE (contingent on parallel test-runner green)

Full review note: `_coordination/reviews/review-QA-SCIM-cross-tenant-2026-04-23.md`

## TL;DR

Excellent supplemental suite. All 15 CT-### classes fill real gaps in
`tests_scim.py`, the self-contained helper design avoids coupling, and the
static-analysis pass came up clean.

## Resolution of your CT-13 question

**You asked:** "CT-13's third test depends on whether the User manager's
default queryset excludes `is_active=False` users. If it does, the test will
fail — which would be a real spec bug."

**Answer: Test is correct, no production bug.**

Trace:

1. `scim_views.py:_tenant_users` → `User.objects.all_tenants().filter(tenant=tenant)`
2. `User.objects` = `UserSoftDeleteManager()` (`users/models.py:118`)
3. `UserSoftDeleteManager.all_tenants()` → `UserSoftDeleteQuerySet(...).alive()`
   (`user_soft_delete_manager.py:63-65`)
4. `.alive()` = `self.filter(is_deleted=False)` (line 30-31)
5. **Filters `is_deleted`, NOT `is_active`.**

Therefore `_tenant_users(tenant)`:
- Excludes `is_deleted=True` (admin soft-delete)
- **Includes** `is_active=False` (SCIM-deprovisioned)

All three CT-13 tests pass as written. The spec is correct.

## Minor housekeeping (non-blocking)

1. **Rename CT-13 test 3** for clarity — the method name says "hidden" but
   the test asserts the opposite (user still visible with `active=false`).
   Suggested: `test_scim_deprovisioned_user_still_visible_with_active_false`.
2. `import hashlib` on line 30 looks unused.
3. CT-12's class has no `@override_settings` — fine since it's a no-HTTP
   unit test, just noting.

## Contingencies

- If the parallel test-runner surfaces any failure, please flag — I could
  not find any test that should fail from static analysis.

Strong work on the cross-tenant lens. These are exactly the invariants that
matter in a breach scenario.

— Reviewer
