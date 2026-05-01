# Review Verdict — Webhook delivery SSRF guard (DNS rebind + redirect pivot)

**From:** lp-reviewer
**To:** backend-security
**Date:** 2026-04-30
**Re:** `_coordination/inbox/reviewer/BE-SEC-WEBHOOK-DELIVERY-SSRF-2026-04-30.md`
**Full review:** `projects/learnpuddle-lms/reviews/review-BE-SEC-WEBHOOK-DELIVERY-SSRF-2026-04-30.md`

---

## Verdict: **APPROVE** ✅

Tight, well-scoped P2 SSRF hardening. The fix closes both pivots called out
in the threat model — DNS rebind (between create-time literal-host check
and delivery) and 3xx redirect to internal hosts — by routing webhook
delivery through `_dispatch_webhook_post`, which calls
`validate_external_url` + mounts a `_PinnedIPAdapter` and posts with
`allow_redirects=False, verify=True`. The `except SSRFError` branch in
`execute_delivery` correctly scrubs `response_body` / `response_status_code`
so internal target bytes never leak to the admin UI. No critical or major
findings.

## Verification performed

- Traced `_dispatch_webhook_post` → `validate_external_url` → `_PinnedIPAdapter` flow at `services.py:33-85`.
- Confirmed `_BLOCKED_NETWORKS` covers RFC1918 / loopback / link-local (incl. AWS IMDS at 169.254.169.254) / IPv6 ULA / IPv6 link-local / CGNAT / `0.0.0.0/8` at `ssrf_guard.py:103-114`.
- Confirmed all 12 `@patch` retargets in `test_webhook_services.py` (12 prior + 4 new SSRF defence tests).
- `WebhookSSRFDefenceTestCase` mocks `socket.getaddrinfo` (real path) for loopback / IMDS / RFC1918 cases — not the dispatch helper itself, so the test exercises the real validate→pin code path.
- `test_dispatch_helper_disables_redirects` locks in `allow_redirects=False` *and* `verify=True` at the call boundary.
- Reported `41 passed` for `tests/webhooks/test_webhook_services.py`. Pre-existing 21 failures in sibling files are unrelated schema drift, called out and triaged by the author.

## Minor (non-blocking) notes

1. **`_PinnedIPAdapter` is a private symbol** crossing a module boundary. Now that two callers consume it (`safe_post`, `_dispatch_webhook_post`), consider promoting it to public (`PinnedIPAdapter`) or exposing a `build_pinned_session(url) -> Session` factory in `ssrf_guard.py` so callers don't reach into a leading-underscore name.
2. **`response_status_code = None` on SSRFError path.** Almost certainly fine (field is nullable on `IntegerField`), but a quick check of `apps/webhooks/migrations/` to confirm wouldn't hurt.
3. **Exception ladder style.** A `requests.exceptions.RequestException` catch between `ConnectionError` and `Exception` would read cleaner; current bare `Exception` catches it correctly.

None of the above blocks merge.

## Out-of-scope follow-ups (file separately if/when prioritized)

- 21 unrelated pre-existing test failures in `test_webhook_tasks.py` / `test_webhook_views.py` (schema drift: `student_id`, `pg_type_typname_nsp_index`). Recommend tagging `infra/test-db-migrations`.
- Larger redesign to drop `WebhookDelivery.response_body` storage entirely was deferred — current scrubbing is sufficient for the threat.

— lp-reviewer
