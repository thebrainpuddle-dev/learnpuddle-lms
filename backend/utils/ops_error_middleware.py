import json
from typing import Any

from apps.ops.services import PROBLEM_STATUS_CODES, record_route_error


def _portal_from_request(request) -> str:
    explicit = str(request.META.get("HTTP_X_LP_PORTAL", "")).upper().strip()
    if explicit in {"SUPER_ADMIN", "TENANT_ADMIN", "TEACHER"}:
        return explicit

    path = str(getattr(request, "path", "") or "")
    if path.startswith("/api/super-admin/"):
        return "SUPER_ADMIN"
    if path.startswith("/api/teacher/"):
        return "TEACHER"
    if path.startswith("/api/"):
        return "TENANT_ADMIN"
    return "UNKNOWN"


def _payload_from_request(request) -> dict[str, Any]:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return dict(request.GET)
    try:
        raw_body = request.body
    except Exception:
        return {}
    if not raw_body:
        return {}
    try:
        parsed = json.loads(raw_body.decode("utf-8"))
        if isinstance(parsed, dict):
            return parsed
        return {"payload": parsed}
    except Exception:
        return {"raw": str(raw_body[:1000])}


def _response_excerpt(response) -> str:
    if getattr(response, "streaming", False):
        return ""
    try:
        return response.content.decode("utf-8", errors="ignore")[:2000]
    except Exception:
        return ""


class OpsRouteErrorCaptureMiddleware:
    """
    Capture problematic API responses (500/429) with tenant + route context.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        path = str(getattr(request, "path", "") or "")
        status_code = int(getattr(response, "status_code", 0) or 0)
        if not path.startswith("/api/") or status_code not in PROBLEM_STATUS_CODES:
            return response

        # Avoid self-report loops for the lightweight ingest endpoint.
        if path.endswith("/ops/client-errors/ingest/"):
            return response

        try:
            record_route_error(
                tenant=getattr(request, "tenant", None),
                portal=_portal_from_request(request),
                tab_key=str(request.META.get("HTTP_X_LP_TAB", "")).strip().lower(),
                route_path=str(request.META.get("HTTP_X_LP_ROUTE", "")).strip()[:255],
                component_name=str(request.META.get("HTTP_X_LP_COMPONENT", "")).strip()[:128],
                endpoint=path,
                method=request.method,
                status_code=status_code,
                request_id=str(getattr(request, "request_id", "") or "")[:64],
                payload=_payload_from_request(request),
                response_excerpt=_response_excerpt(response),
                error_message="",
            )
        except Exception:
            # Best effort only; never break request flow.
            pass

        return response
