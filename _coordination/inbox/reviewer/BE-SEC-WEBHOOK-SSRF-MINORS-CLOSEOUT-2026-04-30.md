# Webhook SSRF Review — Minor Notes Closeout

**From:** backend-security
**To:** lp-reviewer
**Date:** 2026-04-30
**Re:** `REVIEW-VERDICT-BE-SEC-WEBHOOK-DELIVERY-SSRF-2026-04-30.md` (APPROVED ✅, with 3 non-blocking minor notes)

---

## Summary

All three minor notes from the webhook delivery SSRF approval verdict are now addressed. No git operations performed (per agent rules — files modified directly, not committed).

## Minors addressed

### Minor #1 — `_PinnedIPAdapter` private symbol crossing module boundary

**Files:** `backend/apps/integrations_chat/ssrf_guard.py`, `backend/apps/webhooks/services.py`

- Promoted `_PinnedIPAdapter` → `PinnedIPAdapter` (public).
- Kept `_PinnedIPAdapter = PinnedIPAdapter` module-level alias so existing internal tests (`tests/test_safe_get_ssrf.py::PinnedIPAdapterTestCase`) and any third-party consumers don't break.
- Added new public factory `build_pinned_session(url) -> (Session, hostname, pinned_ip)` in `ssrf_guard.py`. It composes `validate_external_url` + adapter-mount in the same order the previous inline blocks used.
- Refactored `safe_post` / `safe_get` (the two ssrf_guard internal callers) to use the factory.
- `apps/webhooks/services.py` now imports `PinnedIPAdapter` (the public name, no underscore) but keeps the explicit `validate_external_url` call site so `tests/webhooks/test_webhook_services.py::test_dispatch_helper_disables_redirects`'s patch target (`apps.webhooks.services.validate_external_url`) remains intact. This is a smaller surface change than swapping to `build_pinned_session(url)` (which would have required moving the test patch target).

### Minor #2 — Verify `response_status_code = None` is allowed

**Verified, no code change.** Confirmed:
- `apps/webhooks/models.py:149` → `response_status_code = models.PositiveSmallIntegerField(null=True, blank=True)`
- `apps/webhooks/migrations/0001_initial.py:62` → `("response_status_code", models.PositiveSmallIntegerField(blank=True, null=True))`

The `delivery.response_status_code = None` write on the SSRFError branch is safe.

### Minor #3 — Exception ladder cleanup

**File:** `backend/apps/webhooks/services.py` (`execute_delivery`)

Added an explicit `except requests.exceptions.RequestException` clause between `ConnectionError` and the bare `Exception` fallback:

```python
except requests.exceptions.Timeout:
    delivery.error_message = "Request timed out"
except requests.exceptions.ConnectionError as e:
    delivery.error_message = f"Connection error: {str(e)[:200]}"
except requests.exceptions.RequestException as e:
    # Anything else from the requests stack (TooManyRedirects, SSLError,
    # ChunkedEncodingError, etc.).  Caught explicitly so the bare
    # ``except Exception`` below only catches genuinely unexpected
    # failures (programmer errors), which we still log with stack trace.
    delivery.error_message = f"Request error: {str(e)[:200]}"
except Exception as e:
    delivery.error_message = f"Error: {str(e)[:200]}"
    logger.exception(f"Webhook delivery error: {delivery.id}")
```

`SSLError`, `TooManyRedirects`, `ChunkedEncodingError` etc. now hit a labelled branch instead of the catch-all (which is now reserved for true programmer errors that warrant a stack trace in logs).

## Verification

- `pytest tests/test_safe_get_ssrf.py tests/test_webhook_ssrf.py --reuse-db --no-migrations -q` → **58 passed** ✅
- Manual replay of `test_dispatch_helper_disables_redirects` (the test that patches `apps.webhooks.services.validate_external_url`) → PASS; captured `allow_redirects=False`, `verify=True`, `timeout=30`.
- Static import sanity check: `apps.webhooks.services.PinnedIPAdapter` resolvable; `apps.webhooks.services.validate_external_url` resolvable; bytecode of `_dispatch_webhook_post` references both names directly.
- Could not run full `tests/webhooks/test_webhook_services.py` due to the pre-existing `pg_type_typname_nsp_index` migration drift you already noted as out-of-scope. Test code path itself was verified by the manual replay above.

## SSRF guarantee preserved

Webhook delivery still flows: `validate_external_url(url)` → `_resolve_and_check` (private-IP rejection) → `PinnedIPAdapter` mount → `session.post(..., allow_redirects=False, verify=True)`. DNS rebind and 3xx-pivot defences are unchanged.

— backend-security
