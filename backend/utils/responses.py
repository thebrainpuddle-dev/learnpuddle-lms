"""
Standardised API error and success responses for LearnPuddle LMS.

Canonical error shape
---------------------
All manual error responses produced by ``error_response()`` and all DRF
exception responses processed by ``utils.exception_handler.custom_exception_handler``
use the **same** shape::

    {
        "error": "<human-readable summary>",   # always present, always a string
        "details": [                            # optional — only when field/extra info available
            {"field": "email",  "message": "Enter a valid email address."},
            {"field": null,     "message": "Non-field message."}
        ],
        "code": "optional_snake_case_code"     # optional — machine-readable code for FE routing
    }

Quick-reference
---------------
* ``error`` is **always a plain string** — never a dict, never null.
* ``details`` is a **list of objects** when present, each with ``field``
  (string or null) and ``message`` (string).
* Extra keyword arguments (e.g. ``upgrade_required=True``) are promoted to
  top-level keys on the response body so the frontend can act on them.
* ``code`` is only included when the caller explicitly passes it or when the
  DRF exception handler finds a machine-readable code.

Frontend extraction recipe::

    const msg = err.response?.data?.error ?? "Unexpected error";
    const details = err.response?.data?.details ?? [];

Usage examples::

    from utils.responses import error_response, success_response

    # Simple error
    return error_response("Not found", status_code=404)

    # Error with per-field details
    return error_response(
        "Validation failed",
        status_code=400,
        field_errors={"email": ["Required"]},
    )

    # Error with machine-readable code + extra key
    return error_response(
        "Certificates not available on your plan.",
        status_code=403,
        code="upgrade_required",
        upgrade_required=True,
    )
"""

from rest_framework.response import Response


def error_response(
    message: str,
    status_code: int = 400,
    field_errors=None,
    code: str | None = None,
    **extra,
):
    """Return a consistently formatted error response.

    Parameters
    ----------
    message : str
        Human-readable error summary.  Always surfaces as ``{"error": "<message>"}``.
    status_code : int
        HTTP status code (default 400).
    field_errors : dict | list | None
        Per-field validation errors.  Dict form ``{"email": ["Required"]}`` is
        normalised to the canonical ``details`` list.  A plain list of strings
        becomes non-field (``field: null``) detail entries.
    code : str | None
        Optional machine-readable snake_case code for the frontend.
    **extra
        Additional key/value pairs merged into the top-level response body
        (e.g. ``upgrade_required=True``).
    """
    body: dict = {"error": str(message)}

    if field_errors:
        details = _normalise_field_errors(field_errors)
        if details:
            body["details"] = details

    if code:
        body["code"] = code

    if extra:
        # Merge extra kwargs at top level (not inside "error")
        body.update(extra)

    return Response(body, status=status_code)


def _normalise_field_errors(field_errors) -> list[dict]:
    """Convert ``field_errors`` into the canonical ``details`` list format.

    Accepts:
    - ``dict``: ``{"email": ["msg1"], "name": "msg2"}``
    - ``list``: ``["msg1", "msg2"]``
    - ``str``: treated as a single non-field message
    """
    if isinstance(field_errors, list):
        return [{"field": None, "message": str(item)} for item in field_errors]

    if isinstance(field_errors, dict):
        details = []
        for field, messages in field_errors.items():
            if isinstance(messages, list):
                for msg in messages:
                    details.append({
                        "field": field if field != "non_field_errors" else None,
                        "message": str(msg),
                    })
            else:
                details.append({
                    "field": field if field != "non_field_errors" else None,
                    "message": str(messages),
                })
        return details

    if isinstance(field_errors, str):
        return [{"field": None, "message": field_errors}]

    return []


def success_response(data=None, message: str = "", status: int = 200):
    """Return a consistently formatted success response.

    Parameters
    ----------
    data : any
        Response payload.  When provided it is returned as-is (the top-level
        response body).
    message : str
        Simple acknowledgement message used when ``data`` is None.
    status : int
        HTTP status code (default 200).
    """
    if data is not None:
        return Response(data, status=status)
    return Response({"message": message}, status=status)
