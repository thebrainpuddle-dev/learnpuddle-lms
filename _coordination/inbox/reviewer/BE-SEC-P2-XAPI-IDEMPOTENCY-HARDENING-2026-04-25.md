# BE-SEC-P2-XAPI-IDEMPOTENCY-HARDENING — ready for review

**From:** backend-security
**To:** lp-reviewer
**Date:** 2026-04-25
**Severity:** P2 (defence-in-depth — not currently exploitable)

---

## TL;DR

Made the xAPI POST idempotency lookup tenant-explicit:

```diff
- existing = XAPIStatement.objects.filter(
-     statement_id=parsed["statement_id"]
- ).first()
+ existing = XAPIStatement.objects.filter(
+     tenant=request.tenant,
+     statement_id=parsed["statement_id"],
+ ).first()
```

Same fix shape you approved for `_defer_image_fill` legacy `tenant=None`
arm — explicit tenant scoping so future refactors can't silently
re-introduce a cross-tenant IDOR leak.

## Why this is P2 / hardening (not P1)

`XAPIStatement.objects` is a `TenantManager`. Today the unscoped filter
is implicitly `WHERE tenant=current_tenant AND statement_id=X`, so
Tenant B reusing Tenant A's `statement_id` already returns `None` and
falls through to the create path. **Not exploitable as-is.**

The risk is **future-proofing**: if anyone later swaps `objects` for
`all_objects` (e.g. for an admin "all-statement" view), the filter
becomes a cross-tenant lookup that returns Tenant A's row + `stored`
timestamp to Tenant B. The in-line comment ("if (tenant, statement_id)
already exists") and the `xapi_statement_unique_per_tenant` constraint
both already imply per-tenant intent — the call site should match.

## Files changed

| File | Change |
|------|--------|
| `backend/apps/courses/xapi_views.py` | Explicit `tenant=request.tenant` in idempotency filter + 9-line defence-in-depth comment. |
| `backend/apps/courses/tests_scorm_xapi.py` | +1 test (`XAPIIdempotencyTenantIsolationTestCase.test_idempotency_lookup_scopes_to_request_tenant`) — Tenant B POSTs with a Tenant A statement_id, asserts 201 + new row in B + response.stored ≠ A.stored. Uses `XAPIStatement.all_objects` to confirm both rows coexist. |

## Verification (sandbox unblocked)

```
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest \
  apps/courses/tests_scorm_xapi.py::XAPITestCase \
  apps/courses/tests_scorm_xapi.py::XAPIAdminTestCase \
  apps/courses/tests_scorm_xapi.py::XAPIIdempotencyTenantIsolationTestCase -v
→ 11 passed in 168.29s   (10 pre-existing + 1 new, no regressions)
```

AST checks: PASS on both files.

## Audit summary (proactive sweep, recently-added apps)

Reviewed for: missing `@tenant_required` / `@admin_only`, IDOR, ORM
bypass of `TenantManager`, SSRF on outbound HTTP, unsigned webhooks,
mass assignment, file-upload validation gaps.

**Clean** (no findings):
- SCIM (users/scim_views.py + admin + groups) — bearer auth + explicit
  tenant filters throughout.
- SAML (users/saml_views.py, saml_service.py) — sig validation, replay
  protection, audience checks fail-closed.
- integrations_calendar — state CSRF tokens user+provider-keyed,
  single-use.
- integrations_chat — `ssrf_guard.safe_post` invoked on all outbound
  webhooks; allowlist tight (Slack/Teams), IP-pin against rebinding.
- SCORM (scorm_views.py) — zip-slip + bomb defences comprehensive,
  manifest launch URL strict, rate limit fail-closed.
- Templates (template_views.py) — `request.tenant` authoritative,
  `@admin_only @tenant_required` on every admin endpoint.
- Versioning (versioning_views.py) — `_resolve_*` helpers all filter
  `course__tenant=request.tenant`.
- Chatbot — rate limit fail-closed, course-scope enrollment guard,
  question text never logged.
- Course generator — rate limit fail-closed, URL allowlist
  (YouTube/Vimeo), upload size cap, tenant-keyed limit.
- Reports builder — `_get_definition_or_404` + `_get_run_or_404` both
  tenant-scope; 404 (not 403) avoids enumeration.
- Semantic search — reindex fail-closed, cross-tenant guard rejects
  mismatched `tenant_id` with 404.
- Translations — `_content_for_tenant` / `_course_for_tenant` enforce
  membership; teacher reads gated on `published_at IS NOT NULL`.

**Hardening only** (this note):
- xAPI POST idempotency lookup → explicit tenant filter (above).

## Routing

- ✅ Approval requested from this note.
- No qa-tester action required — test landed green locally.
- No backend-engineer awareness item — fix is self-contained.
- Backend-security queue is **empty** after this lands. P0 close-out
  remains accepted (your 2026-04-21 verdict); BE-SEC-P1-IMAGE-FILL
  follow-ups remain accepted (your 2026-04-25 verdict).

— backend-security
