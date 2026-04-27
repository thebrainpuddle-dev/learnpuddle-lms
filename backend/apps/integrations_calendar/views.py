"""
Views for integrations_calendar.

Endpoints:
  POST   /api/v1/admin/calendar/{provider}/connect/
  GET    /api/v1/calendar/{provider}/callback/
  POST   /api/v1/admin/calendar/{provider}/disconnect/
  GET    /api/v1/calendar/ical/{user_uuid}/{token}.ics
  POST   /api/v1/calendar/ical/revoke/
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from utils.decorators import admin_only

logger = logging.getLogger(__name__)

VALID_PROVIDERS = {"google", "outlook"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rate_limit_ical(token_hash: str) -> bool:
    """
    Redis-backed rate limit: 60 requests / hour / token.
    Returns True if request is allowed, False if limit exceeded.
    Fail-closed: if Redis is unavailable, deny the request.
    """
    try:
        from django_redis import get_redis_connection
        r = get_redis_connection("default")
    except Exception:
        try:
            import redis as redis_lib
            r = redis_lib.from_url(
                getattr(settings, "REDIS_URL", "redis://localhost:6379/0"),
                socket_timeout=1,
            )
        except Exception:
            logger.error("ical_rate_limit: Redis unavailable — denying request (fail-closed)")
            return False

    key = f"ical_rate:{token_hash}"
    try:
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, 3600)
        results = pipe.execute()
        count = results[0]
        return count <= 60
    except Exception:
        logger.error("ical_rate_limit: Redis error — denying request (fail-closed)")
        return False


def _get_provider_module(provider: str):
    """Return the provider module for google or outlook."""
    if provider == "google":
        from apps.integrations_calendar.providers import google as m
        return m
    elif provider == "outlook":
        from apps.integrations_calendar.providers import outlook as m
        return m
    return None


def _log_audit(request, action: str, target_type: str, target_id: str, changes: dict = None):
    try:
        from apps.tenants.models import AuditLog
        AuditLog.objects.create(
            tenant=getattr(request, "tenant", None),
            actor=request.user if request.user.is_authenticated else None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            changes=changes or {},
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
            request_id=request.META.get("HTTP_X_REQUEST_ID", ""),
        )
    except Exception:
        logger.exception("calendar: audit log write failed")


# ---------------------------------------------------------------------------
# POST /api/v1/admin/calendar/{provider}/connect/
# ---------------------------------------------------------------------------


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
def connect_calendar(request, provider: str):
    """
    Return the OAuth authorisation URL for the given provider.
    A short-lived state token is generated and returned for CSRF protection.
    """
    if provider not in VALID_PROVIDERS:
        return Response({"error": f"Unknown provider '{provider}'."}, status=400)

    provider_mod = _get_provider_module(provider)
    state = secrets.token_urlsafe(32)

    try:
        _result = provider_mod.get_auth_url(state=state)
    except ImportError as exc:
        return Response({"error": str(exc)}, status=501)
    except Exception as exc:
        logger.exception("calendar: connect failed for provider=%s", provider)
        return Response({"error": "Failed to generate auth URL.", "detail": str(exc)}, status=500)

    # Outlook's get_auth_url returns the full MSAL flow dict (code_verifier, nonce,
    # PKCE challenge, redirect_uri, scope) so acquire_token_by_auth_code_flow can
    # run nonce/PKCE validation on the callback.
    # Google's get_auth_url returns a plain URL string; store an existence sentinel.
    if isinstance(_result, dict):
        auth_url = _result["auth_uri"]
        _cache_value = _result  # full MSAL flow dict (Outlook)
    else:
        auth_url = _result
        _cache_value = 1  # existence-only sentinel (Google)

    # RFC 6749 §10.12 — store state server-side so the callback can verify it.
    # Keyed to (provider, user.pk, state) so tokens from one user cannot be
    # replayed by a different user. TTL=600 s covers any reasonable redirect lag.
    # Google: stores integer 1 (existence sentinel).
    # Outlook: stores full MSAL flow dict for nonce/PKCE validation on callback.
    cache.set(
        f"oauth_state:{provider}:{request.user.pk}:{state}",
        _cache_value,
        timeout=600,
    )

    return Response({
        "auth_url": auth_url,
        "state": state,
        "provider": provider,
    })


# ---------------------------------------------------------------------------
# GET /api/v1/calendar/{provider}/callback/
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
def calendar_callback(request, provider: str):
    """
    OAuth redirect callback. Exchanges code for tokens, creates CalendarConnection,
    triggers initial sync.
    """
    if provider not in VALID_PROVIDERS:
        return Response({"error": f"Unknown provider '{provider}'."}, status=400)

    code = request.query_params.get("code", "")
    state = request.query_params.get("state", "")

    if not code:
        return Response({"error": "Missing 'code' parameter."}, status=400)

    # -----------------------------------------------------------------------
    # RFC 6749 §10.12 — CSRF protection: validate state before token exchange.
    # The state must have been issued by connect_calendar for THIS user/provider
    # and must not have been used before (single-use, keyed to user.pk).
    # -----------------------------------------------------------------------
    if not state:
        _log_audit(
            request,
            action="OAUTH_STATE_MISMATCH",
            target_type="CalendarConnection",
            target_id="",
            changes={"provider": provider, "reason": "missing_state"},
        )
        return Response(
            {"error": "OAUTH_STATE_MISMATCH", "detail": "Missing state."},
            status=400,
        )
    _state_cache_key = f"oauth_state:{provider}:{request.user.pk}:{state}"
    _cached_value = cache.get(_state_cache_key)
    if _cached_value is None:  # key absent → unknown or expired state
        _log_audit(
            request,
            action="OAUTH_STATE_MISMATCH",
            target_type="CalendarConnection",
            target_id="",
            changes={"provider": provider, "reason": "unknown_or_expired_state",
                     "state_prefix": state[:8]},
        )
        return Response(
            {"error": "OAUTH_STATE_MISMATCH", "detail": "Unknown or expired state."},
            status=400,
        )
    # Consume the state token (single-use) before the network call.
    cache.delete(_state_cache_key)

    provider_mod = _get_provider_module(provider)

    try:
        if provider == "google":
            token_data = provider_mod.exchange_code(code=code, state=state)
        else:  # outlook
            # Pass the stored MSAL flow dict (code_verifier, nonce, PKCE challenge)
            # so acquire_token_by_auth_code_flow can run full nonce/PKCE validation.
            # For older/legacy flows that stored integer 1, fall back to minimal stub
            # (server-side state check above already prevents CSRF in that case).
            msal_flow = _cached_value if isinstance(_cached_value, dict) else {"state": state}
            token_data = provider_mod.exchange_code(code=code, state=state, session_state=msal_flow)
    except ImportError as exc:
        return Response({"error": str(exc)}, status=501)
    except Exception as exc:
        logger.exception("calendar: token exchange failed for provider=%s", provider)
        return Response({"error": "Token exchange failed.", "detail": str(exc)}, status=502)

    # Upsert CalendarConnection for this user + provider.
    from apps.integrations_calendar.models import CalendarConnection

    tenant = getattr(request, "tenant", None)
    connection, created = CalendarConnection.objects.get_or_create(
        user=request.user,
        provider=provider,
        defaults={"tenant": tenant},
    )
    connection.tenant = tenant
    connection.status = CalendarConnection.STATUS_ACTIVE
    connection.provider_user_id = token_data.get("provider_user_id", "")
    connection.scopes = token_data.get("scopes", "")
    connection.error = ""
    connection.set_access_token(token_data.get("access_token", ""))
    connection.set_refresh_token(token_data.get("refresh_token", ""))

    # Ensure a dedicated LP calendar exists at the provider.
    try:
        cal_id = provider_mod.ensure_learnpuddle_calendar(connection)
        connection.target_calendar_id = cal_id
    except Exception:
        logger.exception("calendar: ensure_learnpuddle_calendar failed for provider=%s", provider)
        # Non-fatal — continue; sync will retry next beat cycle.

    connection.save()

    # Trigger initial sync asynchronously.
    try:
        from apps.integrations_calendar.tasks import sync_calendar_connection
        sync_calendar_connection.delay(str(connection.pk))
    except Exception:
        logger.exception("calendar: failed to enqueue initial sync for connection=%s", connection.pk)

    _log_audit(
        request,
        action="CONNECT_CALENDAR",
        target_type="CalendarConnection",
        target_id=str(connection.pk),
        changes={"provider": provider, "created": created},
    )

    return Response({
        "connection_id": str(connection.pk),
        "provider": provider,
        "status": connection.status,
        "created": created,
    }, status=201 if created else 200)


# ---------------------------------------------------------------------------
# POST /api/v1/admin/calendar/{provider}/disconnect/
# ---------------------------------------------------------------------------


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
def disconnect_calendar(request, provider: str):
    """
    Revoke OAuth tokens at provider, flip connection to 'revoked'.
    """
    if provider not in VALID_PROVIDERS:
        return Response({"error": f"Unknown provider '{provider}'."}, status=400)

    from apps.integrations_calendar.models import CalendarConnection

    try:
        connection = CalendarConnection.objects.get(
            user=request.user,
            provider=provider,
        )
    except CalendarConnection.DoesNotExist:
        return Response({"error": "No active connection found."}, status=404)

    provider_mod = _get_provider_module(provider)
    try:
        provider_mod.revoke_tokens(connection)
    except Exception:
        logger.exception("calendar: revoke_tokens failed for provider=%s connection=%s", provider, connection.pk)
        # Non-fatal — still mark as revoked locally.

    connection.status = CalendarConnection.STATUS_REVOKED
    connection.access_token_encrypted = ""
    connection.refresh_token_encrypted = ""
    connection.save(update_fields=["status", "access_token_encrypted", "refresh_token_encrypted"])

    _log_audit(
        request,
        action="DISCONNECT_CALENDAR",
        target_type="CalendarConnection",
        target_id=str(connection.pk),
        changes={"provider": provider},
    )

    return Response({"detail": f"{provider} calendar disconnected."})


# ---------------------------------------------------------------------------
# GET /api/v1/calendar/ical/{user_uuid}/{token}.ics  (public, token-auth)
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([AllowAny])
def ical_feed(request, user_uuid: str, token: str):
    """
    Public iCal feed — authenticates via hashed token stored in ICalToken.
    Rate-limited to 60/hr/token via Redis (fail-closed → 404 on error).
    Returns text/calendar with 10-minute cache headers.
    """
    from apps.users.models import User
    from apps.integrations_calendar.models import ICalToken

    # Resolve user.
    try:
        user = User.objects.get(pk=user_uuid)
    except (User.DoesNotExist, ValueError):
        return HttpResponse(status=404)

    # Verify token.
    ical_token = ICalToken.verify(user=user, raw_token=token)
    if ical_token is None:
        return HttpResponse(status=404)

    # Rate limit.
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    if not _rate_limit_ical(token_hash):
        return HttpResponse(status=429)

    # Server-side Redis body cache (10 minutes, keyed by token hash).
    # This avoids rebuilding the iCal feed on every calendar client poll
    # while still honoring revocation (revoke rotates the token → new hash).
    _ICAL_CACHE_TTL = 600  # seconds (matches Cache-Control: max-age=600)
    cache_key = f"ical:body:{token_hash}"
    ical_bytes = None
    try:
        from django.core.cache import cache as _cache
        ical_bytes = _cache.get(cache_key)
    except Exception:
        logger.warning("ical_feed: cache GET failed for user=%s — will rebuild", user_uuid)

    if ical_bytes is None:
        # Cache miss — build and populate.
        try:
            from apps.integrations_calendar.ical_builder import build_ical_feed
            ical_bytes = build_ical_feed(user=user)
        except Exception:
            logger.exception("ical_feed: build failed for user=%s", user_uuid)
            return HttpResponse(status=500)

        try:
            from django.core.cache import cache as _cache
            _cache.set(cache_key, ical_bytes, timeout=_ICAL_CACHE_TTL)
        except Exception:
            logger.warning("ical_feed: cache SET failed for user=%s — serving uncached", user_uuid)

    response = HttpResponse(ical_bytes, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="learnpuddle.ics"'
    response["Cache-Control"] = "private, max-age=600"
    return response


# ---------------------------------------------------------------------------
# POST /api/v1/calendar/ical/revoke/  (authenticated)
# ---------------------------------------------------------------------------


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ical_revoke(request):
    """
    Revoke the current iCal token and issue a new one (token rotation).
    Returns the new feed URL.
    """
    from apps.integrations_calendar.models import ICalToken

    # Revoke all existing active tokens for this user.
    ICalToken.objects.filter(
        user=request.user,
        revoked_at__isnull=True,
    ).update(revoked_at=timezone.now())

    # Issue a new token.
    instance, raw_token = ICalToken.generate(user=request.user)

    platform_domain = getattr(settings, "PLATFORM_DOMAIN", "learnpuddle.com")
    feed_url = (
        f"https://{platform_domain}/api/v1/calendar/ical"
        f"/{request.user.pk}/{raw_token}.ics"
    )

    return Response({
        "token_id": str(instance.pk),
        "feed_url": feed_url,
        "note": "Previous tokens have been revoked. Update any calendar subscriptions with the new URL.",
    })
