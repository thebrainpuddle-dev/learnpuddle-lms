---
tags: [review, task/BE-SEC-WEBHOOK-DELIVERY-SSRF, verdict/approve, reviewer/lp-reviewer, security]
created: 2026-04-30
---

# Review: BE-SEC-WEBHOOK-DELIVERY-SSRF — Webhook delivery SSRF guard (DNS rebind + redirect pivot)

## Verdict: APPROVE

## Summary
Tight, well-scoped P2 SSRF hardening that closes both the DNS-rebind and 3xx-redirect pivots at delivery time. Reuses the already-vetted `validate_external_url` + `_PinnedIPAdapter` machinery from `apps/integrations_chat/ssrf_guard.py`, so the new code surface is small and the risk is low. Test coverage demonstrates the actual threat-model: loopback, AWS IMDS, and RFC1918 rebinds are all blocked, and `allow_redirects=False` / `verify=True` are explicitly asserted at the dispatch layer.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **Direct import of a private symbol (`_PinnedIPAdapter`).** `apps/webhooks/services.py:22-26` imports `_PinnedIPAdapter` (leading underscore) across module boundaries. The current implementation is fine and the docstring on the adapter is thorough, but the underscore signals "internal." Consider promoting it to a public name (`PinnedIPAdapter`) in `ssrf_guard.py` now that two modules consume it — or expose a small public factory (`build_pinned_session(url) -> Session`) so callers don't need the adapter directly. Non-blocking; the present import works.

2. **`response_status_code = None` on SSRFError path.** `services.py:253` sets `response_status_code = None`, which the existing migration likely permits (the field is nullable on a Postgres `IntegerField`). Not verified in this review — if the column is non-nullable, the `delivery.save()` at line 279 would crash. A quick grep of `apps/webhooks/migrations/` would confirm. Noted for the author rather than blocking — the rest of the test suite passes 41/41 so this is almost certainly fine in practice.

3. **`requests.exceptions.RequestException` not explicitly caught.** A bare `Exception` catch at `services.py:262` will catch it, so behavior is correct. Just stylistic — the exception ladder reads cleaner with `RequestException` between `ConnectionError` and the bare `Exception`.

## Positive Observations

- **Threat model documented inline.** The `_dispatch_webhook_post` docstring (lines 40-72) and the explanatory comment at lines 226-230 explain *why* `allow_redirects=False` is now load-bearing — exactly the kind of context a future reader needs to avoid "simplifying" the bug back in.
- **Response scrubbing on the SSRF branch.** `delivery.response_body = ""` and `response_status_code = None` (lines 252-253) defend against the actual exfil vector — the admin UI rendering truncated internal target bodies. The comment at lines 247-250 calls this out.
- **Test patches retargeted, not duplicated.** Migrating the 12 existing `@patch("requests.post")` decorators to `@patch("apps.webhooks.services._dispatch_webhook_post")` keeps a single seam for mocking, and the docstring on `ExecuteDeliveryTestCase` (lines 267-273) explains why.
- **`WebhookSSRFDefenceTestCase` exercises the real flow.** Mocking `socket.getaddrinfo` instead of mocking the dispatch helper means the test goes through the *actual* validate→pin code path — that's the right test depth for a regression suite.
- **`test_dispatch_helper_disables_redirects`** locks in both `allow_redirects=False` and `verify=True` at the call boundary. This is exactly the kind of assertion that catches future "let me just turn redirects back on for convenience" regressions.
- **Pre-existing failures called out and triaged.** The 21 unrelated `student_id` / `pg_type_typname_nsp_index` failures in `test_webhook_tasks.py` / `test_webhook_views.py` are flagged as schema drift and explicitly disclaimed. Good submitter discipline.

## Verification Performed

- Confirmed `_dispatch_webhook_post` calls `validate_external_url` → `_PinnedIPAdapter` → `session.post(..., allow_redirects=False, verify=True)`.
- Confirmed `execute_delivery` wraps the call in a new `except SSRFError` branch that scrubs `response_body` / `response_status_code` before falling through to the existing failed/retrying logic.
- Confirmed `_BLOCKED_NETWORKS` in `ssrf_guard.py:103-114` covers RFC1918, loopback (v4 & v6), link-local (v4 & v6, including IMDS), CGNAT, IPv6 ULA, and `0.0.0.0/8` — matches the threat list in the request.
- Confirmed all 4 new SSRF tests assert the right things (loopback rebind blocked, IMDS rebind blocked, RFC1918 rebind blocked, dispatch options correct).
- Author reports `41 passed` for `tests/webhooks/test_webhook_services.py`. Pre-existing failures in sibling files are unrelated and out of scope.

## Notes for Author

- The OBS list ("Out of scope") is appropriate. `WebhookDelivery.response_body` storage redesign would be a larger change; the scrubbing-on-error approach is sufficient for the current threat.
- The pre-existing test failures (`test_webhook_tasks.py`, `test_webhook_views.py`) should be filed as a separate ticket — recommend tagging it `infra/test-db-migrations` so it lands with the next migration sweep.

— lp-reviewer
