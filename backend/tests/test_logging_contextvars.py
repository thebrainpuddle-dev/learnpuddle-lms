# tests/test_logging_contextvars.py
"""
Tests for utils/logging.py — ContextVar-based request logging context.

Security fix: utils/logging.py previously used threading.local() for
request context storage (request_id, tenant_id, user_id). This is ASGI-unsafe
because multiple coroutines share the same OS thread under Daphne/Channels,
causing context leakage between concurrent requests.

Fix: Replaced threading.local() with three contextvars.ContextVar instances.

Tests verify:
1. set/get/clear request context round-trips correctly
2. Defaults are None (no implicit context)
3. Contexts are isolated across independent contextvars.copy_context() runs
4. Nested child contexts do NOT affect the parent
5. ContextualJsonFormatter includes the correct context fields in log output
6. set_request_context / clear_request_context are ASGI-safe (per-task scope)
7. Cross-request context cleanup (simulating middleware lifecycle)
"""

import contextvars
import json
import logging
from io import StringIO

import pytest
from django.test import TestCase, override_settings

from utils.logging import (
    _ctx_request_id,
    _ctx_tenant_id,
    _ctx_user_id,
    clear_request_context,
    get_request_context,
    set_request_context,
    ContextualJsonFormatter,
)


# ===========================================================================
# 1. Basic Context Set / Get / Clear
# ===========================================================================

class RequestContextBasicTestCase(TestCase):
    """Core set/get/clear operations on the ContextVar-backed log context."""

    def tearDown(self):
        clear_request_context()

    def test_default_context_is_all_none(self):
        """Before any set_request_context call, all fields must be None."""
        clear_request_context()
        ctx = get_request_context()
        self.assertIsNone(ctx["request_id"])
        self.assertIsNone(ctx["tenant_id"])
        self.assertIsNone(ctx["user_id"])

    def test_set_request_context_stores_all_three_fields(self):
        """set_request_context stores request_id, tenant_id, user_id."""
        set_request_context(
            request_id="req-abc-123",
            tenant_id="ten-def-456",
            user_id="usr-ghi-789",
        )
        ctx = get_request_context()
        self.assertEqual(ctx["request_id"], "req-abc-123")
        self.assertEqual(ctx["tenant_id"], "ten-def-456")
        self.assertEqual(ctx["user_id"], "usr-ghi-789")

    def test_set_partial_context_leaves_others_as_provided(self):
        """Partial set_request_context only sets the given fields."""
        set_request_context(request_id="req-only")
        ctx = get_request_context()
        self.assertEqual(ctx["request_id"], "req-only")
        # tenant_id and user_id default to None since not passed
        self.assertIsNone(ctx["tenant_id"])
        self.assertIsNone(ctx["user_id"])

    def test_clear_request_context_resets_to_none(self):
        """clear_request_context sets all fields back to None."""
        set_request_context(
            request_id="req-xyz",
            tenant_id="ten-xyz",
            user_id="usr-xyz",
        )
        clear_request_context()
        ctx = get_request_context()
        self.assertIsNone(ctx["request_id"])
        self.assertIsNone(ctx["tenant_id"])
        self.assertIsNone(ctx["user_id"])

    def test_clear_is_idempotent(self):
        """Calling clear_request_context multiple times is safe."""
        clear_request_context()
        clear_request_context()
        clear_request_context()
        ctx = get_request_context()
        self.assertIsNone(ctx["request_id"])

    def test_overwrite_existing_context(self):
        """A second set_request_context call replaces the previous value."""
        set_request_context(request_id="first")
        set_request_context(request_id="second")
        ctx = get_request_context()
        self.assertEqual(ctx["request_id"], "second")

    def test_context_var_defaults_are_none_directly(self):
        """Low-level ContextVar.get() must default to None (no implicit context)."""
        clear_request_context()
        self.assertIsNone(_ctx_request_id.get())
        self.assertIsNone(_ctx_tenant_id.get())
        self.assertIsNone(_ctx_user_id.get())


# ===========================================================================
# 2. ASGI Safety — Isolated ContextVar Runs
# ===========================================================================

class ContextVarIsolationTestCase(TestCase):
    """
    Verify that request context set in one context.run() does NOT leak
    into another — the key security property of the contextvars fix.
    """

    def tearDown(self):
        clear_request_context()

    def test_independent_context_runs_are_fully_isolated(self):
        """
        Two independent context runs (simulating concurrent ASGI requests)
        each see only their own request context values.
        """
        clear_request_context()

        ctx_a = contextvars.copy_context()
        ctx_b = contextvars.copy_context()

        results = {}

        def work_a():
            set_request_context(
                request_id="req-A",
                tenant_id="ten-A",
                user_id="usr-A",
            )
            results["a"] = get_request_context()

        def work_b():
            set_request_context(
                request_id="req-B",
                tenant_id="ten-B",
                user_id="usr-B",
            )
            results["b"] = get_request_context()

        ctx_a.run(work_a)
        ctx_b.run(work_b)

        # Each context only saw its own data
        self.assertEqual(results["a"]["request_id"], "req-A")
        self.assertEqual(results["a"]["tenant_id"], "ten-A")
        self.assertEqual(results["b"]["request_id"], "req-B")
        self.assertEqual(results["b"]["tenant_id"], "ten-B")

        # Parent context is still unset
        self.assertIsNone(get_request_context()["request_id"])

    def test_child_context_does_not_affect_parent(self):
        """
        A child context setting a request_id must NOT change the parent's value.
        This mirrors the threading.local() vs ContextVar difference.
        """
        set_request_context(request_id="parent-req")

        child_ctx = contextvars.copy_context()
        child_result = {}

        def child_work():
            set_request_context(request_id="child-req")
            child_result["ctx"] = get_request_context()

        child_ctx.run(child_work)

        # Child saw its own request_id
        self.assertEqual(child_result["ctx"]["request_id"], "child-req")

        # Parent still has its original value
        parent_ctx = get_request_context()
        self.assertEqual(parent_ctx["request_id"], "parent-req")

    def test_sequential_requests_do_not_bleed_context(self):
        """
        Simulates two sequential requests: after request 1 clears context,
        request 2 should start with clean state.
        """
        # Simulate request 1
        set_request_context(
            request_id="req-1",
            tenant_id="tenant-x",
            user_id="user-1",
        )
        ctx_after_req1 = get_request_context()
        self.assertEqual(ctx_after_req1["request_id"], "req-1")

        # Request 1 ends — middleware clears context
        clear_request_context()

        # Simulate request 2 — should start with None context
        ctx_start_req2 = get_request_context()
        self.assertIsNone(ctx_start_req2["request_id"])
        self.assertIsNone(ctx_start_req2["tenant_id"])

        # Request 2 sets its own context
        set_request_context(
            request_id="req-2",
            tenant_id="tenant-y",
            user_id="user-2",
        )
        ctx_req2 = get_request_context()
        self.assertEqual(ctx_req2["request_id"], "req-2")
        self.assertEqual(ctx_req2["tenant_id"], "tenant-y")


# ===========================================================================
# 3. ContextualJsonFormatter — Log Output Validation
# ===========================================================================

class ContextualJsonFormatterTestCase(TestCase):
    """
    Verify that ContextualJsonFormatter injects request context fields
    into the JSON log output.
    """

    def setUp(self):
        clear_request_context()

    def tearDown(self):
        clear_request_context()

    def _capture_log_record(self, logger_name="test.logger"):
        """
        Set up a logger with ContextualJsonFormatter backed by a StringIO
        stream, returning (logger, stream) so we can inspect the output.
        """
        formatter = ContextualJsonFormatter()
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(formatter)

        test_logger = logging.getLogger(logger_name)
        test_logger.handlers = [handler]
        test_logger.setLevel(logging.DEBUG)
        test_logger.propagate = False

        return test_logger, stream

    def _parse_last_log_line(self, stream):
        """Parse the last JSON line from the stream."""
        lines = [l for l in stream.getvalue().strip().splitlines() if l]
        self.assertGreater(len(lines), 0, "No log output produced")
        return json.loads(lines[-1])

    def test_formatter_includes_request_id_in_output(self):
        """Log record must contain the request_id from context."""
        set_request_context(request_id="req-fmt-001")
        logger, stream = self._capture_log_record("test.fmt.req_id")
        logger.info("Test message")
        data = self._parse_last_log_line(stream)
        self.assertEqual(data.get("request_id"), "req-fmt-001")

    def test_formatter_includes_tenant_id_in_output(self):
        """Log record must contain the tenant_id from context."""
        set_request_context(tenant_id="ten-fmt-002")
        logger, stream = self._capture_log_record("test.fmt.tenant_id")
        logger.warning("Tenant warning")
        data = self._parse_last_log_line(stream)
        self.assertEqual(data.get("tenant_id"), "ten-fmt-002")

    def test_formatter_includes_user_id_in_output(self):
        """Log record must contain the user_id from context."""
        set_request_context(user_id="usr-fmt-003")
        logger, stream = self._capture_log_record("test.fmt.user_id")
        logger.error("User error")
        data = self._parse_last_log_line(stream)
        self.assertEqual(data.get("user_id"), "usr-fmt-003")

    def test_formatter_outputs_none_when_context_not_set(self):
        """When no context is set, request_id/tenant_id/user_id should be null/None."""
        clear_request_context()
        logger, stream = self._capture_log_record("test.fmt.no_ctx")
        logger.info("No context log")
        data = self._parse_last_log_line(stream)
        self.assertIsNone(data.get("request_id"))
        self.assertIsNone(data.get("tenant_id"))
        self.assertIsNone(data.get("user_id"))

    def test_formatter_includes_all_three_fields_simultaneously(self):
        """All three context fields must appear together in the same log record."""
        set_request_context(
            request_id="req-all",
            tenant_id="ten-all",
            user_id="usr-all",
        )
        logger, stream = self._capture_log_record("test.fmt.all_fields")
        logger.info("All context fields")
        data = self._parse_last_log_line(stream)
        self.assertEqual(data.get("request_id"), "req-all")
        self.assertEqual(data.get("tenant_id"), "ten-all")
        self.assertEqual(data.get("user_id"), "usr-all")

    def test_formatter_includes_timestamp_field(self):
        """Log output must include an ISO 8601 timestamp."""
        set_request_context(request_id="req-ts")
        logger, stream = self._capture_log_record("test.fmt.timestamp")
        logger.info("Timestamped log")
        data = self._parse_last_log_line(stream)
        ts = data.get("timestamp")
        self.assertIsNotNone(ts, "timestamp field must be present")
        # Should be parseable as ISO 8601
        self.assertIn("T", ts, "timestamp should be ISO 8601 format (has 'T' separator)")

    def test_formatter_includes_level_field(self):
        """Log output must include the level field."""
        logger, stream = self._capture_log_record("test.fmt.level")
        logger.warning("A warning")
        data = self._parse_last_log_line(stream)
        self.assertEqual(data.get("level"), "WARNING")

    def test_formatter_includes_logger_name(self):
        """Log output must include the logger name."""
        logger, stream = self._capture_log_record("test.fmt.logger_name")
        logger.info("Named logger")
        data = self._parse_last_log_line(stream)
        self.assertEqual(data.get("logger"), "test.fmt.logger_name")

    def test_formatter_context_reflects_cleared_state(self):
        """After clear_request_context, new log records should have null context."""
        set_request_context(request_id="req-before-clear")
        clear_request_context()
        logger, stream = self._capture_log_record("test.fmt.after_clear")
        logger.info("After clear")
        data = self._parse_last_log_line(stream)
        self.assertIsNone(data.get("request_id"))

    def test_formatter_context_updates_between_records(self):
        """Changing context between log calls must be reflected immediately."""
        logger, stream = self._capture_log_record("test.fmt.ctx_update")

        set_request_context(request_id="req-first")
        logger.info("First record")

        set_request_context(request_id="req-second")
        logger.info("Second record")

        lines = [l for l in stream.getvalue().strip().splitlines() if l]
        self.assertEqual(len(lines), 2)

        first_data = json.loads(lines[0])
        second_data = json.loads(lines[1])

        self.assertEqual(first_data.get("request_id"), "req-first")
        self.assertEqual(second_data.get("request_id"), "req-second")


# ===========================================================================
# 4. Middleware Lifecycle Simulation
# ===========================================================================

class MiddlewareLifecycleTestCase(TestCase):
    """
    Simulate the full request lifecycle: context set by middleware,
    used in views, cleared after response. Verifies the pattern is
    safe for both WSGI and ASGI usage.
    """

    def tearDown(self):
        clear_request_context()

    def test_request_context_set_used_and_cleared(self):
        """
        Full request lifecycle:
        1. Middleware sets context at request start
        2. View/service reads context
        3. Middleware clears context at request end
        4. Next request starts with empty context
        """
        # Step 1: Middleware sets context
        set_request_context(
            request_id="lifecycle-req-001",
            tenant_id="lifecycle-tenant",
            user_id="lifecycle-user",
        )

        # Step 2: View/service reads context
        ctx = get_request_context()
        self.assertEqual(ctx["request_id"], "lifecycle-req-001")
        self.assertEqual(ctx["tenant_id"], "lifecycle-tenant")
        self.assertEqual(ctx["user_id"], "lifecycle-user")

        # Step 3: Middleware clears context after response
        clear_request_context()

        # Step 4: Next request starts with empty context
        ctx_empty = get_request_context()
        self.assertIsNone(ctx_empty["request_id"])
        self.assertIsNone(ctx_empty["tenant_id"])
        self.assertIsNone(ctx_empty["user_id"])

    def test_context_not_shared_across_simulated_parallel_asgi_requests(self):
        """
        If two ASGI coroutines run in parallel (different context copies),
        setting context in one must not affect the other.

        This is the core regression test for the threading.local → ContextVar fix.
        """
        clear_request_context()

        ctx_req1 = contextvars.copy_context()
        ctx_req2 = contextvars.copy_context()

        seen = {}

        def handle_request_1():
            set_request_context(
                request_id="req-parallel-1",
                tenant_id="tenant-alpha",
                user_id="user-alpha",
            )
            # Simulate some async work
            seen["req1"] = get_request_context()

        def handle_request_2():
            set_request_context(
                request_id="req-parallel-2",
                tenant_id="tenant-beta",
                user_id="user-beta",
            )
            seen["req2"] = get_request_context()

        ctx_req1.run(handle_request_1)
        ctx_req2.run(handle_request_2)

        # Each request context is independent
        self.assertEqual(seen["req1"]["tenant_id"], "tenant-alpha")
        self.assertEqual(seen["req2"]["tenant_id"], "tenant-beta")
        self.assertNotEqual(
            seen["req1"]["tenant_id"],
            seen["req2"]["tenant_id"],
        )

        # Parent context unchanged
        parent_ctx = get_request_context()
        self.assertIsNone(parent_ctx["request_id"])
