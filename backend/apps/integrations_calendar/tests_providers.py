"""
Provider-level tests for Google and Outlook adapters.

All provider HTTP is stubbed via unittest.mock — NO real provider APIs
are contacted.

Covers acceptance criteria:
 - Outlook upsert hits MS Graph with the right URL + body and returns
   the provider event ID (happy path)
 - Outlook delete calls the expected endpoint
 - Google revoke_tokens posts to the Google revocation endpoint
 - ensure_learnpuddle_calendar reuses an existing calendar instead of
   re-creating it (idempotent behaviour)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone as dt_tz
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.integrations_calendar.models import CalendarConnection


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def make_connection(provider="outlook"):
    from apps.tenants.models import Tenant
    from apps.users.models import User

    subdomain = f"prov-{uuid.uuid4().hex[:6]}"
    tenant = Tenant.objects.create(
        name=subdomain,
        subdomain=subdomain,
        slug=subdomain,
        email=f"admin@{subdomain}.example.com",
    )
    user = User.objects.create_user(
        email=f"u@{subdomain}.example.com",
        password="Passw0rd!1",
        tenant=tenant,
        role="TEACHER",
    )
    conn = CalendarConnection(
        tenant=tenant,
        user=user,
        provider=provider,
        status="active",
        target_calendar_id="cal-xyz-123",
    )
    conn.set_access_token("plaintext-access-token")
    conn.set_refresh_token("plaintext-refresh-token")
    conn.save()
    return conn


def _make_event_dict():
    now = datetime(2026, 6, 1, 9, 0, 0, tzinfo=dt_tz.utc)
    return {
        "source_type": "assignment",
        "source_id": "assn-1",
        "uid": "lp-assignment-assn-1@example.com",
        "summary": "[LearnPuddle] Quiz 1 — Due",
        "description": "Quiz 1 for Course Foo",
        "start_dt": now,
        "end_dt": now,
    }


# ---------------------------------------------------------------------------
# 1. Outlook upsert — creates new event on MS Graph
# ---------------------------------------------------------------------------


class TestOutlookUpsertCreate(TestCase):
    def setUp(self):
        self.conn = make_connection(provider="outlook")
        self.event = _make_event_dict()

    @patch("apps.integrations_calendar.providers.outlook.requests")
    def test_upsert_creates_event_when_not_found(self, mock_requests):
        # Lookup returns no existing events.
        lookup_resp = MagicMock(status_code=200)
        lookup_resp.json.return_value = {"value": []}
        lookup_resp.raise_for_status = MagicMock()
        # Create returns the new event ID.
        create_resp = MagicMock(status_code=201)
        create_resp.json.return_value = {"id": "AAMkAD-event-id-new"}
        create_resp.raise_for_status = MagicMock()

        mock_requests.get.return_value = lookup_resp
        mock_requests.post.return_value = create_resp

        from apps.integrations_calendar.providers.outlook import upsert_event
        event_id = upsert_event(self.conn, self.event)

        self.assertEqual(event_id, "AAMkAD-event-id-new")
        # Must have called POST on the calendar-events endpoint.
        called_url = mock_requests.post.call_args.args[0]
        self.assertIn("/me/calendars/", called_url)
        self.assertIn("/events", called_url)
        # Body must carry the event summary.
        body = mock_requests.post.call_args.kwargs.get("json", {})
        self.assertEqual(body["subject"], self.event["summary"])

    @patch("apps.integrations_calendar.providers.outlook.requests")
    def test_upsert_patches_event_when_found(self, mock_requests):
        # Lookup finds an existing event — upsert must PATCH, not POST.
        lookup_resp = MagicMock(status_code=200)
        lookup_resp.json.return_value = {"value": [{"id": "existing-ms-id"}]}
        lookup_resp.raise_for_status = MagicMock()
        patch_resp = MagicMock(status_code=200)
        patch_resp.raise_for_status = MagicMock()

        mock_requests.get.return_value = lookup_resp
        mock_requests.patch.return_value = patch_resp

        from apps.integrations_calendar.providers.outlook import upsert_event
        event_id = upsert_event(self.conn, self.event)

        self.assertEqual(event_id, "existing-ms-id")
        self.assertTrue(mock_requests.patch.called)
        self.assertFalse(mock_requests.post.called, "Should PATCH, not POST")

    @patch("apps.integrations_calendar.providers.outlook.requests")
    def test_delete_event_hits_delete_endpoint(self, mock_requests):
        delete_resp = MagicMock(status_code=204)
        delete_resp.raise_for_status = MagicMock()
        mock_requests.delete.return_value = delete_resp

        from apps.integrations_calendar.providers.outlook import delete_event
        delete_event(self.conn, "event-id-to-delete")

        self.assertTrue(mock_requests.delete.called)
        called_url = mock_requests.delete.call_args.args[0]
        self.assertIn("event-id-to-delete", called_url)


# ---------------------------------------------------------------------------
# 2. Outlook ensure_learnpuddle_calendar — idempotent (reuse existing)
# ---------------------------------------------------------------------------


class TestOutlookEnsureCalendar(TestCase):
    def setUp(self):
        self.conn = make_connection(provider="outlook")

    @patch("apps.integrations_calendar.providers.outlook.requests")
    def test_reuses_existing_learnpuddle_calendar(self, mock_requests):
        """
        If a calendar named 'LearnPuddle' already exists, return its ID
        rather than creating a second one.
        """
        list_resp = MagicMock(status_code=200)
        list_resp.json.return_value = {
            "value": [
                {"id": "other-cal", "name": "Personal"},
                {"id": "lp-existing-cal-id", "name": "LearnPuddle"},
            ]
        }
        list_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = list_resp

        from apps.integrations_calendar.providers.outlook import (
            ensure_learnpuddle_calendar,
        )
        cal_id = ensure_learnpuddle_calendar(self.conn)
        self.assertEqual(cal_id, "lp-existing-cal-id")
        # Must NOT have called POST (no new calendar created).
        self.assertFalse(mock_requests.post.called)

    @patch("apps.integrations_calendar.providers.outlook.requests")
    def test_creates_learnpuddle_calendar_when_absent(self, mock_requests):
        list_resp = MagicMock(status_code=200)
        list_resp.json.return_value = {"value": [{"id": "other", "name": "Personal"}]}
        list_resp.raise_for_status = MagicMock()

        create_resp = MagicMock(status_code=201)
        create_resp.json.return_value = {"id": "brand-new-lp-cal"}
        create_resp.raise_for_status = MagicMock()

        mock_requests.get.return_value = list_resp
        mock_requests.post.return_value = create_resp

        from apps.integrations_calendar.providers.outlook import (
            ensure_learnpuddle_calendar,
        )
        cal_id = ensure_learnpuddle_calendar(self.conn)
        self.assertEqual(cal_id, "brand-new-lp-cal")
        self.assertTrue(mock_requests.post.called)
        # Body must mark isDefaultCalendar=False (scope minimisation).
        body = mock_requests.post.call_args.kwargs.get("json", {})
        self.assertEqual(body.get("name"), "LearnPuddle")
        self.assertFalse(body.get("isDefaultCalendar"))


# ---------------------------------------------------------------------------
# 3. Google revoke_tokens hits the Google revocation endpoint
# ---------------------------------------------------------------------------


class TestGoogleRevokeTokens(TestCase):
    def setUp(self):
        self.conn = make_connection(provider="google")

    def test_revoke_tokens_calls_google_endpoint(self):
        """Google provider must POST to the OAuth revoke URL."""
        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            from apps.integrations_calendar.providers import google as gprov
            gprov.revoke_tokens(self.conn)

        self.assertTrue(mock_post.called)
        called_url = mock_post.call_args.args[0]
        self.assertIn("oauth2.googleapis.com/revoke", called_url)
        # Token param must contain the (decrypted) access token.
        params = mock_post.call_args.kwargs.get("params", {})
        self.assertEqual(params.get("token"), "plaintext-access-token")

    def test_revoke_tokens_handles_provider_failure(self):
        """Provider errors must be swallowed — revocation is best-effort."""
        with patch("requests.post", side_effect=Exception("network down")):
            from apps.integrations_calendar.providers import google as gprov
            # Must not raise.
            gprov.revoke_tokens(self.conn)


# ---------------------------------------------------------------------------
# 4. Outlook revoke_tokens is a no-op (MS does not expose revoke URL)
# ---------------------------------------------------------------------------


class TestOutlookRevokeTokens(TestCase):
    def setUp(self):
        self.conn = make_connection(provider="outlook")

    def test_revoke_tokens_is_noop_for_outlook(self):
        """
        MS Graph doesn't expose a synchronous token revocation endpoint,
        so outlook.revoke_tokens is a no-op (documented). The disconnect
        view still clears local ciphertext + flips status.
        """
        from apps.integrations_calendar.providers import outlook as oprov
        # Must not raise, must not make any HTTP calls.
        with patch("apps.integrations_calendar.providers.outlook.requests") as mock_req:
            oprov.revoke_tokens(self.conn)
            self.assertFalse(mock_req.get.called)
            self.assertFalse(mock_req.post.called)
            self.assertFalse(mock_req.delete.called)
