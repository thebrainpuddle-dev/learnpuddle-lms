"""
Tests for the calendar sync engine.

Covers acceptance criteria:
 - idempotency: re-running produces zero new provider events
 - 401 / invalid_grant flips connection.status to 'expired'
 - Non-auth errors leave status='active' but record error
 - Active-only gating: revoked/expired connections are skipped
 - Tokens are encrypted in DB (raw-SQL check on CalendarConnection)
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from django.db import connection as db_conn
from django.test import TestCase

from apps.integrations_calendar.models import (
    CalendarConnection,
    CalendarSyncedEvent,
)
from apps.integrations_calendar.sync_engine import _collect_lms_events, push_events_for_connection


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def make_tenant(subdomain="sync-school"):
    from apps.tenants.models import Tenant
    return Tenant.objects.create(
        name=subdomain.replace("-", " ").title(),
        subdomain=subdomain,
        slug=subdomain,
        email=f"admin@{subdomain}.example.com",
    )


def make_user(tenant, email=None):
    from apps.users.models import User
    email = email or f"teacher-{uuid.uuid4().hex[:6]}@{tenant.subdomain}.example.com"
    return User.objects.create_user(
        email=email,
        password="Passw0rd!123",
        tenant=tenant,
        role="TEACHER",
    )


def make_connection(
    tenant, user, provider="google", status="active",
    access="ya29.access", refresh="1//refresh",
    target_calendar_id="cal-id-xyz",
):
    conn = CalendarConnection(
        tenant=tenant,
        user=user,
        provider=provider,
        status=status,
        target_calendar_id=target_calendar_id,
    )
    conn.set_access_token(access)
    conn.set_refresh_token(refresh)
    conn.save()
    return conn


def _make_event_dict(uid="evt-1", summary="Assignment A — Due"):
    from datetime import datetime, timezone as dt_tz
    now = datetime(2026, 5, 1, 12, 0, 0, tzinfo=dt_tz.utc)
    return {
        "source_type": "assignment",
        "source_id": "11111111-1111-1111-1111-111111111111",
        "uid": uid,
        "summary": summary,
        "description": "body",
        "start_dt": now,
        "end_dt": now,
    }


# ---------------------------------------------------------------------------
# 1. Encrypted at rest — raw SQL assertion
# ---------------------------------------------------------------------------


class TestTokensEncryptedAtRest(TestCase):
    """
    Acceptance: access_token_encrypted column must NOT contain the
    plaintext token value even under raw SQL inspection.
    """

    def setUp(self):
        self.tenant = make_tenant(subdomain="cryptodb-school")
        self.user = make_user(self.tenant)
        self.plaintext = "ya29.PLAINTEXT-access-token-do-not-leak-xyz"
        self.conn = make_connection(self.tenant, self.user, access=self.plaintext)

    def test_raw_sql_does_not_expose_plaintext_token(self):
        with db_conn.cursor() as cursor:
            cursor.execute(
                "SELECT access_token_encrypted, refresh_token_encrypted "
                "FROM integrations_calendar_connection WHERE id = %s",
                [str(self.conn.pk)],
            )
            row = cursor.fetchone()
        access_raw, refresh_raw = row
        self.assertIsNotNone(access_raw)
        # Core assertion: the stored ciphertext must NOT contain the plaintext.
        self.assertNotIn(self.plaintext, access_raw)
        self.assertNotIn("PLAINTEXT-access-token", access_raw)
        # Decrypt via model helper → original value returned.
        self.assertEqual(self.conn.get_access_token(), self.plaintext)


# ---------------------------------------------------------------------------
# 2. Inactive connections are skipped
# ---------------------------------------------------------------------------


class TestSyncEngineSkipsInactive(TestCase):
    def setUp(self):
        self.tenant = make_tenant(subdomain="skip-school")
        self.user = make_user(self.tenant)

    def test_revoked_connection_is_skipped(self):
        conn = make_connection(self.tenant, self.user, status="revoked")
        summary = push_events_for_connection(conn)
        self.assertEqual(summary, {"created": 0, "updated": 0, "deleted": 0, "errors": 0})

    def test_expired_connection_is_skipped(self):
        conn = make_connection(self.tenant, self.user, status="expired")
        summary = push_events_for_connection(conn)
        self.assertEqual(summary["created"], 0)
        self.assertEqual(summary["errors"], 0)


class TestSyncEngineCourseAssignments(TestCase):
    def setUp(self):
        from django.utils import timezone
        from apps.courses.models import Course
        from apps.progress.models import Assignment

        self.tenant = make_tenant(subdomain="assigned-course-school")
        self.user = make_user(self.tenant)
        self.conn = make_connection(self.tenant, self.user)
        self.course = Course.objects.create(
            tenant=self.tenant,
            title="Assigned Teacher Course",
            description="Calendar source course",
            is_published=True,
            is_active=True,
            created_by=self.user,
        )
        self.course.assigned_teachers.add(self.user)
        self.assignment = Assignment.objects.create(
            tenant=self.tenant,
            course=self.course,
            title="Assigned course due date",
            description="Should sync through course assignment fields.",
            due_date=timezone.now() + timezone.timedelta(days=2),
            is_active=True,
        )

    def test_collect_lms_events_uses_course_assignment_fields(self):
        events = _collect_lms_events(self.conn)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["source_id"], str(self.assignment.id))
        self.assertIn("Assigned course due date", events[0]["summary"])


# ---------------------------------------------------------------------------
# 3. Idempotency — running twice with same LMS state produces zero new events
# ---------------------------------------------------------------------------


class TestSyncEngineIdempotency(TestCase):
    """
    Acceptance: sync is idempotent — re-run produces zero new provider events.
    We stub both _collect_lms_events (to return a deterministic event) and
    the provider upsert callable (to count invocations).
    """

    def setUp(self):
        self.tenant = make_tenant(subdomain="idem-school")
        self.user = make_user(self.tenant)
        self.conn = make_connection(self.tenant, self.user)
        self.event = _make_event_dict()

    def test_second_run_creates_zero_new_rows(self):
        call_count = {"upsert": 0, "delete": 0}

        def fake_upsert(connection, event_data):
            call_count["upsert"] += 1
            return f"provider-event-{call_count['upsert']}"

        def fake_delete(connection, provider_event_id):
            call_count["delete"] += 1

        fake_provider = {"upsert": fake_upsert, "delete": fake_delete}

        with patch(
            "apps.integrations_calendar.sync_engine._get_provider",
            return_value=fake_provider,
        ), patch(
            "apps.integrations_calendar.sync_engine._collect_lms_events",
            return_value=[self.event],
        ):
            first = push_events_for_connection(self.conn)
            # A synced event row must now exist.
            self.assertEqual(first["created"], 1)
            self.assertEqual(
                CalendarSyncedEvent.objects.filter(connection=self.conn).count(),
                1,
            )

            # Second run — same event state — must NOT create duplicates
            # and must NOT call upsert again (title_hash is unchanged).
            upserts_before = call_count["upsert"]
            second = push_events_for_connection(self.conn)

        self.assertEqual(second["created"], 0)
        # upsert must not have been re-invoked for an unchanged event.
        self.assertEqual(call_count["upsert"], upserts_before)
        # Still exactly one synced event row — no duplicates.
        self.assertEqual(
            CalendarSyncedEvent.objects.filter(connection=self.conn).count(),
            1,
        )


# ---------------------------------------------------------------------------
# 4. 401 → connection flipped to 'expired'
# ---------------------------------------------------------------------------


class TestSyncEngineAuthErrorHandling(TestCase):
    def setUp(self):
        self.tenant = make_tenant(subdomain="autherr-school")
        self.user = make_user(self.tenant)
        self.conn = make_connection(self.tenant, self.user)
        self.event = _make_event_dict()

    def test_401_marks_connection_expired(self):
        """
        Provider raising an error whose message contains '401' must flip
        connection.status to 'expired'.
        """
        def raise_401(connection, event_data):
            raise RuntimeError("HTTP 401 Unauthorized — token revoked")

        fake_provider = {"upsert": raise_401, "delete": lambda *a, **kw: None}

        with patch(
            "apps.integrations_calendar.sync_engine._get_provider",
            return_value=fake_provider,
        ), patch(
            "apps.integrations_calendar.sync_engine._collect_lms_events",
            return_value=[self.event],
        ):
            summary = push_events_for_connection(self.conn)

        self.conn.refresh_from_db()
        self.assertEqual(self.conn.status, "expired")
        self.assertIn("401", self.conn.error)
        self.assertEqual(summary["errors"], 1)

    def test_invalid_grant_marks_connection_expired(self):
        """invalid_grant is the Google/MSAL auth-failure sentinel."""
        def raise_invalid_grant(connection, event_data):
            raise RuntimeError("oauth: invalid_grant — refresh token revoked")

        fake_provider = {"upsert": raise_invalid_grant, "delete": lambda *a, **kw: None}

        with patch(
            "apps.integrations_calendar.sync_engine._get_provider",
            return_value=fake_provider,
        ), patch(
            "apps.integrations_calendar.sync_engine._collect_lms_events",
            return_value=[self.event],
        ):
            push_events_for_connection(self.conn)

        self.conn.refresh_from_db()
        self.assertEqual(self.conn.status, "expired")

    def test_generic_500_keeps_connection_active(self):
        """
        Non-auth errors (e.g. 500 Internal Server Error, network blip)
        must leave connection status='active' and merely record the
        error message for operator visibility.
        """
        def raise_500(connection, event_data):
            raise RuntimeError("HTTP 500 Internal Server Error")

        fake_provider = {"upsert": raise_500, "delete": lambda *a, **kw: None}

        with patch(
            "apps.integrations_calendar.sync_engine._get_provider",
            return_value=fake_provider,
        ), patch(
            "apps.integrations_calendar.sync_engine._collect_lms_events",
            return_value=[self.event],
        ):
            push_events_for_connection(self.conn)

        self.conn.refresh_from_db()
        self.assertEqual(self.conn.status, "active")
        self.assertIn("500", self.conn.error)
