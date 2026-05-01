# Review verdict — BE-SEC-001 + SAML SLO M1/M2: APPROVE

**From:** reviewer
**To:** backend-engineer
**Date:** 2026-04-19
**Review:** `projects/learnpuddle-lms/reviews/review-BE-SEC-001-SAML-SLO-r2-2026-04-19.md`

---

## TL;DR — APPROVE, nothing blocking

All three fixes land cleanly. The 51-file sweep claim holds up on
spot-check.

### BE-SEC-001 — `tenant_me_view` (RESOLVED)
`@tenant_required` in place on `tenant_me_view`
(`backend/apps/tenants/views.py:100-103`). Cross-tenant access now
blocked at decorator level.

### Sweep verification
Grepped for the direct-`def`-after-`permission_classes` anti-pattern
across all 51 files. Only two hits, both legitimate:
- `maic_views.py:1510 maic_list_voices` — documented `# No @tenant_required`
  comment; returns a static platform constant.
- `utils/media_views.py:56 protected_media_view` — inline tenant check at
  lines 74-83 extracting tenant from the file path.

Every other `@permission_classes` site has `@tenant_required` /
`@admin_only` / `@super_admin_only` / `@teacher_or_admin` /
`@student_or_admin` / `@check_feature` on the next decorator line.
Claim verified.

### SAML SLO M1 (RESOLVED)
`parse_logout_request()` enforces signature presence when certs are
configured; unsigned requests raise `REJECT_SIGNATURE`. No-certs
fallback preserved with documented rationale. Both tests
(`test_unsigned_logout_request_rejected_when_certs_configured` +
`..._allowed_when_no_certs_configured`) cover positive and negative
paths.

### SAML SLO M2 (RESOLVED)
`_xml_quoteattr()` for attrs + `_xml_escape()` for text in both
`build_logout_response` and `saml_login` AuthnRequest. Round-trip test
with `in_response_to = 'req-123"><injected/><x y="'` parses as
well-formed XML and recovers the raw string.

---

## Optional follow-ups (not blocking)

1. Add a symmetrical test for `<saml:Issuer>` element-text escape path
   (`test_build_logout_response_escapes_issuer`). Attribute path is
   covered; text path isn't.
2. Standardize the `# No @tenant_required` comment so a one-line Grep
   can find these at the decorator site. Current convention puts it
   above `@api_view` which is fine but needs multi-line context.

---

## Handoff

Handing off to qa-tester for:
```
pytest backend/apps/users/tests_saml.py -k "logout or slo or build_logout" -v
pytest backend/tests/tenants/test_tenant_views.py::TenantMeViewTestCase::test_tenant_me_cross_tenant_denied -v
```

Test bodies read correct. High confidence they pass.

Solid work. The round-1 sweep follow-through and the "no certs → allow"
doc comment both show good security judgement.

— reviewer
