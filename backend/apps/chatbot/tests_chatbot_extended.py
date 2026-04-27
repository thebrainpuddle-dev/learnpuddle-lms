"""
Extended chatbot test coverage — gap-filling tests for TASK-059.

Covers security properties and view behaviours NOT exercised by tests_chatbot.py:

  1.  ask_view HTTP 400 response shape for QUESTION_TOO_LONG
  2.  ask_view: top_k=0 → 400 (min_value=1)
  3.  ask_view: top_k=11 → 400 (max_value=10)
  4.  ask_view: course_id not in tenant → 404 (DoesNotExist branch)
  5.  ask_view: SUPER_ADMIN bypasses course scope guard
  6.  ask_view: log_audit changes dict NEVER contains question text
  7.  ask_view: views.py logger NEVER emits question text
  8.  history_list_view: teacher cannot see other teacher's rows
  9.  history_list_view: admin ?user_id= filter returns other-user rows
 10.  history_list_view: teacher ?user_id= param is silently ignored
 11.  history_list_view: page_size=0 clamped to 1
 12.  history_list_view: page_size=200 clamped to 100
 13.  history_list_view: non-integer page defaults to 1
 14.  history_list_view: rows older than 30 days NOT returned
 15.  history_delete_view: SUPER_ADMIN can delete any row in the tenant
 16.  ChatQueryHistorySerializer: "question" field NOT in serialized output
 17.  _rate_limit_key: key rotates per hour bucket
 18.  _check_course_scope: SUPER_ADMIN bypasses scope check

All LLM / DB calls are mocked; no live HTTP or Celery required.
"""

from __future__ import annotations

import datetime
import logging
import time
import uuid
from unittest.mock import MagicMock, call, patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.request import Request as DRFRequest
from rest_framework.test import APIClient


# ---------------------------------------------------------------------------
# Shared helpers (same as tests_chatbot.py)
# ---------------------------------------------------------------------------

def _make_tenant(tenant_id=None):
    t = MagicMock()
    t.id = tenant_id or uuid.uuid4()
    t.name = "Test School"
    return t


def _make_user(user_id=None, role="TEACHER", tenant=None):
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.role = role
    u.is_authenticated = True
    u.tenant_id = getattr(tenant, "id", None)
    return u


def _make_req(user=None, tenant=None, data=None, query_params=None):
    """Build a minimal mocked DRF Request suitable for direct view calls."""
    req = MagicMock(spec=DRFRequest)
    req.user = user or _make_user()
    req.tenant = tenant or _make_tenant()
    req.data = data or {}
    req.query_params = query_params or {}
    return req


def _make_rag_answer():
    """Build a minimal RAGAnswer for mocking answer_question()."""
    from apps.chatbot.rag_service import Citation, RAGAnswer
    return RAGAnswer(
        answer="The answer is 42 [1].",
        citations=[
            Citation(
                block=1,
                source_type="content",
                source_id=str(uuid.uuid4()),
                title="Test Content",
                score=0.91,
            )
        ],
        grounded=True,
        provider="stub",
        model="stub-1",
        tokens_prompt=25,
        tokens_completion=15,
        latency_ms=80,
        retrieved_chunk_ids=[],
    )


# ---------------------------------------------------------------------------
# 1–3: ask_view HTTP 400 response shapes
# ---------------------------------------------------------------------------


class TestAskViewValidationResponses(TestCase):
    """ask_view returns the correct error body for invalid inputs."""

    def _ask(self, data, rate_limit_ok=True):
        from apps.chatbot.views import ask_view

        req = _make_req(data=data)
        with patch(
            "apps.chatbot.views._check_and_increment_rate_limit",
            return_value=None if rate_limit_ok else MagicMock(status_code=429),
        ):
            return ask_view(req)

    def test_question_too_long_response_has_error_key(self):
        """
        ask_view with question > 2000 chars returns 400 with
        error='QUESTION_TOO_LONG' in the response body.

        Complements the existing test_question_too_long_returns_400 which
        only validates the serializer, not the full view HTTP response.
        """
        resp = self._ask({"question": "q" * 2001})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["error"], "QUESTION_TOO_LONG")
        self.assertIn("2000", resp.data.get("detail", ""))

    def test_top_k_below_minimum_returns_400(self):
        """top_k=0 violates min_value=1 constraint → 400."""
        resp = self._ask({"question": "How do I teach fractions?", "top_k": 0})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("top_k", resp.data)

    def test_top_k_above_maximum_returns_400(self):
        """top_k=11 violates max_value=10 constraint → 400."""
        resp = self._ask({"question": "How do I teach fractions?", "top_k": 11})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("top_k", resp.data)


# ---------------------------------------------------------------------------
# 4: _check_course_scope: course not in tenant → 404
# ---------------------------------------------------------------------------


class TestCourseScopeGuardNotFound(TestCase):
    """_check_course_scope returns 404 when course doesn't exist in tenant."""

    def test_course_not_in_tenant_returns_404(self):
        """
        When the course exists in another tenant (or not at all), the
        DoesNotExist branch returns 404 NOT_FOUND.

        Complements the existing test_course_scope_guard_non_enrolled_403 which
        only covers the enrolled-check path.
        """
        from apps.chatbot.views import _check_course_scope

        tenant = _make_tenant()
        user = _make_user(role="TEACHER", tenant=tenant)
        req = _make_req(user=user, tenant=tenant)
        course_id = uuid.uuid4()

        with patch("apps.chatbot.views.Course") as MockCourse:
            from apps.courses.models import Course as RealCourse

            MockCourse.all_objects.get.side_effect = RealCourse.DoesNotExist

            response = _check_course_scope(req, course_id)

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"], "NOT_FOUND")


# ---------------------------------------------------------------------------
# 5 & 18: SUPER_ADMIN bypasses course scope
# ---------------------------------------------------------------------------


class TestSuperAdminCourseScopeBypass(TestCase):
    """SUPER_ADMIN bypasses the course scope guard without a DB query."""

    def test_super_admin_bypasses_scope_check(self):
        """
        SUPER_ADMIN never hits the DB in _check_course_scope — returns None
        immediately (allow).

        Complements test_course_scope_guard_admin_allowed which only tests
        SCHOOL_ADMIN.
        """
        from apps.chatbot.views import _check_course_scope

        tenant = _make_tenant()
        super_admin = _make_user(role="SUPER_ADMIN", tenant=tenant)
        req = _make_req(user=super_admin, tenant=tenant)
        course_id = uuid.uuid4()

        with patch("apps.chatbot.views.Course") as MockCourse:
            result = _check_course_scope(req, course_id)
            # Course DB should NOT have been queried — admin short-circuits
            MockCourse.all_objects.get.assert_not_called()

        self.assertIsNone(result)

    def test_super_admin_can_delete_other_users_row(self):
        """SUPER_ADMIN (role in "SUPER_ADMIN") is treated as is_admin — can delete."""
        from apps.chatbot.views import history_delete_view

        tenant = _make_tenant()
        super_admin = _make_user(role="SUPER_ADMIN", tenant=tenant)
        other_user_id = uuid.uuid4()
        query_id = uuid.uuid4()

        mock_query = MagicMock()
        mock_query.id = query_id
        mock_query.user_id = other_user_id
        mock_query.tenant_id = tenant.id
        mock_query.grounded = False

        req = _make_req(user=super_admin, tenant=tenant)

        with (
            patch("apps.chatbot.views.ChatQuery") as MockChatQuery,
            patch("apps.chatbot.views.log_audit"),
        ):
            MockChatQuery.all_objects.get.return_value = mock_query
            response = history_delete_view(req, query_id=str(query_id))

        self.assertEqual(response.status_code, 204)
        mock_query.delete.assert_called_once()


# ---------------------------------------------------------------------------
# 6: log_audit changes dict NEVER contains "question"
# ---------------------------------------------------------------------------


class TestAskViewPIIInAuditLog(TestCase):
    """question text must never appear in log_audit changes dict."""

    def test_log_audit_changes_do_not_contain_question_text(self):
        """
        The log_audit call in ask_view must not include the question text in
        the `changes` dict.  PII should be stored only in the ChatQuery row,
        never in audit logs.
        """
        from apps.chatbot.views import ask_view

        secret_question = "SUPER-SECRET-QUESTION-DO-NOT-LOG"
        tenant = _make_tenant()
        user = _make_user(role="TEACHER", tenant=tenant)
        req = _make_req(
            user=user,
            tenant=tenant,
            data={"question": secret_question},
        )

        captured_changes = {}

        def capture_audit(**kwargs):
            captured_changes.update(kwargs.get("changes", {}))

        mock_query = MagicMock()
        mock_query.id = uuid.uuid4()

        with (
            patch("apps.chatbot.views._check_and_increment_rate_limit", return_value=None),
            patch("apps.chatbot.views._check_course_scope", return_value=None),
            patch("apps.chatbot.views.answer_question", return_value=_make_rag_answer()),
            patch("apps.chatbot.views.ChatQuery") as MockChatQuery,
            patch("apps.chatbot.views.log_audit", side_effect=capture_audit),
        ):
            MockChatQuery.objects.create.return_value = mock_query
            ask_view(req)

        # question text must not appear in any audit changes value
        for key, value in captured_changes.items():
            self.assertNotEqual(
                value,
                secret_question,
                f"Question text found in audit changes under key '{key}'",
            )
        self.assertNotIn(
            "question",
            captured_changes,
            "Audit changes dict must not have a 'question' key",
        )


# ---------------------------------------------------------------------------
# 7: views.py logger NEVER emits question text
# ---------------------------------------------------------------------------


class TestAskViewPIIInLogger(TestCase):
    """The chatbot.ask logger must never emit the question text."""

    def test_views_logger_does_not_emit_question_text(self):
        """
        The logger.info call inside ask_view must not include question text.
        This complements the existing rag_service PII test which checks the
        rag_service logger; here we check the views logger.
        """
        from apps.chatbot.views import ask_view

        secret_question = "PRIVATE-VIEW-LOGGER-TEST-DO-NOT-LEAK"
        tenant = _make_tenant()
        user = _make_user(role="TEACHER", tenant=tenant)
        req = _make_req(
            user=user,
            tenant=tenant,
            data={"question": secret_question},
        )

        mock_query = MagicMock()
        mock_query.id = uuid.uuid4()

        log_output: list[str] = []

        class CapturingHandler(logging.Handler):
            def emit(self, record):
                log_output.append(self.format(record))

        handler = CapturingHandler()
        chatbot_logger = logging.getLogger("apps.chatbot.views")
        chatbot_logger.addHandler(handler)
        chatbot_logger.setLevel(logging.DEBUG)

        try:
            with (
                patch("apps.chatbot.views._check_and_increment_rate_limit", return_value=None),
                patch("apps.chatbot.views._check_course_scope", return_value=None),
                patch("apps.chatbot.views.answer_question", return_value=_make_rag_answer()),
                patch("apps.chatbot.views.ChatQuery") as MockChatQuery,
                patch("apps.chatbot.views.log_audit"),
            ):
                MockChatQuery.objects.create.return_value = mock_query
                ask_view(req)
        finally:
            chatbot_logger.removeHandler(handler)

        for line in log_output:
            self.assertNotIn(
                secret_question,
                line,
                f"Question text leaked into views logger: {line!r}",
            )


# ---------------------------------------------------------------------------
# 8–10: history_list_view — tenant isolation and ?user_id= filter
# ---------------------------------------------------------------------------


class TestHistoryListViewAccess(TestCase):
    """history_list_view returns correctly scoped results."""

    def _history_list(self, user, tenant, query_params=None):
        from apps.chatbot.views import history_list_view

        req = _make_req(user=user, tenant=tenant, query_params=query_params or {})
        return history_list_view(req)

    def _make_query_row(self, user_id, tenant_id, created_at=None):
        q = MagicMock()
        q.id = uuid.uuid4()
        q.user_id = user_id
        q.tenant_id = tenant_id
        q.created_at = created_at or timezone.now()
        return q

    def test_teacher_cannot_see_other_teachers_rows(self):
        """
        history_list_view for a TEACHER only returns rows where user=request.user.
        Another teacher's rows must not appear.
        """
        tenant = _make_tenant()
        teacher_a = _make_user(role="TEACHER", tenant=tenant)
        teacher_b_id = uuid.uuid4()

        # Create 2 rows: one for teacher_a, one for teacher_b
        row_a = self._make_query_row(teacher_a.id, tenant.id)
        row_b = self._make_query_row(teacher_b_id, tenant.id)

        with patch("apps.chatbot.views.ChatQuery") as MockChatQuery:
            # The teacher filter (user=teacher_a) should only surface row_a
            filtered_qs = MagicMock()
            filtered_qs.__getitem__ = lambda self, s: []
            filtered_qs.count.return_value = 1
            # Simulate: filter(user=teacher_a) returns only row_a
            filtered_qs.__iter__ = lambda self: iter([row_a])

            base_qs = MagicMock()
            base_qs.order_by.return_value = base_qs
            # filter(user=teacher_a) call
            base_qs.filter.return_value = filtered_qs
            MockChatQuery.all_objects.filter.return_value = base_qs

            response = self._history_list(teacher_a, tenant)

        self.assertEqual(response.status_code, 200)
        # Verify the queryset was filtered to the specific teacher user
        # (the second filter call filters by user=teacher_a)
        filter_calls = base_qs.filter.call_args_list
        user_filter_found = any(
            "user" in str(c) for c in filter_calls
        )
        self.assertTrue(
            user_filter_found,
            "Expected history to be filtered by user, but no 'user' filter found",
        )

    def test_admin_user_id_filter_applies_to_queryset(self):
        """
        Admin with ?user_id=<other_user_id> gets that user's rows.
        """
        tenant = _make_tenant()
        admin = _make_user(role="SCHOOL_ADMIN", tenant=tenant)
        other_user_id = str(uuid.uuid4())

        with patch("apps.chatbot.views.ChatQuery") as MockChatQuery:
            scoped_qs = MagicMock()
            scoped_qs.__getitem__ = lambda self, s: []
            scoped_qs.count.return_value = 3
            scoped_qs.__iter__ = lambda self: iter([])

            base_qs = MagicMock()
            base_qs.order_by.return_value = base_qs
            base_qs.filter.return_value = scoped_qs
            MockChatQuery.all_objects.filter.return_value = base_qs

            response = self._history_list(
                admin, tenant, query_params={"user_id": other_user_id}
            )

        self.assertEqual(response.status_code, 200)
        # Verify ?user_id= filter was applied
        filter_calls_args = [str(c) for c in base_qs.filter.call_args_list]
        user_id_filtered = any(other_user_id in s for s in filter_calls_args)
        self.assertTrue(
            user_id_filtered,
            f"Expected filter(user_id={other_user_id}) to be called; calls: {filter_calls_args}",
        )

    def test_teacher_user_id_filter_is_ignored(self):
        """
        A TEACHER providing ?user_id= should be ignored — they only see
        their own history.  The non-admin path applies user=request.user
        regardless of the query_params.
        """
        tenant = _make_tenant()
        teacher = _make_user(role="TEACHER", tenant=tenant)
        other_user_id = str(uuid.uuid4())

        with patch("apps.chatbot.views.ChatQuery") as MockChatQuery:
            filtered_qs = MagicMock()
            filtered_qs.__getitem__ = lambda self, s: []
            filtered_qs.count.return_value = 0
            filtered_qs.__iter__ = lambda self: iter([])

            base_qs = MagicMock()
            base_qs.order_by.return_value = base_qs
            base_qs.filter.return_value = filtered_qs
            MockChatQuery.all_objects.filter.return_value = base_qs

            response = self._history_list(
                teacher, tenant, query_params={"user_id": other_user_id}
            )

        self.assertEqual(response.status_code, 200)
        # The filter should use user=teacher (not user_id=other_user_id)
        filter_calls_args = [str(c) for c in base_qs.filter.call_args_list]
        other_id_filtered = any(other_user_id in s for s in filter_calls_args)
        self.assertFalse(
            other_id_filtered,
            f"Teacher's ?user_id= param must be silently ignored; calls: {filter_calls_args}",
        )


# ---------------------------------------------------------------------------
# 11–13: history_list_view — pagination clamping
# ---------------------------------------------------------------------------


class TestHistoryListViewPagination(TestCase):
    """history_list_view correctly clamps page_size and page params."""

    def _history_list(self, tenant, user, query_params=None):
        from apps.chatbot.views import history_list_view

        req = _make_req(user=user, tenant=tenant, query_params=query_params or {})
        with patch("apps.chatbot.views.ChatQuery") as MockChatQuery:
            qs = MagicMock()
            qs.order_by.return_value = qs
            qs.filter.return_value = qs
            qs.__getitem__ = lambda self, s: []
            qs.count.return_value = 0
            qs.__iter__ = lambda self: iter([])
            MockChatQuery.all_objects.filter.return_value = qs
            return history_list_view(req)

    def test_page_size_zero_clamped_to_one(self):
        """page_size=0 is below min; must be clamped to 1."""
        tenant = _make_tenant()
        user = _make_user(tenant=tenant)
        resp = self._history_list(tenant, user, query_params={"page_size": "0"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["page_size"], 1)

    def test_page_size_above_max_clamped_to_100(self):
        """page_size=200 exceeds max; must be clamped to 100."""
        tenant = _make_tenant()
        user = _make_user(tenant=tenant)
        resp = self._history_list(tenant, user, query_params={"page_size": "200"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["page_size"], 100)

    def test_non_integer_page_defaults_to_one(self):
        """page='abc' is not a valid integer; must default to 1."""
        tenant = _make_tenant()
        user = _make_user(tenant=tenant)
        resp = self._history_list(tenant, user, query_params={"page": "abc"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["page"], 1)

    def test_non_integer_page_size_defaults_to_twenty(self):
        """page_size='xyz' is not a valid integer; must default to 20."""
        tenant = _make_tenant()
        user = _make_user(tenant=tenant)
        resp = self._history_list(tenant, user, query_params={"page_size": "xyz"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["page_size"], 20)


# ---------------------------------------------------------------------------
# 14: history_list_view — 30-day window filter
# ---------------------------------------------------------------------------


class TestHistoryListView30DayWindow(TestCase):
    """history_list_view base queryset uses a 30-day window filter."""

    def test_base_queryset_has_30_day_created_at_filter(self):
        """
        The queryset passed to all_objects.filter must include
        created_at__gte=(now - 30 days).
        """
        from apps.chatbot.views import history_list_view

        tenant = _make_tenant()
        user = _make_user(role="TEACHER", tenant=tenant)
        req = _make_req(user=user, tenant=tenant)

        now_approx = timezone.now()

        with patch("apps.chatbot.views.ChatQuery") as MockChatQuery:
            qs = MagicMock()
            qs.order_by.return_value = qs
            qs.filter.return_value = qs
            qs.__getitem__ = lambda self, s: []
            qs.count.return_value = 0
            qs.__iter__ = lambda self: iter([])
            MockChatQuery.all_objects.filter.return_value = qs

            history_list_view(req)

        # Verify the initial filter includes created_at__gte with ~30d cutoff
        call_kwargs = MockChatQuery.all_objects.filter.call_args[1]
        self.assertIn(
            "created_at__gte",
            call_kwargs,
            "Base queryset must filter by created_at__gte (30-day window)",
        )
        cutoff = call_kwargs["created_at__gte"]
        expected_cutoff = now_approx - datetime.timedelta(days=30)
        diff_seconds = abs((cutoff - expected_cutoff).total_seconds())
        self.assertLess(
            diff_seconds,
            5,
            f"30-day window cutoff is off by {diff_seconds:.1f}s (expected ≈{expected_cutoff})",
        )


# ---------------------------------------------------------------------------
# 16: ChatQueryHistorySerializer — question field absent from output
# ---------------------------------------------------------------------------


class TestChatQueryHistorySerializerNoPII(TestCase):
    """ChatQueryHistorySerializer must not expose the question field."""

    def test_question_field_not_in_serializer_output(self):
        """
        ChatQueryHistorySerializer.to_representation must not include
        a 'question' key, protecting teacher PII in the history API.
        """
        from apps.chatbot.serializers import ChatQueryHistorySerializer

        # Build a mock ChatQuery-like object with all expected attributes
        mock_row = MagicMock()
        mock_row.id = uuid.uuid4()
        mock_row.course_id = None
        mock_row.question = "SUPER-SECRET-TEACHER-QUESTION"
        mock_row.answer = "Some answer."
        mock_row.citations = []
        mock_row.grounded = False
        mock_row.provider = "stub"
        mock_row.model = "stub-1"
        mock_row.tokens_prompt = 20
        mock_row.tokens_completion = 10
        mock_row.latency_ms = 50
        mock_row.created_at = timezone.now()

        serializer = ChatQueryHistorySerializer(instance=mock_row)
        data = serializer.data

        self.assertNotIn(
            "question",
            data,
            "ChatQueryHistorySerializer must NOT expose the 'question' field (PII protection)",
        )
        # Sanity: expected fields should be present
        for field in ("id", "answer", "grounded", "provider", "created_at"):
            self.assertIn(field, data, f"Expected field '{field}' missing from serializer output")


# ---------------------------------------------------------------------------
# 17: _rate_limit_key time-bucketing
# ---------------------------------------------------------------------------


class TestRateLimitKeyBucketing(TestCase):
    """_rate_limit_key produces bucket keys that rotate once per RATE_LIMIT_WINDOW."""

    def test_same_second_same_key(self):
        """Two calls within the same hour window produce identical keys."""
        from apps.chatbot.views import RATE_LIMIT_WINDOW, _rate_limit_key

        user_id = "user-bucket-test"
        fixed_time = 1_700_000_000.0  # fixed epoch second

        with patch("apps.chatbot.views.time") as mock_time:
            mock_time.time.return_value = fixed_time
            key1 = _rate_limit_key(user_id)

        # Same bucket: shift by 30 seconds (still same hour)
        with patch("apps.chatbot.views.time") as mock_time:
            mock_time.time.return_value = fixed_time + 30
            key2 = _rate_limit_key(user_id)

        self.assertEqual(
            key1,
            key2,
            "Keys in the same RATE_LIMIT_WINDOW bucket must be identical",
        )

    def test_different_hours_different_keys(self):
        """Two calls in different hour windows produce different keys."""
        from apps.chatbot.views import RATE_LIMIT_WINDOW, _rate_limit_key

        user_id = "user-bucket-rotate"
        fixed_time = 1_700_000_000.0

        with patch("apps.chatbot.views.time") as mock_time:
            mock_time.time.return_value = fixed_time
            key_hour1 = _rate_limit_key(user_id)

        # Advance by one full window (next bucket)
        with patch("apps.chatbot.views.time") as mock_time:
            mock_time.time.return_value = fixed_time + RATE_LIMIT_WINDOW
            key_hour2 = _rate_limit_key(user_id)

        self.assertNotEqual(
            key_hour1,
            key_hour2,
            "Keys in different RATE_LIMIT_WINDOW buckets must differ (key rotation)",
        )

    def test_key_format_includes_user_id(self):
        """The rate limit key must include the user_id to isolate per-user counts."""
        from apps.chatbot.views import _rate_limit_key

        user_a = "user-111"
        user_b = "user-222"
        fixed_time = 1_700_000_000.0

        with patch("apps.chatbot.views.time") as mock_time:
            mock_time.time.return_value = fixed_time
            key_a = _rate_limit_key(user_a)
            key_b = _rate_limit_key(user_b)

        self.assertIn(user_a, key_a)
        self.assertIn(user_b, key_b)
        self.assertNotEqual(key_a, key_b, "Different users must have different rate limit keys")
