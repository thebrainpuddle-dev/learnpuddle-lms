---
tags: [review, task/BE-OBS4, task/SAML-SLO, verdict/request_changes, reviewer/lp-reviewer]
created: 2026-04-19
---

# Review: BE-OBS4 (Stripe Webhook Granularity) + SAML SLO

## Verdict: REQUEST_CHANGES

Overall both changes are well-structured. The Stripe webhook work is clean and can
land as-is (modulo tests). The SAML SLO implementation has **one real security
gap (unsigned LogoutRequest accepted) that must be fixed** before merge, plus two
minor XML-hygiene issues.

## Summary

- **OBS-4 Stripe webhook**: Clean split of `except Exception → 400` into three
  clauses with correct HTTP status semantics. No issues.
- **SAML SLO**: Implementation is thoughtful and audits every decision. But
  `parse_logout_request` treats IdP signatures as optional even when IdP certs
  are configured — this opens a CSRF-style forced-logout vector. Plus minor XML
  injection/malformation concerns in response building.

---

## Critical Issues

None (no data loss or tenant isolation bypass).

---

## Major Issues

### M1. Unsigned LogoutRequest accepted → CSRF-style forced logout

**File:** `backend/apps/users/saml_service.py:572-576`

```python
sig = root.find("ds:Signature", NS)
normalized_certs = [_ensure_pem(c) for c in idp_certs_pem if c]
if sig is not None and normalized_certs:
    _verify_xml_signature(root, normalized_certs)
```

The check is guarded by `sig is not None` — if a LogoutRequest arrives without a
`<ds:Signature>`, we skip verification entirely and still parse the NameID.
`saml_sls` is `@csrf_exempt` + `@require_POST`, so any third-party site can
cross-post a forged LogoutRequest with an arbitrary NameID (e.g. the victim's
email, which is often public) and force us to blacklist every one of that
user's refresh tokens — i.e., kick them out of active sessions.

The docstring at lines 528-540 rationalizes this as "many IdPs omit signatures
on SLO requests." That's a weak justification:
- SAML 2.0 core (§3.7.1) recommends signed LogoutRequests.
- Every real-world IdP we've cited as a tenant (Azure AD, Okta, Google) signs
  LogoutRequests by default.
- When `idp_x509_certs` is configured, the tenant has explicitly told us who
  is allowed to authenticate — extending that trust to SLO is the obvious
  consistent behavior.

**Required fix (choose one):**

Option A (preferred): **When IdP certs are configured, require a signed
LogoutRequest.** Unsigned → `SAMLValidationError("REJECT_SIGNATURE", ...)`.
The SLS view already audits-and-continues on `SAMLValidationError`, so the
IdP still gets a `Responder`-status LogoutResponse.

```python
if normalized_certs:
    if sig is None:
        raise SAMLValidationError(
            "REJECT_SIGNATURE",
            "LogoutRequest is unsigned but IdP certificates are configured",
        )
    _verify_xml_signature(root, normalized_certs)
```

Option B: Make signature enforcement configurable on `TenantSAMLConfig`
(`require_signed_logout_requests`, default True). Lets legacy IdPs opt out
explicitly rather than failing silently.

Either way, add a test that asserts an unsigned LogoutRequest does **not**
invalidate tokens when IdP certs exist.

### M2. Attacker-controlled value interpolated into response XML without escaping

**File:** `backend/apps/users/saml_service.py:611-630` (`build_logout_response`)

```python
f" InResponseTo=\"{in_response_to}\">"
```

`in_response_to` is `request_id` from the parsed LogoutRequest's `ID` attribute
(attacker-controlled in the forged-request case above, and still
un-sanitized even when signed — an IdP bug could leak malformed IDs).
A crafted ID like `id"><evil/><foo x="` produces malformed XML in the
LogoutResponse we send back.

Impact today is limited (worst case: the IdP's XML parser rejects our
response and the SLO loop dangles) — but it's poor hygiene and could turn
into an actual XML-injection vector if the SP-signing path (currently
unimplemented per the design note) is added later without revisiting.

**Fix:** XML-escape all interpolated values, or build the response with
`lxml.etree` / `xml.etree.ElementTree` element construction. `saml.utils`
already imports `html` for escaping elsewhere in the stack; `xml.sax.saxutils.quoteattr`
is the cleanest option for attributes, `escape` for element text.

The same issue exists in `saml_views.py:213-222` (`saml_login` AuthnRequest
construction) — `sp_entity` there comes from tenant config, so the risk is
"malicious tenant admin" rather than remote, but still worth escaping once
you touch this code.

---

## Minor Issues

### m1. `slo_outcome` uses the wrong audit code on successful SLO

**File:** `backend/apps/users/saml_views.py:482`

```python
slo_outcome = "ACCEPT" if logout_req else "REJECT_MALFORMED"
```

If `logout_req` parsed OK but the user didn't exist (we logged
`"NameID ... not found in tenant ..."`), we still write `ACCEPT` — which is
fine for the protocol but misleading in the audit log (the event's `user` FK
is null and there are no tokens to revoke, but the row reads as a successful
SSO-style ACCEPT).

Consider `ACCEPT_NO_USER` or `ACCEPT_SESSION_ENDED` for clarity. Not a
blocker.

### m2. Stripe webhook dispatcher still swallows handler errors to 200

**File:** `backend/apps/billing/webhook_views.py:78-83`

```python
try:
    handler(event)
except Exception:
    logger.exception("Error processing webhook event %s (type=%s)", event.id, event.type)
```

Intentional per the design note — prevents retry storms when the bug is in
*our* handler (Stripe retries up to 3 days). But this is invisible to Stripe's
delivery dashboard. Consider emitting a Sentry breadcrumb / `metrics.incr` so
we have observability into handler crashes.

Not a merge blocker — the exception is captured via `logger.exception`, which
Sentry picks up if `SENTRY_DSN` is set.

### m3. Dead `request_id` fallback in `saml_sls`

**File:** `backend/apps/users/saml_views.py:460`

```python
request_id = logout_req.request_id if logout_req else ""
...
response_xml = build_logout_response(
    in_response_to=request_id,
    ...
)
```

When `logout_req` is None we send `InResponseTo=""`. Per SAML 2.0 core §3.2.2,
`InResponseTo` is optional only if the response is *not* in reply to a
request. Since we always arrived here via an SLS POST, we should either
generate a placeholder or omit the attribute entirely when the source
request was unparseable. Most IdPs tolerate the empty string, so flag-only.

### m4. No tests in this changeset

The change requests tests from qa-tester via an inbox message, but the code
is up for review without them. I'm approving the Stripe work on code
inspection, but M1/M2 above can only be closed once tests exist that exercise
unsigned LogoutRequest rejection and malformed ID handling.

---

## Positive Observations

**OBS-4 Stripe webhook:**
- Three-clause split is exactly right: `ValueError → 400` (won't retry),
  `SignatureVerificationError → 401` (distinct in Stripe dashboard),
  generic `Exception → 500 + logger.exception` (triggers auto-retry).
- `import stripe` at module top is correct — the billing app already depends
  on the stripe SDK (`requirements.txt:86`), and local imports inside a
  frequently-hit webhook view were unnecessary overhead.
- Per-IP throttling (`StripeWebhookThrottle`) already present — nice layered
  defense against signature-spam attacks.

**SAML SLO:**
- Explicit `tenant=tenant` on the `User.objects.get(...)` call — defensive
  belt-and-braces even though the User manager is tenant-aware.
  Exactly the pattern we want given the historical `tenant_me` cross-tenant
  leak (BE-SEC-001).
- Token blacklist via `OutstandingToken` + `BlacklistedToken` is the right
  approach (`BLACKLIST_AFTER_ROTATION=True` makes this fully consistent with
  rotation).
- Blacklist failure is contained — SLO loop still completes, preventing the
  user's browser from being stranded on the IdP.
- Audit rows written for every branch (malformed, missing, success, not-found).
- `HTTP-Redirect` binding correctly implements raw-deflate (`[2:-4]` to strip
  zlib header/checksum) symmetric with the existing `saml_login` AuthnRequest
  path. Good reuse of an existing pattern.
- `email__iexact=name_id.lower()` handles case consistently even though
  `iexact` already ignores case — redundant but safe.
- Replay protection (`REPLAY_CACHE_SECONDS = 2h`) fail-closes if Redis is
  down. Correct.

---

## Action Items for backend-engineer

Before re-review:
1. **[M1]** Require a signed LogoutRequest when `idp_x509_certs` is configured.
2. **[M2]** XML-escape attacker-controlled values in `build_logout_response`
   (minimum: `in_response_to`). Same treatment for `saml_login`'s
   `AuthnRequest` while you're in there.
3. **[m4]** Coordinate with qa-tester on the test suite already requested —
   add at least one test for the M1 scenario.
4. Optional polish: m1, m2, m3 above.

OBS-4 Stripe webhook: **APPROVE** independent of SLO rework. Ship it as a
separate diff.
