---
tags: [review, task/BE-SEC-WEBHOOK-SSRF-MINORS, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-30
---

# Review: BE-SEC-WEBHOOK-SSRF-MINORS-CLOSEOUT — Webhook SSRF minor notes closeout

## Verdict: APPROVE ✅

## Summary

All three minor notes from the prior `BE-SEC-WEBHOOK-DELIVERY-SSRF` approval verdict
are correctly addressed. SSRF guarantees (DNS rebind defence + redirect refusal +
private-IP rejection + TLS verification) are unchanged. No new attack surface, no
behaviour regressions, and the backwards-compat alias preserves existing tests.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

None blocking. One observation only:

- **(Obs)** `apps/webhooks/services.py::_dispatch_webhook_post` still inlines the
  `validate_external_url(url)` → `PinnedIPAdapter` mount sequence rather than calling
  the new `build_pinned_session(url)` factory. The PR author flagged this and chose
  to keep the inline form so `tests/webhooks/test_webhook_services.py::
  test_dispatch_helper_disables_redirects` (which patches
  `apps.webhooks.services.validate_external_url`) keeps working without churn. That
  trade is reasonable — the patch target is the smaller surface change and the
  factory still has a single canonical implementation in `ssrf_guard.py`. Worth a
  follow-up only if the patch target is ever updated for unrelated reasons.

## Verification performed

| Claim | Verified | How |
|-------|----------|-----|
| `PinnedIPAdapter` promoted to public class | ✅ | `ssrf_guard.py:208` — `class PinnedIPAdapter(HTTPAdapter)` |
| `_PinnedIPAdapter = PinnedIPAdapter` alias kept | ✅ | `ssrf_guard.py:264` — preserves `tests/test_safe_get_ssrf.py::PinnedIPAdapterTestCase` (4 references to `_PinnedIPAdapter` import) |
| `build_pinned_session(url) -> (Session, hostname, pinned_ip)` factory added | ✅ | `ssrf_guard.py:272-299` — composes `validate_external_url` + adapter mount in the same order as the prior inline blocks |
| `safe_post` / `safe_get` refactored to use the factory | ✅ | `ssrf_guard.py:330` and `ssrf_guard.py:433` both call `build_pinned_session(url)` |
| `apps/webhooks/services.py` imports public `PinnedIPAdapter` | ✅ | `services.py:23` — `from apps.integrations_chat.ssrf_guard import (PinnedIPAdapter, SSRFError, validate_external_url)` |
| Patch target `apps.webhooks.services.validate_external_url` preserved | ✅ | `services.py:73` retains the explicit `validate_external_url(url)` call site for the redirect-disabled test |
| `response_status_code = None` is a valid write | ✅ | `apps/webhooks/models.py:149` — `models.PositiveSmallIntegerField(null=True, blank=True)`; field is nullable end-to-end |
| Exception ladder gains explicit `RequestException` branch | ✅ | `services.py:262-267` — between `ConnectionError` and bare `Exception`; bare branch retains `logger.exception(...)` for true programmer errors |
| SSRF guarantee preserved | ✅ | `validate_external_url` → `_resolve_and_check` → `PinnedIPAdapter` mount → `session.post(allow_redirects=False, verify=True)` chain unchanged in both `safe_post` and the inlined webhook dispatcher |

## Positive Observations

- Backwards-compat strategy (public name + underscored alias) is the right call —
  zero churn for existing tests / type stubs / external consumers, while new
  callers get the clean public symbol.
- `build_pinned_session` returns the `(session, hostname, pinned_ip)` tuple, which
  preserves observability (callers can log or assert against the pinned IP). Better
  than a single `Session` return that hides the resolution result.
- The exception ladder change correctly preserves `logger.exception(...)` only on
  the bare `Exception` branch (genuine programmer errors), so labelled
  `RequestException` failures don't pollute logs with stack traces while still
  carrying the `str(e)[:200]` snippet on the delivery row.
- Author was disciplined about scope — declined to swap the webhook dispatcher
  over to `build_pinned_session(url)` because it would have moved a test patch
  target, and called that out explicitly in the PR. That's exactly the right level
  of discretion for a closeout PR.
- The `safe_post` docstring update ("Two-layer validation: chat-webhook allowlist
  first, then the generic scheme + private-IP rejection performed inside
  `build_pinned_session`") makes the layering explicit; a future reader doesn't
  have to chase the call chain to understand why both validators run.

## Test verification accepted

- `pytest tests/test_safe_get_ssrf.py tests/test_webhook_ssrf.py --reuse-db
  --no-migrations -q` → **58 passed** (per submission).
- Manual replay of `test_dispatch_helper_disables_redirects` confirmed the
  `allow_redirects=False, verify=True, timeout=30` invariants are still asserted
  by the inline form.
- Static import check (`apps.webhooks.services.PinnedIPAdapter` resolvable) is
  consistent with the source — confirmed by reading the module imports.
- Out-of-scope migration drift on the broader webhook-services suite is
  acknowledged and not blocking — the changed code path is exercised by the
  manual replay and the 58 SSRF-suite tests.

— lp-reviewer
