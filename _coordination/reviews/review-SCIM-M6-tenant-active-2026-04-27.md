---
tags: [review, task/TASK-023-followup-M6, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-27
---

# Review: TASK-023 Follow-up M6 — `tenant.is_active` guard in `SCIMToken.verify()`

## Verdict: APPROVE

## Summary
Tight, well-justified addition: a 7-line guard that closes a real
provisioning hole (suspended tenants accepting IdP writes) with zero extra
queries, two regression tests at the right layers (model + HTTP), and an
explicit design comment that captures the "why not also revoke the token"
trade-off. Ready to merge.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
None worth blocking on. Observations only:

1. **Log volume under attack scenarios.** A suspended tenant whose IdP keeps
   pushing SCIM traffic will produce one `WARNING` per request. This is
   consistent with the expiry-check log immediately above it, so the precedent
   is fine. If a noisy ex-tenant ever shows up in dashboards, the existing
   throttle layer (`scim_throttles.py`) is the right place to dampen it — not
   this guard.
2. **Test naming symmetry.** The model test is
   `test_verify_rejected_when_tenant_is_inactive`, the HTTP test is
   `test_inactive_tenant_token_returns_401`. Both read clearly; no change
   needed. Just noting that future SCIM auth tests should follow the
   `test_<scenario>_<expected_outcome>` pattern the HTTP suite already uses.

## Positive Observations

- **Guard placement is correct.** Sitting between expiry-check and
  `last_used_at` update means a suspended tenant doesn't refresh its
  "last active" telemetry — `last_used_at` stays a meaningful liveness
  signal. Good detail.
- **No extra DB query.** Verified at `scim_models.py:134` —
  `select_related("tenant")` already loads `scim_token.tenant`. The guard at
  line 186 reads from the already-hydrated relation. Zero perf cost.
- **Token row left untouched.** The design comment at lines 178–185 explicitly
  calls out that this is a tenant-lifecycle event, not a token-security event.
  Re-activating the tenant restores provisioning without forcing token
  rotation across every IdP. That's the right product call and the comment
  saves a future maintainer an hour of head-scratching.
- **Field exists.** Confirmed `Tenant.is_active = BooleanField(default=True)`
  at `apps/tenants/models.py:81`, indexed at line 271. Guard cannot blow up
  on a missing attribute.
- **Two-layer test coverage.**
  - Unit (`tests_scim.py:142`) pins the model behavior — any future refactor
    that drops the guard fails this test directly.
  - Integration (`tests_scim.py:219`) confirms the model rejection
    propagates to a 401 at the HTTP boundary. Both happy and sad paths
    already exist in the surrounding suite (`test_valid_token_grants_access`,
    `test_revoked_token_returns_401`), so this slots in cleanly.
- **Logging discipline.** No raw token, no PII — just `token_id` and
  `tenant_id`, matching the surrounding warnings.
- **Test count matches.** `tests_scim.py` is at 72 test methods (was 70),
  consistent with the +2 claimed in the request.

## Verification performed

- Read full `backend/apps/users/scim_models.py` — guard logic, ordering,
  and select_related coverage all check out.
- Read both new tests at `tests_scim.py:142` and `:219` — assertions
  target the right behavior, fixtures use the existing `_make_tenant` /
  `_make_admin` helpers, no implementation-coupling.
- Confirmed `Tenant.is_active` field and index exist.
- Docker test execution deferred to qa-tester (already routed; see
  `QA-SCIM-M6-STATIC-VERIFIED-2026-04-27.md`). Static verification by qa
  agrees with this review.

— reviewer
