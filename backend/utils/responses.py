"""
Standardized API error/success responses.

All custom error responses should use the ``error_response`` helper so the
frontend can rely on a single shape:

    {
        "error": {
            "message": "Human-readable summary",
            "fields": {"email": ["Already taken."]}   # optional
        }
    }

Usage:
    from utils.responses import error_response, success_response

    return error_response("Not found", status_code=404)
    return error_response(
        "Validation failed",
        status_code=400,
        field_errors={"email": ["Required"]},
    )
    return success_response({"id": "..."}, status=201)
"""

from rest_framework.response import Response


def error_response(message: str, status_code: int = 400, field_errors=None, **extra):
    """Return a consistently formatted error response.

    Parameters
    ----------
    message : str
        Human-readable error summary.
    status_code : int
        HTTP status code (default 400).
    field_errors : dict | None
        Per-field validation errors, e.g. ``{"email": ["Required"]}``.
    **extra
        Additional top-level keys merged into the ``error`` object
        (e.g. ``upgrade_required=True``).
    """
    error_body: dict = {"message": message}
    if field_errors:
        error_body["fields"] = field_errors
    if extra:
        error_body.update(extra)
    return Response({"error": error_body}, status=status_code)


def success_response(data=None, message: str = "", status=200):
    """Return a consistently formatted success response."""
    if data is not None:
        return Response(data, status=status)
    return Response({"message": message}, status=status)
