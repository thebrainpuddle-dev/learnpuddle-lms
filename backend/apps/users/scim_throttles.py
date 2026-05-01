"""
Throttle classes for the SCIM 2.0 endpoints (AUDIT-2026-04-26-PHASE3-5).

The SCIM views are bare Django views (not DRF) so we drive the throttle
manually:

    throttle = SCIMUnauthThrottle()
    if not throttle.allow_request(request, None):
        return JsonResponse({"detail": "Rate limit exceeded"}, status=429)

Two complementary buckets:

* ``SCIMUnauthThrottle`` (scope ``scim-unauth``) — strict per-IP rate
  limiting on requests that lack a valid SCIM bearer token.  Defends
  against bearer-token guessing attacks where each attempt produces a
  401.

* ``SCIMTokenThrottle`` (scope ``scim-token``) — high-rate per-token-hash
  limit for authenticated requests.  Okta/Azure can hit ~100/min during
  a sync; the default of 600/min gives ample headroom while still
  containing a runaway IdP loop or a leaked-token scraper.

Rates resolve from ``REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']`` in
settings, which themselves accept env overrides — so ops can tune
without code changes.
"""

from __future__ import annotations

import hashlib
import os

from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle


def _env_default_rate(env_var: str, fallback: str) -> str:
    """Look up a throttle rate at *runtime* from the environment.

    Reading at import time would freeze the value for the entire process,
    making rates non-overridable in tests / under hot reloads.  Reading
    each call is cheap and also makes monkeypatch-based tests trivial.
    """
    return os.environ.get(env_var, fallback)


class _ScopedSimpleRateThrottle(SimpleRateThrottle):
    """Common base: pull the rate from settings at call time."""

    scope: str = ""

    def get_rate(self):
        rates = (
            getattr(settings, "REST_FRAMEWORK", {})
            .get("DEFAULT_THROTTLE_RATES", {})
        )
        return rates.get(self.scope) or self._env_fallback()

    def _env_fallback(self) -> str:
        raise NotImplementedError


class SCIMUnauthThrottle(_ScopedSimpleRateThrottle):
    """Per-IP throttle for requests that fail bearer-token authentication.

    Apply this *first* on every SCIM request — independent of whether
    the token verifies — so token-guess attempts are throttled even if
    the token never resolves.
    """

    scope = "scim-unauth"

    def _env_fallback(self) -> str:
        return _env_default_rate("SCIM_UNAUTH_RATE", "30/min")

    def get_cache_key(self, request, view):
        return f"throttle_scim_unauth:{self.get_ident(request)}"


class SCIMTokenThrottle(_ScopedSimpleRateThrottle):
    """Per-token-hash throttle for authenticated SCIM requests.

    The cache key is keyed off the SHA-256 of the bearer token so a leaked
    token cannot dilute the rate budget for legitimate tokens.  When the
    request is unauthenticated we fall back to per-IP — but in practice
    callers should run :class:`SCIMUnauthThrottle` first for that case.
    """

    scope = "scim-token"

    def _env_fallback(self) -> str:
        return _env_default_rate("SCIM_TOKEN_RATE", "600/min")

    def get_cache_key(self, request, view):
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if auth.startswith("Bearer "):
            raw = auth[len("Bearer "):].rstrip()
            if raw:
                token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                # First 32 hex chars = 128 bits — plenty for cache-key uniqueness.
                return f"throttle_scim_token:{token_hash[:32]}"
        # No usable token — bucket per-IP as a degenerate fallback.
        return f"throttle_scim_token:ip:{self.get_ident(request)}"


def _throttle_429():
    from django.http import JsonResponse
    return JsonResponse(
        {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
            "status": 429,
            "detail": "Rate limit exceeded.",
        },
        status=429,
        content_type="application/scim+json",
    )


def check_unauth_throttle(request):
    """Apply :class:`SCIMUnauthThrottle`.  Call this for requests that have
    NOT presented a verified SCIM bearer token (i.e. token-guess attempts).

    Returns ``None`` on allow or a 429 :class:`~django.http.JsonResponse`
    on deny.
    """
    throttle = SCIMUnauthThrottle()
    if not throttle.allow_request(request, None):
        return _throttle_429()
    return None


def check_token_throttle(request):
    """Apply :class:`SCIMTokenThrottle`.  Call this AFTER the bearer token
    has verified successfully, so authenticated traffic gets the
    higher-rate bucket keyed per token.
    """
    throttle = SCIMTokenThrottle()
    if not throttle.allow_request(request, None):
        return _throttle_429()
    return None
