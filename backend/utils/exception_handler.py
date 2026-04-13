# utils/exception_handler.py
"""
Custom DRF exception handler that normalises DRF's auto-generated error responses
to the LearnPuddle standard format:

    {"error": "<human-readable message>"}

DRF's default handler produces:

    {"detail": "Authentication credentials were not provided."}  # 401
    {"detail": "Not found."}                                      # 404
    {"detail": "Method \"DELETE\" not allowed."}                  # 405

These are converted to:

    {"error": "Authentication credentials were not provided."}

Field-level validation errors produced by serializers (e.g.
``{"email": ["Enter a valid email address."]}``) are left unchanged because
the frontend uses them to display per-field feedback in forms.

Usage (settings.py):
    REST_FRAMEWORK = {
        ...
        'EXCEPTION_HANDLER': 'utils.exception_handler.custom_exception_handler',
    }
"""

from rest_framework.views import exception_handler as drf_default_exception_handler


def custom_exception_handler(exc, context):
    """Normalise DRF ``detail`` error key to ``error`` for consistent API responses.

    Passes the exception to DRF's default handler first so that all the standard
    Django/DRF exception types (AuthenticationFailed, NotFound, PermissionDenied,
    MethodNotAllowed, etc.) are correctly converted to Response objects with the
    right HTTP status codes.

    Post-processing:
    - If the response body is a dict containing only a ``"detail"`` key, rename
      it to ``"error"`` so the frontend always sees ``{"error": "..."}``.
    - If the response body contains both ``"detail"`` and other keys (rare), only
      the rename is performed — no other keys are modified.
    - Serializer validation errors (format: ``{"field": ["msg"]}``) are NOT
      altered because they do not have a top-level ``"detail"`` key.
    """
    response = drf_default_exception_handler(exc, context)

    if response is not None and isinstance(response.data, dict):
        if "detail" in response.data:
            # Convert ErrorDetail (or plain string) to a clean string
            detail_value = response.data.pop("detail")
            response.data["error"] = str(detail_value)

    return response
