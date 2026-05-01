# apps/users/saml_views.py
"""
SAML 2.0 SSO endpoints.

All endpoints are tenant-scoped via the ``tenant_subdomain`` path
parameter — we do *not* trust ``request.tenant`` for ACS because SAML
flows commonly come through the root platform domain and the tenant is
determined by where the IdP was told to POST.

The ACS endpoint is CSRF-exempt (IdP POSTs a browser form back) but:
  * it rate-limits per IP (`SAMLAcsThrottle`),
  * it cryptographically verifies the assertion signature, and
  * every decision — accept or reject — is written as a
    :class:`SAMLAuthEvent` audit row.
"""

from __future__ import annotations

import base64
import logging
import secrets
import urllib.parse
import uuid
from typing import Optional
from xml.sax.saxutils import escape as _xml_escape, quoteattr as _xml_quoteattr

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from rest_framework.throttling import SimpleRateThrottle

from apps.tenants.models import Tenant
from apps.tenants.saml_models import TenantSAMLConfig
from apps.users.models import SAMLAuthEvent, User  # noqa: F401 — User needed for type hint below
from apps.users.saml_service import (
    SAMLValidationError,
    build_logout_response,
    generate_sp_metadata,
    parse_logout_request,
    verify_and_parse_response,
)
from apps.users.sso_pipeline import provision_saml_user
from apps.users.tokens import get_tokens_for_user
from utils.audit import log_audit

logger = logging.getLogger(__name__)

# Replay-protection window.  Assertion IDs we've already accepted are
# cached for at least the typical NotOnOrAfter span (~1h).  If an IdP
# uses longer lifetimes, bump this via env.
REPLAY_CACHE_SECONDS = 2 * 60 * 60


class SAMLAcsThrottle(SimpleRateThrottle):
    """Per-IP rate limit for the ACS endpoint — deters signature spam.

    Reads its rate from ``REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['saml_acs']``
    (see settings.py), defaulting to 30/minute.
    """

    scope = "saml_acs"

    def get_cache_key(self, request, view):
        return f"throttle_saml_acs:{self.get_ident(request)}"

    def get_rate(self):
        rates = (
            getattr(settings, "REST_FRAMEWORK", {})
            .get("DEFAULT_THROTTLE_RATES", {})
        )
        return rates.get(self.scope, "30/minute")


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _load_tenant_saml(tenant_subdomain: str):
    """Resolve tenant + SAML config, or return (None, HttpResponse error)."""
    try:
        tenant = Tenant.objects.get(subdomain=tenant_subdomain, is_active=True)
    except Tenant.DoesNotExist:
        return None, None, JsonResponse({"error": "Unknown tenant"}, status=404)

    # Task spec mandates `tenant.features['saml']` as the feature flag.
    # We consult the `features` dict (backed by the `feature_saml` BooleanField)
    # so SAML can be enabled/disabled independently of OAuth-style SSO.
    features = getattr(tenant, "features", {}) or {}
    if not features.get("saml", False):
        return tenant, None, JsonResponse(
            {"error": "SAML SSO is not enabled for this tenant"}, status=403
        )

    try:
        config = TenantSAMLConfig.objects.get(tenant=tenant)
    except TenantSAMLConfig.DoesNotExist:
        return tenant, None, JsonResponse(
            {"error": "SAML not configured for this tenant"}, status=404
        )

    if not config.enabled:
        return tenant, config, JsonResponse(
            {"error": "SAML disabled for this tenant"}, status=403
        )

    return tenant, config, None


def _acs_url(request, tenant_subdomain: str) -> str:
    scheme = "https" if request.is_secure() else "http"
    host = request.get_host()
    return f"{scheme}://{host}/api/v1/auth/saml/{tenant_subdomain}/acs/"


def _invalidate_user_tokens(user: "User") -> None:
    """Blacklist all non-expired SimpleJWT refresh tokens for ``user``.

    Called by the SLS handler so that a SAML Single Logout immediately
    invalidates the user's active sessions.  Failures are logged but do
    not abort the SLO flow — the IdP must still receive its LogoutResponse.
    """
    try:
        from rest_framework_simplejwt.token_blacklist.models import (  # type: ignore
            BlacklistedToken,
            OutstandingToken,
        )
        outstanding = list(
            OutstandingToken.objects.filter(user=user, expires_at__gt=timezone.now())
        )
        blacklisted = 0
        for token in outstanding:
            _, created = BlacklistedToken.objects.get_or_create(token=token)
            if created:
                blacklisted += 1
        logger.info(
            "SAML SLO: blacklisted %d/%d refresh token(s) for user %s",
            blacklisted,
            len(outstanding),
            user.id,
        )
    except Exception as exc:
        logger.warning(
            "SAML SLO: failed to blacklist tokens for user %s: %s", user.id, exc
        )


def _audit_event(
    *,
    tenant,
    decision: str,
    detail: str = "",
    user: Optional[User] = None,
    email: str = "",
    assertion_id: str = "",
    request=None,
) -> None:
    ip = None
    if request is not None:
        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = (xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR")) or None
    try:
        SAMLAuthEvent.objects.create(
            tenant=tenant,
            user=user,
            email=(email or "")[:254],
            decision=decision,
            detail=(detail or "")[:500],
            ip_address=ip,
            assertion_id=(assertion_id or "")[:255],
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to persist SAMLAuthEvent: %s", exc)


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------

@require_GET
def saml_metadata(request, tenant_subdomain: str):
    """SP metadata XML — unauthenticated but only exposes public info."""
    tenant, config, err = _load_tenant_saml(tenant_subdomain)
    if err is not None:
        return err

    metadata = generate_sp_metadata(
        entity_id=config.sp_entity_id or _acs_url(request, tenant_subdomain),
        acs_url=_acs_url(request, tenant_subdomain),
        slo_url=f"{request.scheme}://{request.get_host()}/api/v1/auth/saml/{tenant_subdomain}/sls/",
        sp_cert=config.sp_x509_cert,
    )
    return HttpResponse(metadata, content_type="application/samlmetadata+xml")


@require_GET
def saml_login(request, tenant_subdomain: str):
    """Initiate SSO by sending the browser to the IdP SSO URL.

    Two binding modes:

    * **No SP private key configured** (default): emit an unsigned
      AuthnRequest via the HTTP-Redirect binding (deflate-encoded query
      param).  Many IdPs accept unsigned requests; this preserves existing
      behaviour.
    * **SP private key configured** (``sp_private_key_encrypted`` set
      and ``sp_x509_cert`` populated): emit an enveloped-XMLDSig-signed
      AuthnRequest via the HTTP-POST binding (auto-submitting form).
      Strict-mode IdPs — Microsoft Entra/AzureAD strict, ADFS — require
      this.
    """
    tenant, config, err = _load_tenant_saml(tenant_subdomain)
    if err is not None:
        return err

    request_id = f"id-{uuid.uuid4().hex}"
    issue_instant = timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    acs_url = _acs_url(request, tenant_subdomain)
    sp_entity = config.sp_entity_id or acs_url

    # Use quoteattr() for attributes and escape() for element text.
    # Values here are server-controlled (UUID, timestamp, config URLs) but
    # we escape for defence-in-depth: a misconfigured idp_sso_url or
    # sp_entity_id containing XML special characters would otherwise
    # silently produce a malformed AuthnRequest.
    authn_request = (
        "<samlp:AuthnRequest xmlns:samlp=\"urn:oasis:names:tc:SAML:2.0:protocol\" "
        "xmlns:saml=\"urn:oasis:names:tc:SAML:2.0:assertion\" "
        f"ID={_xml_quoteattr(request_id)} Version=\"2.0\" IssueInstant={_xml_quoteattr(issue_instant)} "
        f"Destination={_xml_quoteattr(config.idp_sso_url)} "
        f"AssertionConsumerServiceURL={_xml_quoteattr(acs_url)} "
        "ProtocolBinding=\"urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST\">"
        f"<saml:Issuer>{_xml_escape(sp_entity)}</saml:Issuer>"
        "</samlp:AuthnRequest>"
    )

    relay_state = request.GET.get("next", "/")

    sp_key_pem = config.sp_private_key_pem
    sp_cert_pem = config.sp_x509_cert if sp_key_pem else ""
    if sp_key_pem and sp_cert_pem:
        # Sign + emit via HTTP-POST binding.  An enveloped XMLDSig is not
        # compatible with HTTP-Redirect (which uses an external SigAlg /
        # Signature query string instead).
        from apps.users.saml_service import sign_saml_xml

        signed_xml = sign_saml_xml(
            authn_request,
            sp_private_key_pem=sp_key_pem,
            sp_x509_cert_pem=sp_cert_pem,
        )
        encoded = base64.b64encode(signed_xml.encode("utf-8")).decode("ascii")
        # Auto-posting HTML form per SAML §3.5.4 (HTTP POST binding).
        # The values placed into ``value="…"`` attributes are HTML-escaped
        # so a hostile RelayState (URL-controlled) can't break out of the
        # attribute.  ``encoded`` is base64 (a-zA-Z0-9+/=) so it's already
        # HTML-safe.
        from django.utils.html import escape as _html_escape

        form_html = (
            "<!DOCTYPE html><html><head>"
            "<meta charset=\"utf-8\">"
            "<title>Redirecting…</title></head>"
            "<body onload=\"document.forms[0].submit()\">"
            "<noscript><p>JavaScript is disabled. Click the button to continue.</p></noscript>"
            f"<form method=\"post\" action=\"{_html_escape(config.idp_sso_url)}\">"
            f"<input type=\"hidden\" name=\"SAMLRequest\" value=\"{encoded}\">"
            f"<input type=\"hidden\" name=\"RelayState\" value=\"{_html_escape(relay_state)}\">"
            "<noscript><button type=\"submit\">Continue</button></noscript>"
            "</form></body></html>"
        )
        return HttpResponse(form_html, content_type="text/html; charset=utf-8")

    # Unsigned fallback — HTTP-Redirect binding (deflate + base64).
    import zlib

    deflated = zlib.compress(authn_request.encode("utf-8"))[2:-4]
    encoded = base64.b64encode(deflated).decode("ascii")

    query = urllib.parse.urlencode(
        {"SAMLRequest": encoded, "RelayState": relay_state}
    )
    separator = "&" if "?" in config.idp_sso_url else "?"
    return HttpResponseRedirect(f"{config.idp_sso_url}{separator}{query}")


@csrf_exempt
@require_POST
def saml_acs(request, tenant_subdomain: str):
    """Assertion Consumer Service — accepts the IdP's SAML Response.

    CSRF-exempt because the IdP is the form submitter; signature
    verification substitutes for CSRF protection.
    """
    # Rate-limit by IP before doing any XML parsing.
    throttle = SAMLAcsThrottle()
    if not throttle.allow_request(request, None):
        return JsonResponse({"error": "Rate limit exceeded"}, status=429)

    tenant, config, err = _load_tenant_saml(tenant_subdomain)
    if err is not None:
        if tenant is not None:
            _audit_event(
                tenant=tenant,
                decision="REJECT_DISABLED",
                detail="SAML disabled or not configured",
                request=request,
            )
        return err

    saml_response = request.POST.get("SAMLResponse")
    if not saml_response:
        _audit_event(
            tenant=tenant,
            decision="REJECT_MALFORMED",
            detail="Missing SAMLResponse",
            request=request,
        )
        return HttpResponseBadRequest("Missing SAMLResponse")

    acs_url = _acs_url(request, tenant_subdomain)
    audience = config.sp_entity_id or acs_url

    try:
        parsed = verify_and_parse_response(
            raw_response_b64=saml_response,
            idp_certs_pem=config.idp_x509_certs or [],
            expected_audience=audience,
            attribute_mapping=config.attribute_mapping or {},
            expected_destination=acs_url,
        )
    except SAMLValidationError as exc:
        _audit_event(
            tenant=tenant,
            decision=exc.code,
            detail=exc.message,
            request=request,
        )
        return JsonResponse({"error": "SAML assertion rejected", "detail": exc.message}, status=403)

    # Replay protection: reject if we've seen this assertion ID already.
    # Note: REPLAY_CACHE_SECONDS (2 h) must be ≥ any IdP NotOnOrAfter window
    # or a replay could sneak past after the cache entry expires but before
    # the assertion itself does.
    replay_key = f"saml_replay:{tenant.id}:{parsed.assertion_id}"
    try:
        seen = cache.get(replay_key)
    except Exception as exc:  # Redis unavailable / mis-configured
        # FAIL CLOSED: if we can't consult replay cache we cannot honor
        # the replay guarantee, so we reject rather than silently accept.
        logger.error("SAML replay cache unavailable: %s", exc)
        _audit_event(
            tenant=tenant,
            decision="REJECT_REPLAY",
            detail=f"Replay cache unavailable: {exc}",
            email=parsed.email,
            assertion_id=parsed.assertion_id,
            request=request,
        )
        return JsonResponse({"error": "SAML replay cache unavailable"}, status=503)

    if seen:
        _audit_event(
            tenant=tenant,
            decision="REJECT_REPLAY",
            detail="Duplicate assertion ID",
            email=parsed.email,
            assertion_id=parsed.assertion_id,
            request=request,
        )
        return JsonResponse({"error": "SAML replay detected"}, status=403)
    try:
        cache.set(replay_key, True, REPLAY_CACHE_SECONDS)
    except Exception as exc:  # pragma: no cover — same fail-closed path
        logger.error("SAML replay cache write failed: %s", exc)
        _audit_event(
            tenant=tenant,
            decision="REJECT_REPLAY",
            detail=f"Replay cache write failed: {exc}",
            email=parsed.email,
            assertion_id=parsed.assertion_id,
            request=request,
        )
        return JsonResponse({"error": "SAML replay cache unavailable"}, status=503)

    if not parsed.email:
        _audit_event(
            tenant=tenant,
            decision="REJECT_NO_EMAIL",
            detail="Assertion contained no email attribute",
            assertion_id=parsed.assertion_id,
            request=request,
        )
        return JsonResponse({"error": "Assertion contained no email"}, status=400)

    if not config.domain_allowed(parsed.email):
        _audit_event(
            tenant=tenant,
            decision="REJECT_DOMAIN_NOT_ALLOWED",
            detail=f"domain for {parsed.email} not in allowed list",
            email=parsed.email,
            assertion_id=parsed.assertion_id,
            request=request,
        )
        return JsonResponse({"error": "Email domain not allowed"}, status=403)

    try:
        user = provision_saml_user(tenant=tenant, config=config, assertion=parsed)
    except PermissionError as exc:
        _audit_event(
            tenant=tenant,
            decision="REJECT_PROVISION_DISABLED",
            detail=str(exc),
            email=parsed.email,
            assertion_id=parsed.assertion_id,
            request=request,
        )
        return JsonResponse({"error": str(exc)}, status=403)

    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])

    tokens = get_tokens_for_user(user)
    _audit_event(
        tenant=tenant,
        decision="ACCEPT",
        user=user,
        email=parsed.email,
        assertion_id=parsed.assertion_id,
        request=request,
    )
    try:
        log_audit(
            "LOGIN",
            "User",
            target_id=str(user.id),
            target_repr=str(user),
            request=request,
            actor=user,
        )
    except Exception:  # pragma: no cover
        pass

    relay_state = request.POST.get("RelayState", "/")
    # AUDIT-2026-04-26-PHASE3-10: do NOT embed JWTs in a URL fragment.
    # Browser history, JS-based error trackers (Sentry, Datadog RUM), and
    # the address bar all capture fragments — fragments only avoid being
    # transmitted in HTTP request bodies, which is a much weaker guarantee
    # than people assume.  Mirror the OAuth callback's pattern instead:
    # cache the token pair under a short-lived, single-use, opaque code
    # and redirect with ``?code=<code>``.  The frontend then POSTs the
    # code to ``/users/auth/sso/token-exchange/`` (sso_views.sso_token_exchange)
    # which pops the cache key and returns the JWT pair.
    if relay_state and relay_state.startswith("/"):
        sso_code = secrets.token_urlsafe(48)
        # 120 s TTL: long enough for a slow frontend bootstrap, short
        # enough that a leaked code is rapidly useless.  Same key
        # namespace as the OAuth callback (``sso_code:<code>``) so a
        # single exchange endpoint serves both flows.
        try:
            cache.set(
                f"sso_code:{sso_code}",
                {
                    "access_token": tokens["access"],
                    "refresh_token": tokens["refresh"],
                    "user_id": str(user.id),
                },
                timeout=120,
            )
        except Exception as exc:  # pragma: no cover — Redis unavailable
            logger.error("SAML ACS: cache write failed for sso_code: %s", exc)
            # Fail closed: without the cache we can't exchange the code,
            # so don't pretend the redirect worked.  Return JSON so the
            # frontend can surface a sensible error.
            return JsonResponse(
                {"error": "Login succeeded but token exchange is unavailable"},
                status=503,
            )

        scheme = "https" if request.is_secure() else "http"
        host = request.get_host()
        # Preserve any existing query string on the relay path (rare, but
        # the frontend may include ``?next=...``).  The ``code`` is
        # appended with the right separator either way.
        separator = "&" if "?" in relay_state else "?"
        return HttpResponseRedirect(
            f"{scheme}://{host}{relay_state}{separator}code={sso_code}"
        )
    return JsonResponse(
        {"tokens": tokens, "user": {"id": str(user.id), "email": user.email}},
        status=200,
    )


@csrf_exempt
@require_POST
def saml_sls(request, tenant_subdomain: str):
    """Single Logout Service — IdP-initiated SLO endpoint.

    Flow:
      1. Parse the base64-encoded SAMLRequest (LogoutRequest) from the POST body.
      2. Verify the XMLDSig signature when present (using the configured IdP
         certificate(s)).
      3. Locate the user by NameID and blacklist all their outstanding
         SimpleJWT refresh tokens so active browser sessions are invalidated.
      4. Build an unsigned LogoutResponse and redirect the browser to the
         IdP's SLO URL via HTTP-Redirect binding.

    Errors during parsing or user lookup are logged and audited but do
    **not** prevent the LogoutResponse from being sent — the IdP must
    receive a response to complete the SLO handshake regardless.
    """
    tenant, config, err = _load_tenant_saml(tenant_subdomain)
    if err is not None:
        return err

    saml_request_b64 = request.POST.get("SAMLRequest", "")
    if not saml_request_b64:
        _audit_event(
            tenant=tenant,
            decision="REJECT_MALFORMED",
            detail="SLS: Missing SAMLRequest field",
            request=request,
        )
        return HttpResponseBadRequest("Missing SAMLRequest")

    # --- Step 1 & 2: Parse and optionally verify the LogoutRequest ----------
    logout_req = None
    try:
        logout_req = parse_logout_request(
            raw_request_b64=saml_request_b64,
            idp_certs_pem=config.idp_x509_certs or [],
        )
    except SAMLValidationError as exc:
        logger.warning("SAML SLO parse error for tenant %s: %s", tenant.subdomain, exc.message)
        _audit_event(
            tenant=tenant,
            decision=exc.code,
            detail=f"SLS parse error: {exc.message}",
            request=request,
        )
        # Continue — we still need to emit a LogoutResponse (with Responder
        # status) so the IdP's SLO loop can complete.

    # --- Step 3: Find user and blacklist their tokens -----------------------
    name_id = logout_req.name_id if logout_req else ""
    request_id = logout_req.request_id if logout_req else ""

    user = None
    if name_id:
        try:
            user = User.objects.get(email__iexact=name_id.lower(), tenant=tenant)
        except User.DoesNotExist:
            logger.info(
                "SAML SLO: NameID %r not found in tenant %s — no tokens to revoke",
                name_id,
                tenant.subdomain,
            )
        except User.MultipleObjectsReturned:  # pragma: no cover
            logger.warning(
                "SAML SLO: multiple users for NameID %r in tenant %s — skipping revocation",
                name_id,
                tenant.subdomain,
            )

    if user is not None:
        _invalidate_user_tokens(user)

    slo_outcome = "ACCEPT" if logout_req else "REJECT_MALFORMED"
    _audit_event(
        tenant=tenant,
        decision=slo_outcome,
        detail=f"SLO completed for NameID={name_id}",
        user=user,
        request=request,
    )

    # --- Step 4: Return LogoutResponse to IdP via HTTP-Redirect binding -----
    sp_entity = config.sp_entity_id or _acs_url(request, tenant_subdomain)

    if config.idp_slo_url:
        status_code = (
            "urn:oasis:names:tc:SAML:2.0:status:Success"
            if logout_req
            else "urn:oasis:names:tc:SAML:2.0:status:Responder"
        )
        # When the SP private key is configured, sign the LogoutResponse so
        # strict-mode IdPs (Microsoft Entra/AzureAD strict, ADFS) accept it.
        # Backwards compatible: if no key is set, emit unsigned.
        sp_key_pem = config.sp_private_key_pem
        sp_cert_pem = config.sp_x509_cert if sp_key_pem else ""
        response_xml = build_logout_response(
            in_response_to=request_id,
            issuer=sp_entity,
            destination=config.idp_slo_url,
            status_code=status_code,
            sp_private_key_pem=sp_key_pem,
            sp_x509_cert_pem=sp_cert_pem,
        )

        import zlib
        deflated = zlib.compress(response_xml.encode("utf-8"))[2:-4]  # strip zlib header/crc
        encoded = base64.b64encode(deflated).decode("ascii")

        params: dict = {"SAMLResponse": encoded}
        relay_state = request.POST.get("RelayState", "")
        if relay_state:
            params["RelayState"] = relay_state

        query = urllib.parse.urlencode(params)
        separator = "&" if "?" in config.idp_slo_url else "?"
        return HttpResponseRedirect(f"{config.idp_slo_url}{separator}{query}")

    # IdP SLO URL not configured — return a simple 200 so the browser isn't
    # left on an error page.  This shouldn't happen in production because
    # SAML metadata exchange ensures the SLO URL is present.
    return JsonResponse({"message": "Logout processed"}, status=200)
