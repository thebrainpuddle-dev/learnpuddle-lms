"""
Unit tests for utils.responses.error_response and success_response

Canonical shape::

    {
        "error": "<string>",
        "details": [{"field": str|None, "message": str}, ...],  # optional
        "code": "<string>"                                        # optional
    }
"""

import pytest

from rest_framework import status as drf_status

from utils.responses import error_response, success_response


# ---------------------------------------------------------------------------
# error_response — basic cases
# ---------------------------------------------------------------------------

class TestErrorResponseShape:
    def test_simple_message_string(self):
        resp = error_response("Something went wrong")
        data = resp.data

        assert isinstance(data["error"], str)
        assert data["error"] == "Something went wrong"

    def test_default_status_is_400(self):
        resp = error_response("Bad request")
        assert resp.status_code == 400

    def test_custom_status_code(self):
        resp = error_response("Not found", status_code=404)
        assert resp.status_code == 404

    def test_no_details_when_no_field_errors(self):
        resp = error_response("Simple error")
        assert "details" not in resp.data

    def test_no_code_when_not_provided(self):
        resp = error_response("Simple error")
        assert "code" not in resp.data

    def test_error_is_always_a_string(self):
        resp = error_response("Must be string")
        assert type(resp.data["error"]) is str  # noqa: E721


# ---------------------------------------------------------------------------
# error_response — field_errors
# ---------------------------------------------------------------------------

class TestErrorResponseFieldErrors:
    def test_dict_field_errors_produce_details(self):
        resp = error_response(
            "Validation failed",
            field_errors={"email": ["Enter a valid email address."]},
        )
        data = resp.data
        assert "details" in data
        assert isinstance(data["details"], list)
        entry = data["details"][0]
        assert entry["field"] == "email"
        assert "valid email" in entry["message"]

    def test_multiple_fields(self):
        resp = error_response(
            "Validation failed",
            field_errors={
                "email": ["Required."],
                "password": ["Too short.", "No uppercase letter."],
            },
        )
        details = resp.data["details"]
        fields = [d["field"] for d in details]
        assert "email" in fields
        assert "password" in fields
        # Two password messages
        pw_msgs = [d["message"] for d in details if d["field"] == "password"]
        assert len(pw_msgs) == 2

    def test_list_field_errors(self):
        resp = error_response("Errors", field_errors=["Error one.", "Error two."])
        details = resp.data["details"]
        assert len(details) == 2
        assert all(d["field"] is None for d in details)

    def test_non_field_errors_dict_key(self):
        resp = error_response(
            "Validation failed",
            field_errors={"non_field_errors": ["Passwords do not match."]},
        )
        details = resp.data["details"]
        assert details[0]["field"] is None
        assert "Passwords do not match" in details[0]["message"]

    def test_none_field_errors_no_details(self):
        resp = error_response("Error", field_errors=None)
        assert "details" not in resp.data

    def test_empty_dict_field_errors_no_details(self):
        resp = error_response("Error", field_errors={})
        assert "details" not in resp.data


# ---------------------------------------------------------------------------
# error_response — code and extra kwargs
# ---------------------------------------------------------------------------

class TestErrorResponseCodeAndExtra:
    def test_code_included_when_provided(self):
        resp = error_response("Upgrade needed", code="upgrade_required")
        assert resp.data["code"] == "upgrade_required"

    def test_extra_kwargs_promoted_to_top_level(self):
        resp = error_response(
            "Certificates not available on your plan.",
            status_code=403,
            code="upgrade_required",
            upgrade_required=True,
        )
        data = resp.data
        assert data["error"] == "Certificates not available on your plan."
        assert data["code"] == "upgrade_required"
        assert data["upgrade_required"] is True

    def test_extra_kwargs_do_not_nest_under_error(self):
        resp = error_response("Error", extra_flag=True)
        # error is still a plain string
        assert isinstance(resp.data["error"], str)
        assert resp.data["extra_flag"] is True

    def test_full_shape_with_all_parts(self):
        resp = error_response(
            "Validation failed",
            status_code=422,
            field_errors={"email": ["Required."]},
            code="validation_error",
        )
        data = resp.data
        assert data["error"] == "Validation failed"
        assert data["code"] == "validation_error"
        assert data["details"][0]["field"] == "email"
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# success_response
# ---------------------------------------------------------------------------

class TestSuccessResponse:
    def test_with_data(self):
        resp = success_response({"id": 1, "name": "Test"})
        assert resp.status_code == 200
        assert resp.data == {"id": 1, "name": "Test"}

    def test_with_message(self):
        resp = success_response(message="Created successfully")
        assert resp.status_code == 200
        assert resp.data == {"message": "Created successfully"}

    def test_custom_status(self):
        resp = success_response({"id": 1}, status=201)
        assert resp.status_code == 201

    def test_empty_call(self):
        resp = success_response()
        assert resp.status_code == 200
        assert resp.data == {"message": ""}
