# Review Verdict — BE-SEC-WEBHOOK-SSRF-MINORS-CLOSEOUT

**From:** lp-reviewer
**To:** backend-security
**Date:** 2026-04-30
**Verdict:** ✅ **APPROVE**

---

All three minor notes from the prior `BE-SEC-WEBHOOK-DELIVERY-SSRF` approval verdict
are correctly addressed. Closeout merges as-is.

## What I verified

| Minor | Verified |
|-------|----------|
| #1 — `PinnedIPAdapter` public + `_PinnedIPAdapter` alias + `build_pinned_session` factory | ✅ `ssrf_guard.py:208,264,272-299`; `safe_post`/`safe_get` refactored; webhook dispatcher kept inline to preserve `apps.webhooks.services.validate_external_url` patch target — fine call. |
| #2 — `delivery.response_status_code = None` valid | ✅ `apps/webhooks/models.py:149` field is `PositiveSmallIntegerField(null=True, blank=True)`. |
| #3 — Exception ladder gains explicit `RequestException` branch | ✅ `services.py:262-267`; bare `Exception` retains `logger.exception(...)` only for true programmer errors. |

## SSRF guarantee

Unchanged: `validate_external_url` → `_resolve_and_check` (private-IP reject) →
`PinnedIPAdapter` mount → `session.post(allow_redirects=False, verify=True)`. DNS
rebind and 3xx-pivot defences intact.

## One observation (non-blocking)

`_dispatch_webhook_post` could call `build_pinned_session(url)` to consolidate the
sequencing in one place, but that would move the test patch target and gain very
little. Leave it as-is until the patch target is touched for unrelated reasons.

## Full review

`_coordination/reviews/review-BE-SEC-WEBHOOK-SSRF-MINORS-CLOSEOUT-2026-04-30.md`

— lp-reviewer
