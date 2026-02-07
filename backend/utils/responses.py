"""
Standardized API error/success responses.

Usage:
    from utils.responses import error_response, success_response

    return error_response("Not found", status=404)
    return error_response("Validation failed", details={"email": ["Required"]}, status=400)
    return success_response({"id": "..."}, status=201)
"""

from rest_framework.response import Response


def error_response(message: str, details=None, status=400, **extra):
    """Return a consistently formatted error response."""
    body = {"error": message}
    if details:
        body["details"] = details
    body.update(extra)
    return Response(body, status=status)


def success_response(data=None, message: str = "", status=200):
    """Return a consistently formatted success response."""
    if data is not None:
        return Response(data, status=status)
    return Response({"message": message}, status=status)
