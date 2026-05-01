# utils/exception_handler.py
"""
Custom DRF exception handler that normalises all DRF exception responses to the
LearnPuddle canonical error shape:

    {
        "error": "<human-readable summary>",          # canonical key
        "details": [                                  # optional, present when there are
            {"field": "email", "message": "Enter a valid email address."},
            {"field": null,    "message": "Non-field error message."}
        ],
        "code": "optional_snake_case_code"            # only when DRF provides one
    }

TASK-008 AC6 — cleanup complete (2026-04-30)
--------------------------------------------
The legacy ``detail`` key has been removed.  Frontend migration of all
``data.detail`` reads to ``data?.error ?? data?.detail`` was confirmed
complete by frontend-engineer on 2026-04-30 (see inbox note
``FE-TASK008-DETAIL-KEY-MIGRATION-COMPLETE-2026-04-30.md``).
The ``Deprecation: detail-key`` monitoring header has also been removed.

Error sources and their handling
---------------------------------
1. **DRF system errors** (``AuthenticationFailed``, ``NotAuthenticated``,
   ``PermissionDenied``, ``NotFound``, ``MethodNotAllowed``, ``Throttled``, etc.)
   These produce ``{"detail": ErrorDetail("...", code="...")}`` from DRF's default
   handler.  We rename ``detail`` → ``error``, promote the code, and leave
   ``details`` absent (no per-field breakdown).

   Result::

       {"error": "Authentication credentials were not provided.", "code": "not_authenticated"}

2. **Serializer ``ValidationError``** (field-level)
   DRF produces ``{"email": ["Enter a valid email."], "password": ["Too short."]}``
   (no top-level ``detail`` key).  We flatten this into the canonical shape:

   Result::

       {
           "error": "Validation failed.",
           "details": [
               {"field": "email",    "message": "Enter a valid email."},
               {"field": "password", "message": "Too short."}
           ]
       }

3. **Serializer ``ValidationError``** (non-field / list form)
   DRF sometimes produces ``["error1", "error2"]`` or ``{"non_field_errors": [...]}``
   at the top level.  We normalise these into ``details`` with ``field: null``.

4. **Non-dict / non-list ``response.data``**
   Rare but possible.  Converted to ``{"error": str(response.data)}``.

Usage (settings.py)::

    REST_FRAMEWORK = {
        ...
        'EXCEPTION_HANDLER': 'utils.exception_handler.custom_exception_handler',
    }
"""

from rest_framework.views import exception_handler as drf_default_exception_handler


def _flatten_drf_errors(data) -> list[dict]:
    """Recursively flatten a DRF validation error dict/list into ``details`` entries.

    Parameters
    ----------
    data:
        The ``response.data`` produced by DRF for a ``ValidationError``.
        May be a dict (field → list[str]) or a list of strings.

    Returns
    -------
    list[dict]
        Each entry has keys ``field`` (str or None) and ``message`` (str).
    """
    details = []

    if isinstance(data, list):
        for item in data:
            details.append({"field": None, "message": str(item)})
        return details

    if isinstance(data, dict):
        for field, messages in data.items():
            # DRF occasionally nests dicts (nested serializer errors).
            if isinstance(messages, dict):
                for sub_field, sub_messages in messages.items():
                    if isinstance(sub_messages, list):
                        for msg in sub_messages:
                            details.append({
                                "field": f"{field}.{sub_field}",
                                "message": str(msg),
                            })
                    else:
                        details.append({
                            "field": f"{field}.{sub_field}",
                            "message": str(sub_messages),
                        })
            elif isinstance(messages, list):
                for msg in messages:
                    if field == "non_field_errors":
                        details.append({"field": None, "message": str(msg)})
                    else:
                        details.append({"field": field, "message": str(msg)})
            else:
                # Scalar value (rare)
                details.append({"field": field, "message": str(messages)})
        return details

    # Fallback: wrap the whole thing as a non-field message
    return [{"field": None, "message": str(data)}]


def custom_exception_handler(exc, context):
    """Normalise DRF exceptions to the LearnPuddle canonical error shape.

    All error responses produced by this handler will have the shape::

        {"error": "...", "details": [...], "code": "..."}

    where ``details`` and ``code`` are present only when applicable.
    """
    response = drf_default_exception_handler(exc, context)

    if response is None:
        # Non-DRF exception — let Django's 500 handler deal with it.
        return None

    data = response.data

    # ── Case 1: DRF system error — top-level "detail" key ────────────────────
    if isinstance(data, dict) and "detail" in data and len(data) == 1:
        detail_value = data["detail"]
        error_str = str(detail_value)
        new_data: dict = {
            "error": error_str,
        }
        # Preserve error code when DRF provides one (e.g. "not_authenticated")
        code = getattr(detail_value, "code", None)
        if code and code not in ("invalid", "error"):
            new_data["code"] = str(code)
        response.data = new_data
        return response

    # ── Case 1b: DRF system error — "detail" alongside other keys (rare) ─────
    if isinstance(data, dict) and "detail" in data:
        detail_value = data.pop("detail")
        error_str = str(detail_value)
        data["error"] = error_str
        code = getattr(detail_value, "code", None)
        if code and code not in ("invalid", "error"):
            data["code"] = str(code)
        response.data = data
        return response

    # ── Case 2: Serializer ValidationError — dict without "detail" ───────────
    if isinstance(data, dict):
        # This is a field-level validation error from a serializer.
        # Flatten into canonical shape.
        details = _flatten_drf_errors(data)
        response.data = {
            "error": "Validation failed.",
            "details": details,
        }
        return response

    # ── Case 3: Serializer ValidationError — list form ───────────────────────
    if isinstance(data, list):
        details = _flatten_drf_errors(data)
        response.data = {
            "error": "Validation failed.",
            "details": details,
        }
        return response

    # ── Case 4: Any other shape — wrap as flat string ─────────────────────────
    error_str = str(data)
    response.data = {
        "error": error_str,
    }
    return response
