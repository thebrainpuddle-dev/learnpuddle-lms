from __future__ import annotations

import hashlib
import hmac
import time
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response


SERVICE_TIMESTAMP_HEADER = "HTTP_X_LP_SERVICE_TIMESTAMP"
SERVICE_NONCE_HEADER = "HTTP_X_LP_SERVICE_NONCE"
SERVICE_SIGNATURE_HEADER = "HTTP_X_LP_SERVICE_SIGNATURE"
MAX_CLOCK_SKEW_SECONDS = 60


def _body_digest(request) -> str:
    body = request._request.body if hasattr(request, "_request") else request.body
    return hashlib.sha256(body or b"").hexdigest()


def _canonical_message(request, timestamp: str, nonce: str) -> bytes:
    method = request.method.upper()
    path = request.get_full_path()
    return f"{timestamp}\n{nonce}\n{method}\n{path}\n{_body_digest(request)}".encode()


def require_openmaic_service(view_func):
    """Authenticate a private OpenMAIC-to-Django request.

    The nonce is claimed with Redis SET-NX semantics, so a correctly signed
    request cannot be replayed inside the timestamp window.
    """

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        secret = getattr(settings, "OPENMAIC_SERVICE_SECRET", "")
        if not secret:
            return Response(
                {"error": "OpenMAIC service authentication is not configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        timestamp = request.META.get(SERVICE_TIMESTAMP_HEADER, "")
        nonce = request.META.get(SERVICE_NONCE_HEADER, "")
        supplied = request.META.get(SERVICE_SIGNATURE_HEADER, "")
        try:
            timestamp_int = int(timestamp)
        except (TypeError, ValueError):
            return Response({"error": "Invalid service timestamp"}, status=401)

        if abs(int(time.time()) - timestamp_int) > MAX_CLOCK_SKEW_SECONDS:
            return Response({"error": "Expired service request"}, status=401)
        if len(nonce) < 16 or len(nonce) > 128:
            return Response({"error": "Invalid service nonce"}, status=401)

        expected = hmac.new(
            secret.encode(),
            _canonical_message(request, timestamp, nonce),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, supplied):
            return Response({"error": "Invalid service signature"}, status=401)

        replay_key = f"openmaic:service-nonce:{nonce}"
        try:
            claimed = cache.add(replay_key, "1", timeout=MAX_CLOCK_SKEW_SECONDS * 2)
        except Exception:
            return Response({"error": "Service replay protection unavailable"}, status=503)
        if not claimed:
            return Response({"error": "Replayed service request"}, status=409)

        return view_func(request, *args, **kwargs)

    return wrapped
