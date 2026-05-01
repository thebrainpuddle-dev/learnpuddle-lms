# REVIEW REQUEST — P0 Security Fixes Audit (all 5 items)

**From**: backend-security
**Date**: 2026-04-19
**Branch**: `maic-sprint-1-presence-rhythm`
**Severity**: P0 (platform-wide critical fixes)
**Action requested**: Independent verification / sign-off

---

## Summary

Audited all five P0 security items listed in the backend-security agent definition. **All five are already patched in the working tree.** I made **no new code changes** — the fixes landed in prior sessions. I verified each by code inspection against the existing test suites authored by qa-tester.

| # | Issue | File(s) | Status |
|---|-------|---------|--------|
| 1 | Thread-local → contextvars tenant storage | `backend/utils/tenant_middleware.py` | ✅ FIXED |
| 2 | Double password hashing (RegisterTeacherSerializer) | `backend/apps/users/serializers.py` | ✅ FIXED |
| 3 | Webhook fail-open when secret empty | `backend/apps/tenants/webhook_views.py` + `backend/apps/billing/stripe_service.py` | ✅ FIXED |
| 4 | HLS / media CORS wildcard | `nginx/includes/shared_locations.conf` + `backend/config/settings.py` | ✅ FIXED |
| 5 | Default Redis password in prod compose | `docker-compose.prod.yml` | ✅ FIXED |

Full evidence for each item is in `_coordination/shared-log.md` under the `[backend-security] 2026-04-19 — VERIFIED — P0 security fixes audit` entry.

---

## What to verify

1. **Contextvars isolation**: `backend/utils/tenant_middleware.py:17-34` uses `contextvars.ContextVar`, not `threading.local`. Covered by `tests/test_contextvars_isolation.py`.
2. **No double-hash on teacher create**: `backend/apps/users/serializers.py:280-310` passes `password` directly to `create_user()`. No lingering `set_password()+save()`.
3. **Cal webhook fail-closed**: `backend/apps/tenants/webhook_views.py:40-48` returns 503 when `CAL_WEBHOOK_SECRET` is empty, **before** signature check. Stripe equivalent in `backend/apps/billing/stripe_service.py:131-138`.
4. **No wildcard CORS**: `grep -r 'Allow-Origin.*\*' nginx/` returns nothing. `backend/config/settings.py:460-508` uses `CORS_ALLOWED_ORIGIN_REGEXES` scoped to `{platform_domain}`.
5. **Redis password enforced**: `docker-compose.prod.yml:39,46` uses `${REDIS_PASSWORD:?Set REDIS_PASSWORD in .env}` — compose refuses to start with unset password.

---

## Tests

All tests were authored by **qa-tester** (see `2026-04-19` shared-log entry — 210/211 previously passing; the 1 failure was BE-SEC-001 `tenant_me` leak which backend-engineer has since fixed):

- `backend/tests/test_contextvars_isolation.py` — ASGI coroutine isolation
- `backend/tests/test_cors_headers.py` — wildcard never returned, attacker origins rejected
- `backend/tests/test_webhook_ssrf.py` — outgoing webhook SSRF
- `backend/tests/webhooks/test_webhook_views.py` — cross-tenant isolation, CRUD
- `backend/tests/users/test_auth_views.py` — register-teacher login flow

I was unable to run `pytest` in this session (sandboxed bash blocked; docker compose is the canonical runner). Please confirm via `docker compose exec web pytest tests/test_contextvars_isolation.py tests/test_cors_headers.py tests/webhooks/ tests/test_webhook_ssrf.py`.

---

## Nothing committed

Per the backend-security agent policy (no `git add/commit/push`), I did **not** stage or commit anything. Reviewer/backend-engineer own the commit flow for any staging of these verified fixes.

---

## Open items on backend-security: none

All five P0 items from the agent definition are closed. No blockers open. Reassign or ping me when new security work is queued.

## Processed 2026-04-19

Already reviewed — **APPROVED** at
`projects/learnpuddle-lms/reviews/review-BE-SEC-P0-AUDIT-2026-04-19.md`
(08:02). Closing out of queue.
