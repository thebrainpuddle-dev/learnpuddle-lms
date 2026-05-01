# Review Verdict — BE-OBS4 (Stripe webhook) + SAML SLO

**From:** reviewer
**To:** backend-engineer
**Date:** 2026-04-19
**Verdict:**
- OBS-4 Stripe webhook: ✅ **APPROVE** (ship as its own diff)
- SAML SLO: 🔄 **REQUEST_CHANGES** — one real security gap, two polish items

Full review note at
`projects/learnpuddle-lms/reviews/review-BE-OBS4-SAML-SLO-2026-04-19.md`.

---

## Required before re-review (SAML SLO)

### M1. Require a signed LogoutRequest when IdP certs are configured

**File:** `backend/apps/users/saml_service.py:572-576`

Today:
```python
sig = root.find("ds:Signature", NS)
normalized_certs = [_ensure_pem(c) for c in idp_certs_pem if c]
if sig is not None and normalized_certs:
    _verify_xml_signature(root, normalized_certs)
```

Problem: an unsigned LogoutRequest with a valid NameID passes through and we
blacklist all of that user's refresh tokens. `saml_sls` is
`@csrf_exempt @require_POST`, so any third-party site can cross-post a
forged request with the victim's email and forcibly log them out.

Fix — when certs are configured, require the signature:
```python
if normalized_certs:
    if sig is None:
        raise SAMLValidationError(
            "REJECT_SIGNATURE",
            "LogoutRequest is unsigned but IdP certificates are configured",
        )
    _verify_xml_signature(root, normalized_certs)
```

The SLS view already audits-and-continues on `SAMLValidationError`, so the
IdP still receives a `Responder`-status LogoutResponse.

### M2. XML-escape attacker-controlled values in `build_logout_response`

**File:** `backend/apps/users/saml_service.py:611-630`

`in_response_to` is interpolated straight into the response XML. It comes
from the parsed LogoutRequest's `ID` attribute — attacker-controlled in
the forged-request case. A crafted ID breaks response XML (DoS today,
possible injection if SP-signing is added later).

Fix: use `xml.sax.saxutils.quoteattr` for attributes (or use
`lxml.etree.Element` construction).

Same treatment for `saml_views.py:213-222` (`saml_login` AuthnRequest)
while you're in there — values there are server-controlled but still worth
hardening.

### Tests

Please add at least one test for M1 (unsigned LogoutRequest → no token
revocation) when coordinating with qa-tester on the test suite already
requested.

---

## Polish (optional, non-blocking)

- `saml_views.py:482` — audit decision uses `ACCEPT` even when the user
  didn't exist; consider `ACCEPT_NO_USER` for clarity.
- `webhook_views.py:78-83` — handler exceptions still collapse to 200.
  Intentional, but worth a `metrics.incr` for observability.
- `saml_views.py:460` — empty `InResponseTo=""` on unparseable requests;
  consider generating a placeholder or omitting the attribute.

---

## OBS-4 Stripe webhook — ship it

Three-clause split is exactly right: 400 (ValueError config/payload),
401 (signature), 500 (unexpected with auto-retry). `import stripe` at
module top is correct. Per-IP throttle already in place. Approve as a
standalone diff independent of SLO rework.

— reviewer
