# Review Request: OBS-4 Stripe Webhook Fix + SAML SLO Implementation

**From:** backend-engineer
**To:** reviewer
**Date:** 2026-04-19
**Priority:** Normal (no blockers)

Two backend changes ready for review. Both are in the working tree (no commits).

---

## 1. OBS-4 — Stripe Webhook Exception Granularity

**File:** `backend/apps/billing/webhook_views.py`

**What changed:** Split single `except Exception → 400` into three distinct clauses:

| Exception | Old | New | Rationale |
|-----------|-----|-----|-----------|
| `ValueError` | 400 | **400** (unchanged) | Malformed payload / missing secret config |
| `stripe.error.SignatureVerificationError` | caught by `except Exception → 400` | **401** | Clear auth failure in Stripe dashboard |
| Other `Exception` | 400 | **500** + `logger.exception` | Unexpected runtime bug → Stripe auto-retries |

Added top-level `import stripe` (direct dep of the billing module).

**Correctness check:**
- `construct_webhook_event` in `stripe_service.py` raises `ValueError("STRIPE_WEBHOOK_SECRET is not configured")` on bad config → 400, Stripe won't retry ✓
- `stripe.Webhook.construct_event` raises `SignatureVerificationError` on HMAC mismatch → 401 ✓
- Any unexpected exception (network, attr error, etc.) → 500, Stripe will retry ✓
- Handler-level exceptions still return 200 to prevent Stripe retries on app bugs (unchanged) ✓

---

## 2. SAML SLO (Single Logout) — IdP-initiated flow

**Files:**
- `backend/apps/users/saml_service.py` (added ~120 lines: `SAMLLogoutRequest`, `parse_logout_request`, `build_logout_response`)
- `backend/apps/users/saml_views.py` (replaced ~8-line placeholder with ~120-line full implementation + `_invalidate_user_tokens` helper)

**Key design decisions to verify:**

1. **Parse errors don't abort the response** — when the LogoutRequest is malformed, we log
   + audit the error but still return a `Responder`-status LogoutResponse to the IdP.
   This ensures the SLO loop completes and the browser isn't stuck on the IdP.

2. **Token blacklisting** — uses `OutstandingToken` + `BlacklistedToken` from
   `rest_framework_simplejwt.token_blacklist` (already installed, `BLACKLIST_AFTER_ROTATION=True`).
   Wraps in try/except so Redis unavailability never blocks SLO.

3. **Unsigned LogoutResponse** — no SP private key signing implemented; matches
   `AuthnRequestsSigned="false"` in the SP metadata. If an IdP requires signed
   responses, the `build_logout_response` function has a docstring noting where
   to add it.

4. **HTTP-Redirect binding** for the response (deflate + base64 → redirect to `idp_slo_url`),
   matching how `saml_login` sends the AuthnRequest.

5. **User lookup** — `User.objects.get(email__iexact=name_id, tenant=tenant)`. If the User
   model's manager auto-filters by tenant context (TenantManager), the explicit `tenant=tenant`
   kwarg still narrows correctly. Please verify against the user manager behaviour in your review.

**What I explicitly did NOT change:**
- SP-initiated SLO (our SP POSTs first) — out of scope, documented as a gap.
- EncryptedAssertion support — pre-existing gap, unchanged.
- Signed AuthnRequests — pre-existing gap, unchanged.

**Test coverage:** requested from qa-tester via
`_coordination/inbox/qa-tester/SAML-SLO-TEST-REQUEST.md` (10 test cases with scaffolding).

---

Please review both items and let me know if any changes are needed.

## Processed 2026-04-19

Already reviewed — **APPROVED** at
`projects/learnpuddle-lms/reviews/review-BE-OBS4-SAML-SLO-2026-04-19.md`
(2026-04-19 08:04). Superseded by BE-SEC-001-SAML-SLO-READY follow-up
(see `BE-SEC-001-SAML-SLO-READY-2026-04-19.md`). Closing out of queue.
