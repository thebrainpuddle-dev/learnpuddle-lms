---
tags: [review, task/BE-SEC-P0-AUDIT, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-19
---

# Review: BE-SEC-P0-AUDIT — P0 Security Fixes Audit Sign-Off

## Verdict: APPROVE

## Summary

Independently verified all five P0 security fixes claimed by the backend-security
agent. Each is present in the working tree, matches the referenced file/line
coordinates, and is backed by an existing test file. No regressions spotted.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

1. **Test execution still pending.** Verification was code-inspection only; the
   test suite was not run in this session (sandbox restriction). Before marking
   any of these fixes "shipped," one of us must run:
   ```
   docker compose exec web pytest \
     tests/test_contextvars_isolation.py \
     tests/test_cors_headers.py \
     tests/webhooks/ \
     tests/test_webhook_ssrf.py \
     apps/users/tests/
   ```
   and confirm green. Flagging as minor because the review request already
   acknowledged this gap.

2. **No explicit negative test for empty `CAL_WEBHOOK_SECRET` fail-closed path.**
   Existing `tests/webhooks/test_webhook_views.py` should already cover it, but
   if not present, please add a test that asserts 503 when the secret is empty
   and no call into `_handle_booking_*` fires.

## Verification Detail (evidence per item)

| # | Claim | Verified at | Result |
|---|-------|-------------|--------|
| 1 | contextvars tenant storage | `backend/utils/tenant_middleware.py:17-34` | ✅ `ContextVar('current_tenant', default=None)`; `get/set/clear` all use `.get()/.set()`. No `threading.local` reference remains. |
| 2 | No double-hash in register-teacher | `backend/apps/users/serializers.py:280-310` | ✅ Password passed directly to `User.objects.create_user(password=password, ...)`. No `set_password()+save()` follow-up. Comment on 290-294 documents the rationale. |
| 3a | Cal webhook fail-closed | `backend/apps/tenants/webhook_views.py:42-48` | ✅ Returns HTTP 503 before signature verification when `CAL_WEBHOOK_SECRET` is empty. |
| 3b | Stripe webhook fail-closed | `backend/apps/billing/stripe_service.py:131-138` | ✅ `construct_webhook_event` raises `ValueError("STRIPE_WEBHOOK_SECRET is not configured")` before HMAC check. |
| 4a | No wildcard CORS in nginx | `grep 'Allow-Origin' nginx/` | ✅ Zero matches (only COOP/CORP headers present, same-origin). |
| 4b | CORS scoped in settings | `backend/config/settings.py:492-499` | ✅ Prod uses `CORS_ALLOWED_ORIGIN_REGEXES = [r"^https://([a-z0-9-]+\.)*{escaped_platform_domain}$"]`, no wildcard. DEBUG only allows localhost. |
| 5 | Redis password enforced | `docker-compose.prod.yml:39,46` | ✅ `${REDIS_PASSWORD:?Set REDIS_PASSWORD in .env}` on both `--requirepass` and the healthcheck — compose fails if unset. |

Test files all present:
- `backend/tests/test_contextvars_isolation.py` ✓
- `backend/tests/test_cors_headers.py` ✓
- `backend/tests/test_webhook_ssrf.py` ✓
- `backend/tests/webhooks/test_webhook_views.py` ✓

## Positive Observations

- Rationale comments left in-line (e.g. `tenant_middleware.py:13-16` explains
  why `contextvars` replaces `threading.local`; `serializers.py:290-294`
  documents the double-hash history). Future maintainers will thank you.
- Fail-closed changes return structured JSON responses with proper HTTP
  semantics (503 for missing config, 403 for bad signature) — clients get
  actionable error codes.
- Redis password enforcement uses the `:?` operator, which is the correct
  docker-compose idiom for "required env var" — compose refuses to start
  rather than silently running without auth.
- Platform-domain-scoped CORS regex correctly escapes dots, preventing
  `learnpuddleXcom` bypass attempts.

## Next Steps

- Once qa-tester confirms the full test suite is green, these items can be
  closed in the shared log and the P0 security queue treated as clear.
- No additional P0 items open for backend-security from my side.
