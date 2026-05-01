# Review Request: Webhook delivery SSRF guard (DNS rebind + redirect pivot)

**From:** backend-security
**To:** reviewer
**Date:** 2026-04-30
**Severity:** P2 (admin-gated SSRF + internal-data exfil to admin UI)
**Status changes:** working tree only — not committed (backend-security agent
rules forbid `git add`/`commit`/`push`).

## Summary

Tenant-admin-configured webhook URLs were validated only at create time
(literal-hostname check). At delivery time `apps/webhooks/services.py:execute_delivery`
called `requests.post(endpoint.url, …)` with default `allow_redirects=True`
and no IP pinning. A school-admin (or attacker who phished one) could:

1. **DNS rebind**: register `attacker.example` pointing at a public IP at
   create time, then flip DNS to `169.254.169.254` (AWS IMDS) or
   `127.0.0.1`. Internal target's response body — truncated to 5000 chars
   — was persisted on `WebhookDelivery.response_body` and rendered in the
   admin UI.
2. **Redirect pivot**: legitimate external server returns `302` to an
   internal URL; `requests` follows; same internal-body leak.

## Fix

### `backend/apps/webhooks/services.py`

- Added module-level imports for `SSRFError`, `_PinnedIPAdapter`,
  `validate_external_url` from `apps.integrations_chat.ssrf_guard`.
- New helper `_dispatch_webhook_post(url, *, data, headers, timeout)`:
  - Calls `validate_external_url(url)` — rejects scheme≠http(s), and
    rejects resolved IPs in RFC1918, loopback, link-local, CGNAT, IPv6
    ULA, IPv6 link-local, and `0.0.0.0/8`.
  - Pins the resolved IP into a `_PinnedIPAdapter`-mounted `requests.Session`
    so the actual TCP connect cannot land on a different IP (defeats DNS
    rebind between resolution and connect).
  - Calls `session.post(url, …, allow_redirects=False, verify=True)`.
    Original hostname preserved on the pinned `HTTPSConnection.host` →
    SNI + cert validation still pin to the user's expected certificate.
- `execute_delivery` updated:
  - Calls the new helper instead of `requests.post`.
  - New `except SSRFError as e:` branch — scrubs `response_body` and
    `response_status_code` so no internal data leaks even if a prior
    attempt left some on the row, then handles the failure via the
    existing failed/retrying branch.
  - Comment in the success branch explains why 3xx is no longer followed
    (now an explicit error, response_body of internal target never
    exposed).

### `backend/tests/webhooks/test_webhook_services.py`

- 12 `@patch("apps.webhooks.services.requests.post")` decorators retargeted
  to `@patch("apps.webhooks.services._dispatch_webhook_post")`. Call
  signature is preserved (`url` positional, `data=`, `headers=`, `timeout=`
  kwargs) and the mocked-response contract (object with `.status_code` /
  `.text`) is unchanged, so no assertion bodies needed editing.
- Updated `ExecuteDeliveryTestCase` docstring to explain the patch target
  rationale.
- New `WebhookSSRFDefenceTestCase` (4 tests):
  1. `test_dns_rebind_to_loopback_blocked` — `127.0.0.1` rebind blocked,
     `response_body` left empty.
  2. `test_dns_rebind_to_aws_imds_blocked` — `169.254.169.254` rebind
     blocked.
  3. `test_dns_rebind_to_rfc1918_blocked` — `10.0.0.5` rebind blocked.
  4. `test_dispatch_helper_disables_redirects` — verifies
     `allow_redirects=False` and `verify=True` are passed to `session.post`.

## Verification

```
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest \
  tests/webhooks/test_webhook_services.py --no-migrations --create-db -q
# 41 passed in 57.74s
```

Smoke-test of the helper (run from `backend/`):

```
.venv/bin/python -c "
import django; django.setup()
from unittest.mock import patch
from apps.webhooks import services as ws
with patch('apps.integrations_chat.ssrf_guard.socket.getaddrinfo') as m:
    m.return_value = [(2, 1, 6, '', ('127.0.0.1', 0))]
    try:
        ws._dispatch_webhook_post('https://x.example/h', data='{}', headers={}, timeout=5)
        print('FAIL'); 
    except ws.SSRFError as e:
        print('OK:', e)
"
# OK: SSRF_BLOCKED: 'x.example' resolves to private/loopback address '127.0.0.1'
```

## Out of scope (not addressed in this change)

- `apps/webhooks/services.py:trigger_webhook` and the per-endpoint stats
  update path — both already filter by `tenant`, no SSRF surface.
- `apps/billing/webhook_views.py` and `apps/tenants/webhook_views.py` —
  these are *inbound* webhooks (Stripe / Cal.com), already covered by
  signature verification + fail-closed-on-empty-secret.
- `WebhookDelivery.response_body` schema change to drop the storage
  entirely — would be a larger surgery; current scrubbing on the SSRF
  branch is sufficient since legitimate external targets' bodies are
  still safe (admin-controlled).

## Pre-existing test failures (NOT introduced by this change)

`tests/webhooks/test_webhook_tasks.py` and
`tests/webhooks/test_webhook_views.py` show ~21 failures during my run
all caused by:

```
django.db.utils.ProgrammingError: column "student_id" of relation "users" does not exist
django.db.utils.IntegrityError: duplicate key … "pg_type_typname_nsp_index" … staff_certifications
```

These are local-DB schema drift between the model and the cached test
DB (latest migrations not applied to test DB). They reproduce before the
test functions even start, on every test in those files, and are
unrelated to webhook services. Recommend triaging separately.

## Files changed

| File | Change |
|------|--------|
| `backend/apps/webhooks/services.py` | +73 / -8 — SSRF helper + execute_delivery hook |
| `backend/tests/webhooks/test_webhook_services.py` | +95 / -1 — patch retargets + 4 new SSRF tests + docstring |

— backend-security
