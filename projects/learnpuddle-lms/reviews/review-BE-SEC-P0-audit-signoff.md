---
tags: [review, task/BE-SEC-P0, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-19
---

# Review: BE-SEC P0 Fixes Audit — Independent Sign-off

## Verdict: APPROVE (code-inspection sign-off; pytest execution still required before ship)

## Summary

Backend-security reported all five P0 security items already patched in the
working tree with no new code changes. I independently verified each fix by
direct code inspection and cross-checked against the backing test files. All
five patches are correct and match the intended threat model. I could not
execute `pytest` in this environment (docker not installed) — the author is
responsible for re-running `docker compose exec web pytest` against the
listed suites and confirming green before the branch ships.

---

## Verification — item by item

### 1. Thread-local → contextvars tenant storage ✅

**File**: `backend/utils/tenant_middleware.py:17-34`

```python
_current_tenant: contextvars.ContextVar = contextvars.ContextVar(
    'current_tenant', default=None
)
```

- `contextvars.ContextVar` is task-local in asyncio/Channels, unlike
  `threading.local()` which would leak across coroutines sharing one OS
  thread.
- `get_current_tenant`, `set_current_tenant`, `clear_current_tenant`
  correctly use `.get()` / `.set()`.
- Inline comment explicitly documents the ASGI rationale — future-proofs
  against a regression.
- Backing test: `backend/tests/test_contextvars_isolation.py` exists.

**Verdict**: correct.

### 2. No double-hash in RegisterTeacherSerializer ✅

**File**: `backend/apps/users/serializers.py:280-310`

```python
user = User.objects.create_user(
    **validated_data,
    password=password,
    tenant=tenant,
    role='TEACHER'
)
```

- Single call path: password is passed straight to `create_user`, which
  internally invokes `set_password`. No follow-up `set_password()` + `save()`.
- Well-commented explanation of why the old pattern was dangerous.
- Backing test: `backend/tests/users/test_auth_views.py` exists.

**Verdict**: correct.

### 3. Webhook fail-closed when secret empty ✅

**Cal.com** — `backend/apps/tenants/webhook_views.py:42-48`

```python
cal_secret = getattr(settings, "CAL_WEBHOOK_SECRET", "")
if not cal_secret:
    logger.error("cal_webhook: CAL_WEBHOOK_SECRET not configured — rejecting request")
    return Response({"error": "Webhook not configured"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE)
```

Check is **before** the signature path — attacker can't bypass by omitting
the secret. `_verify_cal_signature` also returns `False` if secret empty
(belt-and-braces).

**Stripe** — `backend/apps/billing/stripe_service.py:133-138`

```python
if not settings.STRIPE_WEBHOOK_SECRET:
    raise ValueError("STRIPE_WEBHOOK_SECRET is not configured")
return s.Webhook.construct_event(
    payload, sig_header, settings.STRIPE_WEBHOOK_SECRET, ...
)
```

Raises before handing to `stripe` lib — also fail-closed.

Backing tests: `backend/tests/webhooks/test_webhook_views.py`,
`backend/tests/test_webhook_ssrf.py`.

**Verdict**: correct.

### 4. HLS / media CORS wildcard removed ✅

- `grep -rn 'Access-Control-Allow-Origin' nginx/` → no matches. The wildcard
  header is gone from nginx entirely; dynamic origin handling is delegated
  to Django.
- `backend/config/settings.py:471-499` only ever sets
  `CORS_ALLOWED_ORIGIN_REGEXES` (never `CORS_ALLOW_ALL_ORIGINS = True`), and
  lines 502–506 hard-fail boot in non-DEBUG if no origins are configured —
  no silent permissive fallback.
- `backend/apps/courses/video_views.py:389-440` shows per-request origin
  echo for HLS with an allowed-origin gate (tenant-scoped).
- Backing tests in `backend/tests/test_cors_headers.py` enforce:
  "no response must ever contain `Access-Control-Allow-Origin: *`" and
  "attacker origin is rejected".

**Verdict**: correct.

### 5. Default Redis password in prod compose ✅

**File**: `docker-compose.prod.yml:39,46`

```yaml
--requirepass ${REDIS_PASSWORD:?Set REDIS_PASSWORD in .env}
test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD:?Set REDIS_PASSWORD in .env}", "ping"]
```

`${VAR:?message}` causes Compose to abort startup with the message if
`REDIS_PASSWORD` is unset or empty — impossible to accidentally boot prod
with a default / blank password.

**Verdict**: correct.

---

## Gaps I could not close

- **Pytest run**: I cannot execute `docker compose exec web pytest …` in
  this review session. The audit's code inspection is high-confidence, but
  the canonical proof is the green suite. Before this branch ships, please
  run:

  ```bash
  docker compose exec web pytest \
    tests/test_contextvars_isolation.py \
    tests/test_cors_headers.py \
    tests/webhooks/ \
    tests/test_webhook_ssrf.py \
    apps/users/
  ```

  …and attach the summary to the deploy ticket.

- **SSRF allow-list**: backend-security's note mentions
  `test_webhook_ssrf.py` for outgoing webhook SSRF. I did not re-derive the
  allow-list — trusting the existing test coverage. If a new outgoing
  webhook is added in a future PR, verify it still goes through the SSRF
  guard.

---

## Positive Observations

- Each fix has an explanatory comment in-tree, not just a commit message —
  future maintainers will understand why the pattern looks unusual
  (contextvars, fail-closed order, etc.). That's the right way to harden a
  codebase.
- The settings.py fail-fast on missing CORS config (lines 502-506) is a
  particularly nice defense-in-depth addition beyond just removing the
  wildcard.
- `${VAR:?…}` for REDIS_PASSWORD is the idiomatic Compose pattern — much
  better than a default string with a warning log.

## Nothing committed

As required by the reviewer agent charter, I made no code changes and ran
no git write operations. This review is code-inspection sign-off only.

— lp-reviewer
