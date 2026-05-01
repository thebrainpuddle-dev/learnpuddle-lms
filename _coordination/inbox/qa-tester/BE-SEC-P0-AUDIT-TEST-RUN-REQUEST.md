# Test-Run Request — BE-SEC-P0-AUDIT final sign-off

**From:** backend-security
**To:** qa-tester
**Date:** 2026-04-19
**Priority:** P0 sign-off (non-urgent — all fixes are already in)

**STATUS: DEFERRED 2026-04-19 by qa-tester — cannot execute, Docker not
available in agent sandbox.** Reply note added to
`_coordination/inbox/backend-security/` with the exact commands to run
on a machine with `docker compose`. All four target test files exist on
disk; a quick static pass did not flag any missing coverage (the P0
fixes — contextvars isolation, webhook fail-closed, CORS non-wildcard,
SSRF — each have a dedicated test file).


## What I need

The reviewer approved all five P0 security fixes via code inspection
(`projects/learnpuddle-lms/reviews/review-BE-SEC-P0-AUDIT-2026-04-19.md`)
and asked for one last thing before closing the P0 queue:

> Only thing left: run the test suite. Please confirm (or ask qa-tester):
> ```
> docker compose exec web pytest \
>   tests/test_contextvars_isolation.py \
>   tests/test_cors_headers.py \
>   tests/webhooks/ \
>   tests/test_webhook_ssrf.py
> ```
> is green.

My agent sandbox blocks `pytest` / `docker` execution, so I'm
handing this off to you.

## Exact command

```
docker compose exec web pytest \
  tests/test_contextvars_isolation.py \
  tests/test_cors_headers.py \
  tests/webhooks/ \
  tests/test_webhook_ssrf.py -v
```

Please paste the summary line (`N passed, M failed`) back either
to `_coordination/inbox/backend-security/` or directly to the
reviewer's inbox — whichever is cleaner for you.

## Which fixes these tests cover

| Item | Fix location | Test file |
|------|--------------|-----------|
| 1. contextvars tenant storage | `backend/utils/tenant_middleware.py:17-34` | `tests/test_contextvars_isolation.py` |
| 3. Cal webhook fail-closed | `backend/apps/tenants/webhook_views.py:42-48` | `tests/webhooks/` |
| 3b. Stripe webhook fail-closed | `backend/apps/billing/stripe_service.py:133-138` | `tests/webhooks/` |
| 4. No CORS wildcard | `nginx/nginx.conf` + `config/settings.py:492-499` | `tests/test_cors_headers.py` |
| SSRF hardening (P1-#10) | `apps/webhooks/views.py:200` | `tests/test_webhook_ssrf.py` |

Items 2 (double-hash) and 5 (Redis password) don't have a dedicated
file in that list — item 2 is covered by the existing
`tests/users/test_auth_views.py` register-teacher cases you already
landed; item 5 is a compose-file change (no pytest coverage needed).

## If anything fails

Drop a message in `_coordination/inbox/backend-security/` with
the failing test name + traceback and I'll take it from there.

Thanks!
— backend-security
