"""
Unit tests for utils.exception_handler.custom_exception_handler

Canonical error shape under test::

    {
        "error": "<string>",           # canonical key (always present)
        "detail": "<same value>",      # legacy key (present during TASK-012 transition)
        "details": [{"field": str|None, "message": str}, ...],  # optional
        "code": "<string>"                                        # optional
    }

Transition note
---------------
The handler emits BOTH ``error`` (canonical) and ``detail`` (legacy) simultaneously
until TASK-012 completes the frontend cleanup pass.  Tests assert both keys are
present and equal for every response shape.
"""

import pytest
from unittest.mock import MagicMock, patch

from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    Throttled,
    ValidationError,
    MethodNotAllowed,
)
from rest_framework.response import Response

from utils.exception_handler import custom_exception_handler, _flatten_drf_errors


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def run_handler(exc):
    """Run the custom handler with a minimal fake context."""
    context = {"view": MagicMock(), "request": MagicMock()}
    return custom_exception_handler(exc, context)


# ---------------------------------------------------------------------------
# DRF system errors — produce {"error": "...", "code": "..."}
# ---------------------------------------------------------------------------

class TestSystemErrors:
    def test_not_authenticated_shape(self):
        exc = NotAuthenticated()
        response = run_handler(exc)

        assert response is not None
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        data = response.data
        assert isinstance(data["error"], str)
        assert data["error"] != ""
        # No per-field details for system errors
        assert "details" not in data

    def test_not_authenticated_code(self):
        exc = NotAuthenticated()
        response = run_handler(exc)
        assert response.data.get("code") == "not_authenticated"

    def test_not_authenticated_legacy_detail_key(self):
        """TASK-012 transition: 'detail' key must be present and equal 'error'."""
        exc = NotAuthenticated()
        response = run_handler(exc)
        data = response.data
        assert "detail" in data, "Legacy 'detail' key must be present during TASK-012 transition"
        assert data["detail"] == data["error"]

    def test_permission_denied_shape(self):
        exc = PermissionDenied()
        response = run_handler(exc)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert isinstance(response.data["error"], str)
        assert "details" not in response.data

    def test_permission_denied_legacy_detail_key(self):
        """TASK-012 transition: 'detail' key must be present and equal 'error'."""
        exc = PermissionDenied()
        response = run_handler(exc)
        assert response.data.get("detail") == response.data["error"]

    def test_not_found_shape(self):
        exc = NotFound()
        response = run_handler(exc)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert isinstance(response.data["error"], str)
        assert "details" not in response.data

    def test_not_found_code(self):
        exc = NotFound()
        response = run_handler(exc)
        assert response.data.get("code") == "not_found"

    def test_method_not_allowed(self):
        exc = MethodNotAllowed("DELETE")
        response = run_handler(exc)

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert isinstance(response.data["error"], str)

    def test_throttled(self):
        exc = Throttled(wait=60)
        response = run_handler(exc)

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert isinstance(response.data["error"], str)

    def test_authentication_failed(self):
        exc = AuthenticationFailed("Invalid token.")
        response = run_handler(exc)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert isinstance(response.data["error"], str)
        assert "Invalid token" in response.data["error"]

    def test_authentication_failed_legacy_detail_key(self):
        """TASK-012 transition: 'detail' mirrors 'error' on AuthenticationFailed."""
        exc = AuthenticationFailed("Invalid token.")
        response = run_handler(exc)
        assert response.data.get("detail") == response.data["error"]

    def test_error_value_is_plain_string_not_object(self):
        """The error value must be a plain string — never a dict or ErrorDetail."""
        exc = NotAuthenticated()
        response = run_handler(exc)
        assert type(response.data["error"]) is str  # noqa: E721

    def test_detail_value_is_plain_string_not_object(self):
        """TASK-012 transition: legacy 'detail' must also be a plain string."""
        exc = NotAuthenticated()
        response = run_handler(exc)
        assert type(response.data["detail"]) is str  # noqa: E721


# ---------------------------------------------------------------------------
# Serializer ValidationError — field-level errors
# ---------------------------------------------------------------------------

class TestValidationErrors:
    def test_field_validation_canonical_shape(self):
        exc = ValidationError({"email": ["Enter a valid email address."]})
        response = run_handler(exc)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.data
        assert isinstance(data["error"], str)
        assert "details" in data
        assert isinstance(data["details"], list)
        assert len(data["details"]) == 1
        entry = data["details"][0]
        assert entry["field"] == "email"
        assert "valid email" in entry["message"]

    def test_field_validation_legacy_detail_key(self):
        """TASK-012 transition: 'detail' mirrors 'error' for validation errors."""
        exc = ValidationError({"email": ["Enter a valid email address."]})
        response = run_handler(exc)
        data = response.data
        assert "detail" in data, "Legacy 'detail' key must be present during TASK-012 transition"
        assert data["detail"] == data["error"]

    def test_multiple_field_errors(self):
        exc = ValidationError({
            "email": ["Enter a valid email address.", "This field is required."],
            "password": ["Too short."],
        })
        response = run_handler(exc)

        details = response.data["details"]
        fields = [d["field"] for d in details]
        assert "email" in fields
        assert "password" in fields
        # Both email messages appear
        email_messages = [d["message"] for d in details if d["field"] == "email"]
        assert len(email_messages) == 2

    def test_non_field_errors_have_null_field(self):
        exc = ValidationError({"non_field_errors": ["Passwords do not match."]})
        response = run_handler(exc)

        details = response.data["details"]
        assert len(details) == 1
        assert details[0]["field"] is None
        assert "Passwords do not match" in details[0]["message"]

    def test_list_form_validation_error(self):
        """DRF can produce a top-level list ValidationError."""
        exc = ValidationError(["Invalid data supplied.", "Try again."])
        response = run_handler(exc)

        data = response.data
        assert isinstance(data["error"], str)
        details = data["details"]
        assert len(details) == 2
        assert all(d["field"] is None for d in details)

    def test_list_form_validation_legacy_detail_key(self):
        """TASK-012 transition: list-form ValidationError also emits 'detail'."""
        exc = ValidationError(["Something went wrong."])
        response = run_handler(exc)
        data = response.data
        assert "detail" in data
        assert data["detail"] == data["error"]

    def test_error_summary_string_for_field_errors(self):
        """Summary 'error' key must still be a string even for validation errors."""
        exc = ValidationError({"email": ["Required."]})
        response = run_handler(exc)
        assert isinstance(response.data["error"], str)

    def test_no_code_key_for_generic_validation(self):
        """'code' key is absent (or 'invalid') for standard validation errors."""
        exc = ValidationError({"email": ["Bad email."]})
        response = run_handler(exc)
        # 'invalid' is DRF's generic code — we omit it to avoid noise
        assert "code" not in response.data or response.data.get("code") != "invalid"


# ---------------------------------------------------------------------------
# Non-DRF exception — handler returns None
# ---------------------------------------------------------------------------

class TestNonDRFException:
    def test_returns_none_for_non_drf_exception(self):
        exc = ValueError("This is not a DRF exception")
        response = run_handler(exc)
        assert response is None


# ---------------------------------------------------------------------------
# _flatten_drf_errors helper
# ---------------------------------------------------------------------------

class TestFlattenDRFErrors:
    def test_dict_input(self):
        data = {"email": ["Required."], "name": ["Too long."]}
        result = _flatten_drf_errors(data)
        fields = {d["field"] for d in result}
        assert "email" in fields
        assert "name" in fields

    def test_list_input(self):
        data = ["Error one.", "Error two."]
        result = _flatten_drf_errors(data)
        assert len(result) == 2
        assert all(d["field"] is None for d in result)

    def test_non_field_errors_key(self):
        data = {"non_field_errors": ["Must accept terms."]}
        result = _flatten_drf_errors(data)
        assert result[0]["field"] is None

    def test_nested_serializer_errors(self):
        data = {"address": {"city": ["Required."]}}
        result = _flatten_drf_errors(data)
        assert result[0]["field"] == "address.city"

    def test_scalar_fallback(self):
        result = _flatten_drf_errors("plain string error")
        assert result == [{"field": None, "message": "plain string error"}]
