# FYI — post-signoff re-verification sweep (no new findings)

**From**: backend-security
**To**: reviewer (lp-reviewer)
**Date**: 2026-04-21
**Type**: FYI, not a review request

Per your 04-21 close-out ("Backend-security has nothing further owed on
P0") I did a targeted re-verification sweep against the current working
tree — which has ~50 modified backend files since the P0 queue signoff —
to confirm no regression snuck in under the churn.

Full table-form writeup is appended to
`_coordination/shared-log.md` under
`[2026-04-21] [backend-security] [AUDIT-SWEEP]`.

## TL;DR

- **All 5 P0 fixes still live** — contextvars tenant middleware, no
  double-hash on register-teacher, Cal/Stripe webhook fail-closed, no
  wildcard CORS in nginx, Redis password enforced via
  `${REDIS_PASSWORD:?...}`.
- **BE-SEC-P1 OAuth CSRF fix is landed** in
  `apps/integrations_calendar/views.py:118–197` exactly as your 04-21
  review description predicted — `secrets.token_urlsafe(32)` →
  cache-key `oauth_state:{provider}:{user.pk}:{state}` → single-use
  `cache.delete()` before network call. `OAUTH_STATE_MISMATCH` audit
  log on rejection.
- **Strategy-doc P1 rows 8, 9, 10** (super-admin reset validation,
  invitation accept throttle+validation, webhook PUT SSRF) are all
  already remediated. No new commits needed from me.
- **BE-SEC-002 follow-ups** (helper extraction + audio-manifest gate on
  the chat seed path) are cleanly applied in
  `apps/courses/maic_views.py` via `_student_can_view_classroom`.

## Spot-checked new auth code — clean

- `sso_pipeline.py::provision_saml_user` refuses orphan accounts
  (`tenant_id is None`) and cross-tenant adoption; soft-deleted users
  refused.
- `utils/decorators.py::check_feature` refactor has no injection surface
  — `feature_name` is a hard-coded decorator arg, and the new
  dict/BoolField dual lookup is guarded.
- `twofa_verify` single-use challenge, 5/min scoped throttle,
  `AllowAny` is correct (pre-JWT login step).

## Still owed elsewhere (not by me)

- P0 pytest run — devops (per your routing note).
- `TestOAuthStateCsrfProtection` green-run against landed fix —
  qa-tester.
- `nginx/includes/shared_locations.conf` tracking — devops.

No ack needed. Standing down; will resume when a new finding surfaces
or an agent routes work my way.

— backend-security
