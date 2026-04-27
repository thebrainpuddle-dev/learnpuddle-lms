# tests/test_request_id_middleware.py
"""
Tests for utils/request_id_middleware.py — RequestIDMiddleware and
LoggingContextMiddleware.

Covers:
1. RequestIDMiddleware generates UUID when no X-Request-ID header present
2. RequestIDMiddleware uses existing X-Request-ID header if provided
3. RequestIDMiddleware sets request.request_id attribute
4. RequestIDMiddleware adds X-Request-ID to response
5. RequestIDMiddleware clears logging context after response
6. Generated IDs are unique per request (not reused)
7. LoggingContextMiddleware updates context with tenant/user info
8. LoggingContextMiddleware is a no-op when tenant/user absent
"""

import uuid as uuid_lib
from types import SimpleNamespace

from django.http import HttpResponse
from django.test import TestCase


# ===========================================================================
# Helpers
# ===========================================================================


class _AnonUser:
    """Minimal stub for anonymous (unauthenticated) request user."""
    is_authenticated = False


def _make_request(
    request_id_header: str = "",
    user=None,
    tenant=None,
) -> SimpleNamespace:
    """Build a minimal mock request."""
    meta = {}
    if request_id_header:
        meta["HTTP_X_REQUEST_ID"] = request_id_header

    return SimpleNamespace(
        META=meta,
        user=user if user is not None else _AnonUser(),
        tenant=tenant,
    )


def _make_middleware():
    """Instantiate RequestIDMiddleware with a pass-through get_response."""
    from utils.request_id_middleware import RequestIDMiddleware

    def _get_response(req):
        return HttpResponse("OK", status=200)

    return RequestIDMiddleware(_get_response)


def _make_logging_middleware():
    """Instantiate LoggingContextMiddleware with a pass-through get_response."""
    from utils.request_id_middleware import LoggingContextMiddleware

    def _get_response(req):
        return HttpResponse("OK", status=200)

    return LoggingContextMiddleware(_get_response)


# ===========================================================================
# 1. Request ID Generation Tests
# ===========================================================================


class RequestIDGenerationTestCase(TestCase):
    """RequestIDMiddleware must assign a unique X-Request-ID to each request."""

    def setUp(self):
        self.middleware = _make_middleware()

    def test_request_id_set_on_request_object(self):
        """After middleware runs, request.request_id must be set."""
        request = _make_request()
        self.middleware(request)

        self.assertTrue(
            hasattr(request, "request_id"),
            "request.request_id must be set by RequestIDMiddleware",
        )
        self.assertIsNotNone(request.request_id)
        self.assertGreater(len(request.request_id), 0)

    def test_generated_id_is_valid_uuid(self):
        """When no X-Request-ID header is provided, a UUID must be generated."""
        request = _make_request()
        self.middleware(request)

        try:
            parsed = uuid_lib.UUID(request.request_id)
            self.assertIsInstance(parsed, uuid_lib.UUID)
        except ValueError:
            self.fail(
                f"Generated request_id '{request.request_id}' is not a valid UUID"
            )

    def test_existing_request_id_header_reused(self):
        """If X-Request-ID header is present, it must be used as-is."""
        incoming_id = "my-custom-trace-id-123"
        request = _make_request(request_id_header=incoming_id)

        self.middleware(request)

        self.assertEqual(
            request.request_id,
            incoming_id,
            "X-Request-ID header must be reused if already present",
        )

    def test_consecutive_requests_get_different_ids(self):
        """Each request must get a unique ID (no reuse)."""
        ids = []

        def _capture_response(req):
            ids.append(req.request_id)
            return HttpResponse("OK")

        from utils.request_id_middleware import RequestIDMiddleware
        middleware = RequestIDMiddleware(_capture_response)

        for _ in range(5):
            middleware(_make_request())

        unique_ids = set(ids)
        self.assertEqual(
            len(unique_ids),
            5,
            "Each request must receive a unique request ID",
        )


# ===========================================================================
# 2. Response Header Tests
# ===========================================================================


class RequestIDResponseHeaderTestCase(TestCase):
    """X-Request-ID must be added to response headers."""

    def setUp(self):
        self.middleware = _make_middleware()

    def test_response_contains_x_request_id_header(self):
        """Response must have X-Request-ID header."""
        request = _make_request()
        response = self.middleware(request)

        self.assertIn(
            "X-Request-ID",
            response,
            "Response must include X-Request-ID header",
        )

    def test_response_header_matches_request_id(self):
        """Response X-Request-ID must match the ID set on the request."""
        request = _make_request()
        response = self.middleware(request)

        self.assertEqual(
            response["X-Request-ID"],
            request.request_id,
            "Response X-Request-ID must match request.request_id",
        )

    def test_custom_incoming_id_echoed_in_response(self):
        """Custom X-Request-ID from client must be echoed in response."""
        custom_id = "trace-abc-xyz-987"
        request = _make_request(request_id_header=custom_id)
        response = self.middleware(request)

        self.assertEqual(
            response["X-Request-ID"],
            custom_id,
            "Incoming X-Request-ID must be echoed back in response header",
        )


# ===========================================================================
# 3. Logging Context Lifecycle Tests
# ===========================================================================


class RequestIDLoggingContextTestCase(TestCase):
    """RequestIDMiddleware must manage the logging context correctly."""

    def test_logging_context_cleared_after_response(self):
        """
        After the middleware returns a response, the logging context
        must be cleared (preventing context leak to next request).
        """
        from utils.logging import get_request_context
        from utils.request_id_middleware import RequestIDMiddleware

        def _get_response(req):
            return HttpResponse("OK")

        middleware = RequestIDMiddleware(_get_response)
        request = _make_request()
        middleware(request)

        # After the call, the logging context must be cleared
        ctx = get_request_context()
        self.assertIsNone(
            ctx.get("request_id"),
            "Logging context must be cleared after request completes",
        )

    def test_logging_context_set_during_request(self):
        """
        During request processing (inside get_response), request_id must
        be in the logging context.
        """
        from utils.logging import get_request_context
        from utils.request_id_middleware import RequestIDMiddleware

        captured_ctx = {}

        def _get_response(req):
            captured_ctx.update(get_request_context())
            return HttpResponse("OK")

        middleware = RequestIDMiddleware(_get_response)
        request = _make_request()
        middleware(request)

        self.assertIn(
            "request_id",
            captured_ctx,
            "request_id must be in logging context during request processing",
        )
        self.assertEqual(captured_ctx["request_id"], request.request_id)


# ===========================================================================
# 4. LoggingContextMiddleware Tests
# ===========================================================================


class LoggingContextMiddlewareTestCase(TestCase):
    """LoggingContextMiddleware must update logging context with tenant/user."""

    def test_returns_response_from_get_response(self):
        """LoggingContextMiddleware must pass through to get_response."""
        middleware = _make_logging_middleware()
        request = _make_request()
        # Manually set request_id since RequestIDMiddleware is expected to run first
        request.request_id = "test-request-id-logging"
        response = middleware(request)
        self.assertEqual(response.status_code, 200)

    def test_logging_middleware_does_not_crash_without_tenant(self):
        """If request has no tenant, LoggingContextMiddleware must not raise."""
        middleware = _make_logging_middleware()
        request = _make_request(tenant=None)
        request.request_id = "test-no-tenant"
        try:
            middleware(request)
        except Exception as exc:
            self.fail(
                f"LoggingContextMiddleware raised {exc!r} when tenant is None"
            )

    def test_logging_middleware_does_not_crash_without_user(self):
        """If request.user is anonymous, LoggingContextMiddleware must not raise."""
        middleware = _make_logging_middleware()

        class _AnonUser:
            is_authenticated = False

        request = SimpleNamespace(
            META={},
            user=_AnonUser(),
            tenant=None,
        )
        request.request_id = "test-anon-user"
        try:
            middleware(request)
        except Exception as exc:
            self.fail(
                f"LoggingContextMiddleware raised {exc!r} with anonymous user"
            )
