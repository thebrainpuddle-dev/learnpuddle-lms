"""
apps/courses/helpers/signed_urls.py
------------------------------------
HMAC-signed, user-bound, short-TTL URL generation.

Used by:
  * SCORM export (TASK-052) — video launch stubs + quiz deep-links in exported
    SCORM packages.
  * Scheduled report delivery (TASK-053) — presigned download tokens.

Security design:
  * HMAC-SHA256 keyed on Django's SECRET_KEY so the token is opaque and
    non-forgeable without the server secret.
  * Token payload: ``{url}|{user_id}|{expires_ts}|{extra}`` — the receiving
    endpoint must verify all components.
  * User-bound — a token issued to user A cannot be used by user B because the
    user_id is part of the signed payload.
  * No tenant tokens or session data are embedded in plaintext.
  * Max TTL: 24 hours (86_400 seconds).  Callers may request a shorter TTL.

Public API:
  * ``make_signed_url(base_url, user_id, ttl_seconds, extra_params=None)``
      Returns a complete URL with ?lp_token=&lp_expires= appended.
  * ``verify_signed_url(base_url, user_id, token, expires_ts, extra_params=None)``
      Returns True iff signature is valid, token has not expired, and the
      user_id matches the one embedded in the signature payload.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.conf import settings

__all__ = [
    "make_signed_url",
    "verify_signed_url",
    "SignedUrlError",
]

MAX_TTL_SECONDS = 86_400  # 24 hours hard cap


class SignedUrlError(Exception):
    """Raised when a signed URL cannot be created or verified."""


def _get_secret() -> bytes:
    """Return Django SECRET_KEY as bytes for use in HMAC."""
    secret = getattr(settings, "SECRET_KEY", "")
    if isinstance(secret, str):
        return secret.encode()
    return secret  # type: ignore[return-value]


def _compute_hmac(payload: str) -> str:
    """Compute HMAC-SHA256 of *payload* and return hex digest."""
    return hmac.new(_get_secret(), payload.encode(), hashlib.sha256).hexdigest()


def make_signed_url(
    base_url: str,
    user_id: str,
    ttl_seconds: int,
    extra_params: dict | None = None,
) -> str:
    """Return *base_url* with HMAC-signed query parameters appended.

    Args:
        base_url: The URL to sign (may already contain query parameters).
        user_id: Opaque user identifier (typically ``str(user.id)``).
        ttl_seconds: Token lifetime.  Capped at :data:`MAX_TTL_SECONDS`.
        extra_params: Additional query-string parameters to embed (e.g.
            ``{"course_id": "..."}``) — these are INCLUDED in the signature
            so they cannot be tampered with.

    Returns:
        A URL string with ``?lp_token=…&lp_expires=…`` (and any extra params)
        appended.  The signature covers ``base_url|user_id|expires|extra``.

    Raises:
        :class:`SignedUrlError` if *base_url* is empty.
    """
    if not base_url:
        raise SignedUrlError("base_url must not be empty")

    ttl_seconds = min(max(int(ttl_seconds), 1), MAX_TTL_SECONDS)
    expires_ts = int(time.time()) + ttl_seconds

    # Canonical extra payload — deterministic sort so signature is stable.
    extra_str = ""
    if extra_params:
        extra_str = "&".join(
            f"{k}={v}" for k, v in sorted(extra_params.items())
        )

    payload = f"{base_url}|{user_id}|{expires_ts}|{extra_str}"
    token = _compute_hmac(payload)

    # Build the final URL: preserve any existing query params, then append ours.
    parsed = urlparse(base_url)
    sig_params: dict[str, str] = {"lp_token": token, "lp_expires": str(expires_ts)}
    if extra_params:
        sig_params.update(extra_params)

    # Combine existing query params with our signed params.
    existing_qs = parse_qsl(parsed.query)
    combined = existing_qs + list(sig_params.items())
    new_query = urlencode(combined)
    final = urlunparse(parsed._replace(query=new_query))
    return final


def verify_signed_url(
    base_url: str,
    user_id: str,
    token: str,
    expires_ts: int,
    extra_params: dict | None = None,
) -> bool:
    """Return True iff the HMAC token is valid for this (base_url, user, expiry).

    Args:
        base_url: The *original* base URL that was signed (without lp_token /
            lp_expires query parameters).
        user_id: User identifier — must match the one the token was issued for.
        token: The ``lp_token`` value from the request.
        expires_ts: The ``lp_expires`` value from the request (integer timestamp).
        extra_params: Same extra_params dict that was passed to
            :func:`make_signed_url`.

    Returns:
        ``True`` if the token is valid and not expired; ``False`` otherwise.
    """
    try:
        expires_ts = int(expires_ts)
    except (TypeError, ValueError):
        return False

    # Check expiry first (avoids HMAC computation on obviously stale tokens).
    if time.time() > expires_ts:
        return False

    extra_str = ""
    if extra_params:
        extra_str = "&".join(
            f"{k}={v}" for k, v in sorted(extra_params.items())
        )

    payload = f"{base_url}|{user_id}|{expires_ts}|{extra_str}"
    expected = _compute_hmac(payload)

    # Constant-time comparison to prevent timing attacks.
    return hmac.compare_digest(expected, token)
