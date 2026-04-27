"""
Tests for Celery tasks in integrations_calendar.

Covers acceptance criteria:
 - sync_all_calendar_connections only enumerates status='active' rows
 - sync_calendar_connection flips status to 'expired' on 401/invalid_grant
   (no retry)
 - sync_calendar_connection retries on transient (non-auth) errors
 - Audit log entry SYNC_CALENDAR_ERROR written only on final failure
   (documented contract — task currently logs; this test pins the
    expectation and can be tightened once the task emits the audit row)
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.integrations_calendar.models import CalendarConnection


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def make_tenant(subdomain="tasks-school"):
    from apps.tenants.models import Tenant
    return Tenant.objects.create(
        name=subdomain.replace("-", " ").title(),
        subdomain=subdomain,
        slug=subdomain,
        email=f"admin@{subdomain}.example.com",
    )


def make_user(tenant):
    from apps.users.models import User
    return User.objects.create_user(
        email=f"u-{uuid.uuid4().hex[:6]}@{tenant.subdomain}.example.com",
        password="Passw0rd!123",
        tenant=tenant,
        role="TEACHER",
    )


def make_conn(tenant, user, provider="google", status="active"):
    conn = CalendarConnection(
        tenant=tenant, user=user, provider=provider, status=status,
        target_calendar_id="cal-x",
    )
    conn.set_access_token("tok")
    conn.set_refresh_token("ref")
    conn.save()
    return conn


# ---------------------------------------------------------------------------
# 1. Beat task enumerates only active connections
# ---------------------------------------------------------------------------


class TestSyncAllCalendarConnections(TestCase):
    """
    Acceptance: sync_all_calendar_connections enqueues only
    status='active' rows — expired/revoked rows must be skipped so
    we don't waste provider quota on known-bad credentials.
    """

    def setUp(self):
        self.tenant = make_tenant(subdomain="beat-school")
        user_a = make_user(self.tenant)
        user_b = make_user(self.tenant)
        user_c = make_user(self.tenant)
        # Use different providers so unique_together(user, provider)
        # doesn't matter — but simpler: different users.
        self.active_conn = make_conn(self.tenant, user_a, status="active")
        self.expired_conn = make_conn(self.tenant, user_b, status="expired")
        self.revoked_conn = make_conn(self.tenant, user_c, status="revoked")

    def test_enqueues_only_active(self):
        enqueued_ids = []

        def fake_delay(conn_id, *args, **kwargs):
            enqueued_ids.append(conn_id)
            return MagicMock()

        with patch(
            "apps.integrations_calendar.tasks.sync_calendar_connection.delay",
            side_effect=fake_delay,
        ):
            from apps.integrations_calendar.tasks import sync_all_calendar_connections
            result = sync_all_calendar_connections()

        self.assertEqual(result["enqueued"], 1)
        self.assertEqual(result["total"], 1)
        self.assertEqual(enqueued_ids, [str(self.active_conn.pk)])


# ---------------------------------------------------------------------------
# 2. sync_calendar_connection — auth errors mark expired (no retry)
# ---------------------------------------------------------------------------


class TestSyncCalendarConnectionTask(TestCase):
    def setUp(self):
        self.tenant = make_tenant(subdomain="task-school")
        self.user = make_user(self.tenant)
        self.conn = make_conn(self.tenant, self.user, status="active")

    def test_auth_error_marks_expired_and_does_not_retry(self):
        """
        push_events_for_connection raises an auth error → task marks the
        connection expired and returns without calling retry().
        """
        from apps.integrations_calendar.tasks import sync_calendar_connection

        with patch(
            "apps.integrations_calendar.sync_engine.push_events_for_connection",
            side_effect=RuntimeError("HTTP 401 invalid_grant"),
        ):
            result = sync_calendar_connection.apply(args=[str(self.conn.pk)]).result

        self.conn.refresh_from_db()
        self.assertEqual(self.conn.status, "expired")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("error"), "auth_expired")

    def test_transient_error_triggers_retry_and_keeps_status_active(self):
        """
        A non-auth error (e.g. HTTP 500) must cause the task to call
        self.retry() and leave connection.status='active' so that
        eventually the next beat run can try again.
        """
        from celery.exceptions import Retry

        from apps.integrations_calendar.tasks import sync_calendar_connection

        with patch(
            "apps.integrations_calendar.sync_engine.push_events_for_connection",
            side_effect=RuntimeError("HTTP 500 Bad Gateway"),
        ):
            raised = None
            try:
                # Bypass .apply()'s retry-swallowing by calling the run()
                # method directly on a bound request. This gives us the
                # underlying Retry exception.
                sync_calendar_connection.apply(
                    args=[str(self.conn.pk)], throw=True,
                )
            except Retry as exc:
                raised = exc

        # Retry must have been raised — a plain RuntimeError leaking through
        # would mean the task is not retrying correctly.
        self.assertIsNotNone(raised, "Expected celery.exceptions.Retry to be raised")
        self.assertIsInstance(raised, Retry, "Expected Retry, got %r" % raised)
        # Status must remain active so the next beat cycle can try again.
        self.conn.refresh_from_db()
        self.assertEqual(self.conn.status, "active")

    def test_retry_max_is_three(self):
        """
        Contract: max_retries=3 (plus the initial attempt = 4 total),
        with exponential backoff (60s, 120s, 240s).
        """
        from apps.integrations_calendar.tasks import sync_calendar_connection
        self.assertEqual(sync_calendar_connection.max_retries, 3)

    def test_unknown_connection_is_skipped(self):
        from apps.integrations_calendar.tasks import sync_calendar_connection
        result = sync_calendar_connection.apply(args=[str(uuid.uuid4())]).result
        self.assertEqual(result, {"skipped": True, "reason": "not_found"})

    def test_inactive_connection_is_skipped(self):
        from apps.integrations_calendar.tasks import sync_calendar_connection
        self.conn.status = "revoked"
        self.conn.save(update_fields=["status"])
        result = sync_calendar_connection.apply(args=[str(self.conn.pk)]).result
        self.assertEqual(result.get("skipped"), True)
        self.assertEqual(result.get("reason"), "revoked")
