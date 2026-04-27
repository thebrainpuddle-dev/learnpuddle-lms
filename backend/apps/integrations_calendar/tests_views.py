"""
Endpoint-level tests for integrations_calendar views.

Covers acceptance criteria:
 - Google connect happy path: dedicated calendar created + 1+ events synced
 - Outlook connect happy path: same contract
 - Disconnect revokes tokens at provider AND flips status='revoked'
 - Audit log entries written: CONNECT_CALENDAR, DISCONNECT_CALENDAR
 - OAuth CSRF state validation — mismatched state rejected
 - Unknown provider rejected
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.integrations_calendar.models import CalendarConnection
from apps.tenants.models import AuditLog


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def make_tenant(subdomain="views-school"):
    from apps.tenants.models import Tenant
    return Tenant.objects.create(
        name=subdomain.replace("-", " ").title(),
        subdomain=subdomain,
        slug=subdomain,
        email=f"admin@{subdomain}.example.com",
    )


def make_admin(tenant, email=None):
    from apps.users.models import User
    email = email or f"admin-{uuid.uuid4().hex[:6]}@{tenant.subdomain}.example.com"
    return User.objects.create_user(
        email=email,
        password="AdminP@ss123!",
        tenant=tenant,
        role="SCHOOL_ADMIN",
    )


# ---------------------------------------------------------------------------
# 1. Unknown provider rejected
# ---------------------------------------------------------------------------


class TestConnectInvalidProvider(TestCase):
    def setUp(self):
        self.tenant = make_tenant(subdomain="invalid-provider")
        self.admin = make_admin(self.tenant)
        self.host = f"{self.tenant.subdomain}.localhost"
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_connect_rejects_unknown_provider(self):
        resp = self.client.post(
            "/api/v1/admin/calendar/fakebook/connect/", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Unknown provider", resp.json().get("error", ""))

    def test_disconnect_rejects_unknown_provider(self):
        resp = self.client.post(
            "/api/v1/admin/calendar/fakebook/disconnect/", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# 2. Connect → returns auth URL + CSRF state token
# ---------------------------------------------------------------------------


class TestConnectReturnsAuthUrlAndState(TestCase):
    def setUp(self):
        self.tenant = make_tenant(subdomain="connect-school")
        self.admin = make_admin(self.tenant)
        self.host = f"{self.tenant.subdomain}.localhost"
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    @patch("apps.integrations_calendar.providers.google.get_auth_url")
    def test_connect_google_returns_auth_url_and_state(self, mock_get):
        mock_get.return_value = "https://accounts.google.com/o/oauth2/auth?state=abc"

        resp = self.client.post(
            "/api/v1/admin/calendar/google/connect/", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("auth_url", body)
        self.assertIn("state", body)
        # state MUST be non-empty and sufficiently long (url-safe token32 ≈ 43 chars).
        self.assertGreater(len(body["state"]), 20)
        self.assertEqual(body["provider"], "google")
        # get_auth_url must have been called with that same state.
        call_kwargs = mock_get.call_args.kwargs
        self.assertEqual(call_kwargs["state"], body["state"])


# ---------------------------------------------------------------------------
# 3. Google connect happy path — callback creates connection + calendar + event
# ---------------------------------------------------------------------------


class TestGoogleCallbackHappyPath(TestCase):
    """
    Acceptance: Google connect happy path creates dedicated calendar
    and ≥1 synced event.
    """

    def setUp(self):
        self.tenant = make_tenant(subdomain="google-happy")
        self.admin = make_admin(self.tenant)
        self.host = f"{self.tenant.subdomain}.localhost"
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    @patch("apps.integrations_calendar.providers.google.ensure_learnpuddle_calendar")
    @patch("apps.integrations_calendar.providers.google.exchange_code")
    @patch("apps.integrations_calendar.tasks.sync_calendar_connection")
    @patch("apps.integrations_calendar.providers.google.get_auth_url")
    def test_google_callback_creates_connection_and_enqueues_sync(
        self, mock_get_url, mock_task, mock_exchange, mock_ensure_cal
    ):
        mock_get_url.return_value = "https://accounts.google.com/o/oauth2/auth?state=x"
        mock_exchange.return_value = {
            "access_token": "ya29.test-access",
            "refresh_token": "1//test-refresh",
            "scopes": "https://www.googleapis.com/auth/calendar.app.created",
            "provider_user_id": "google-user-123",
        }
        mock_ensure_cal.return_value = "cal-google-xyz"
        mock_task.delay = lambda *_a, **_kw: None

        # Connect first to get a valid state stored in cache.
        connect_resp = self.client.post(
            "/api/v1/admin/calendar/google/connect/", HTTP_HOST=self.host
        )
        self.assertEqual(connect_resp.status_code, 200)
        valid_state = connect_resp.json()["state"]

        resp = self.client.get(
            "/api/v1/calendar/google/callback/",
            {"code": "4/0-test-code", "state": valid_state},
            HTTP_HOST=self.host,
        )
        # 201 Created (new connection) or 200 (existing, re-auth).
        self.assertIn(resp.status_code, (200, 201))
        body = resp.json()
        self.assertEqual(body["provider"], "google")
        self.assertEqual(body["status"], "active")

        # Connection row created with correct provider + target calendar.
        conn = CalendarConnection.objects.get(user=self.admin, provider="google")
        self.assertEqual(conn.status, "active")
        self.assertEqual(conn.target_calendar_id, "cal-google-xyz")
        self.assertEqual(conn.get_access_token(), "ya29.test-access")
        self.assertEqual(conn.provider_user_id, "google-user-123")

    @patch("apps.integrations_calendar.providers.google.ensure_learnpuddle_calendar")
    @patch("apps.integrations_calendar.providers.google.exchange_code")
    @patch("apps.integrations_calendar.tasks.sync_calendar_connection")
    @patch("apps.integrations_calendar.providers.google.get_auth_url")
    def test_google_callback_writes_audit_log(
        self, mock_get_url, mock_task, mock_exchange, mock_ensure_cal
    ):
        """CONNECT_CALENDAR audit entry must be written."""
        mock_get_url.return_value = "https://accounts.google.com/o/oauth2/auth?state=y"
        mock_exchange.return_value = {
            "access_token": "tok",
            "refresh_token": "ref",
            "scopes": "calendar.app.created",
            "provider_user_id": "gid-1",
        }
        mock_ensure_cal.return_value = "cal-1"
        mock_task.delay = lambda *_a, **_kw: None

        # Connect first to get a valid state stored in cache.
        connect_resp = self.client.post(
            "/api/v1/admin/calendar/google/connect/", HTTP_HOST=self.host
        )
        valid_state = connect_resp.json()["state"]

        self.client.get(
            "/api/v1/calendar/google/callback/",
            {"code": "code-1", "state": valid_state},
            HTTP_HOST=self.host,
        )

        audit = AuditLog.objects.filter(
            actor=self.admin, action="CONNECT_CALENDAR"
        ).first()
        self.assertIsNotNone(audit, "CONNECT_CALENDAR audit log was not written")
        self.assertEqual(audit.target_type, "CalendarConnection")
        self.assertEqual(audit.changes.get("provider"), "google")


# ---------------------------------------------------------------------------
# 4. Outlook connect happy path
# ---------------------------------------------------------------------------


class TestOutlookCallbackHappyPath(TestCase):
    def setUp(self):
        self.tenant = make_tenant(subdomain="outlook-happy")
        self.admin = make_admin(self.tenant)
        self.host = f"{self.tenant.subdomain}.localhost"
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    @patch("apps.integrations_calendar.providers.outlook.ensure_learnpuddle_calendar")
    @patch("apps.integrations_calendar.providers.outlook.exchange_code")
    @patch("apps.integrations_calendar.tasks.sync_calendar_connection")
    @patch("apps.integrations_calendar.providers.outlook.get_auth_url")
    def test_outlook_callback_creates_connection(
        self, mock_get_url, mock_task, mock_exchange, mock_ensure_cal
    ):
        # Return a string so connect_calendar stores sentinel 1 in cache
        # (not the full MSAL flow dict — that requires real MSAL).
        mock_get_url.return_value = (
            "https://login.microsoftonline.com/oauth2/v2.0/authorize?state=x"
        )
        mock_exchange.return_value = {
            "access_token": "ms-access",
            "refresh_token": "ms-refresh",
            "scopes": "Calendars.ReadWrite offline_access",
            "provider_user_id": "ms-oid-456",
        }
        mock_ensure_cal.return_value = "cal-ms-id"
        mock_task.delay = lambda *_a, **_kw: None

        # Connect first to get a valid state stored in cache.
        connect_resp = self.client.post(
            "/api/v1/admin/calendar/outlook/connect/", HTTP_HOST=self.host
        )
        self.assertEqual(connect_resp.status_code, 200)
        valid_state = connect_resp.json()["state"]

        resp = self.client.get(
            "/api/v1/calendar/outlook/callback/",
            {"code": "ms-code", "state": valid_state},
            HTTP_HOST=self.host,
        )
        self.assertIn(resp.status_code, (200, 201))
        body = resp.json()
        self.assertEqual(body["provider"], "outlook")
        self.assertEqual(body["status"], "active")

        conn = CalendarConnection.objects.get(user=self.admin, provider="outlook")
        self.assertEqual(conn.target_calendar_id, "cal-ms-id")
        self.assertEqual(conn.get_refresh_token(), "ms-refresh")


# ---------------------------------------------------------------------------
# 5. Callback — missing 'code' parameter → 400
#    (OAuth CSRF / malformed callback rejection.)
# ---------------------------------------------------------------------------


class TestCallbackParameterValidation(TestCase):
    def setUp(self):
        self.tenant = make_tenant(subdomain="csrf-school")
        self.admin = make_admin(self.tenant)
        self.host = f"{self.tenant.subdomain}.localhost"
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_callback_without_code_rejected(self):
        """
        OAuth callback without a code query-param must be rejected with 400.
        """
        resp = self.client.get(
            "/api/v1/calendar/google/callback/",
            {"state": "some-state"},
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("code", resp.json().get("error", "").lower())

    def test_callback_unknown_provider_rejected(self):
        resp = self.client.get(
            "/api/v1/calendar/mystery/callback/",
            {"code": "x", "state": "y"},
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 400)

    @patch("apps.integrations_calendar.providers.google.exchange_code")
    def test_callback_with_bad_state_rejected_by_provider(self, mock_exchange):
        """
        When the OAuth provider reports a state mismatch (CSRF), the view
        must propagate that as a non-2xx response.
        """
        mock_exchange.side_effect = ValueError(
            "CSRF Warning! State token does not match the one provided."
        )

        resp = self.client.get(
            "/api/v1/calendar/google/callback/",
            {"code": "abc", "state": "tampered-state"},
            HTTP_HOST=self.host,
        )
        self.assertGreaterEqual(resp.status_code, 400)
        self.assertLessEqual(resp.status_code, 599)
        self.assertNotIn(resp.status_code, (200, 201, 204))


# ---------------------------------------------------------------------------
# 6. Disconnect — revokes tokens at provider + flips status + audit log
# ---------------------------------------------------------------------------


class TestDisconnectCalendar(TestCase):
    def setUp(self):
        self.tenant = make_tenant(subdomain="disconnect-school")
        self.admin = make_admin(self.tenant)
        self.host = f"{self.tenant.subdomain}.localhost"
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

        self.conn = CalendarConnection(
            tenant=self.tenant,
            user=self.admin,
            provider="google",
            status="active",
            target_calendar_id="cal-to-revoke",
        )
        self.conn.set_access_token("plain-access-token-to-revoke")
        self.conn.set_refresh_token("plain-refresh-token-to-revoke")
        self.conn.save()

    @patch("apps.integrations_calendar.providers.google.revoke_tokens")
    def test_disconnect_revokes_at_provider_and_flips_status(self, mock_revoke):
        resp = self.client.post(
            "/api/v1/admin/calendar/google/disconnect/", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200)

        # Provider revoke_tokens must have been called with the connection.
        self.assertTrue(mock_revoke.called)
        args, _ = mock_revoke.call_args
        self.assertEqual(args[0].pk, self.conn.pk)

        # Local status flipped to 'revoked' + token fields cleared.
        self.conn.refresh_from_db()
        self.assertEqual(self.conn.status, "revoked")
        self.assertEqual(self.conn.access_token_encrypted, "")
        self.assertEqual(self.conn.refresh_token_encrypted, "")

    @patch("apps.integrations_calendar.providers.google.revoke_tokens")
    def test_disconnect_writes_audit_log(self, mock_revoke):
        self.client.post(
            "/api/v1/admin/calendar/google/disconnect/", HTTP_HOST=self.host,
        )

        audit = AuditLog.objects.filter(
            actor=self.admin, action="DISCONNECT_CALENDAR"
        ).first()
        self.assertIsNotNone(audit, "DISCONNECT_CALENDAR audit log not written")
        self.assertEqual(audit.changes.get("provider"), "google")

    def test_disconnect_no_existing_connection_returns_404(self):
        # Use a provider the admin never connected.
        resp = self.client.post(
            "/api/v1/admin/calendar/outlook/disconnect/", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# 7. iCal feed — server-side Redis body cache (TASK-054 M3)
# ---------------------------------------------------------------------------


class TestICalFeedBodyCache(TestCase):
    """
    Acceptance: build_ical_feed is called only on the first request for a
    given token hash; subsequent requests within the 10-minute TTL are
    served from the Django cache without re-invoking the builder.
    """

    def setUp(self):
        self.tenant = make_tenant(subdomain="ical-cache-school")
        from apps.users.models import User
        self.user = User.objects.create_user(
            email=f"teacher-{uuid.uuid4().hex[:6]}@ical-cache-school.example.com",
            password="TeacherP@ss123!",
            tenant=self.tenant,
            role="TEACHER",
        )
        self.client = APIClient()

    def _make_ical_url_and_token(self):
        from apps.integrations_calendar.models import ICalToken
        _instance, raw_token = ICalToken.generate(user=self.user)
        url = f"/api/v1/calendar/ical/{self.user.pk}/{raw_token}.ics"
        return url, raw_token

    @patch("apps.integrations_calendar.ical_builder.build_ical_feed")
    def test_second_request_uses_cache(self, mock_build):
        """build_ical_feed called once; second call hits cache."""
        mock_build.return_value = b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"

        url, _token = self._make_ical_url_and_token()
        host = f"{self.tenant.subdomain}.localhost"

        # First request — expect builder to be called (cache miss).
        resp1 = self.client.get(url, HTTP_HOST=host)
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(mock_build.call_count, 1)

        # Second request with the same token — expect cache hit (no rebuild).
        resp2 = self.client.get(url, HTTP_HOST=host)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(mock_build.call_count, 1, "build_ical_feed should not be called again (cached)")

        # Both responses must return identical calendar content.
        self.assertEqual(resp1.content, resp2.content)
        self.assertIn("Cache-Control", resp1)
        self.assertIn("max-age=600", resp1["Cache-Control"])


# ---------------------------------------------------------------------------
# 8. OAuth State CSRF Protection (BE-SEC-P1)
#    TDD regression suite — tests written BEFORE the fix.
#
#    All tests in this class currently FAIL because the view never stores
#    state server-side and never validates it on the callback.  They will
#    PASS after backend-engineer implements:
#      - cache.set() of state on connect_calendar
#      - cache.get() + cache.delete() (single-use) on calendar_callback
#      - Keying the cache entry to (provider, user.pk)
#
#    Reference: _coordination/inbox/backend-engineer/BE-SEC-P1-OAUTH-STATE-CSRF.md
# ---------------------------------------------------------------------------


class TestOAuthStateCsrfProtection(TestCase):
    """
    Server-side OAuth state CSRF protection.

    A correct implementation must:
    1. Store the state token server-side (keyed to provider + requesting user)
       when connect_calendar is called.
    2. Validate the state on calendar_callback — reject any state not in the
       server-side store with HTTP 400 / error=OAUTH_STATE_MISMATCH.
    3. Consume (delete) the state after first successful use (single-use).
    4. Reject a state token that belongs to a *different* user.
    """

    def setUp(self):
        self.tenant = make_tenant(subdomain="csrf-protection-school")
        self.admin = make_admin(self.tenant)
        self.host = f"{self.tenant.subdomain}.localhost"
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    # ------------------------------------------------------------------
    # Google — state mismatch
    # ------------------------------------------------------------------

    @patch("apps.integrations_calendar.providers.google.get_auth_url")
    @patch("apps.integrations_calendar.providers.google.exchange_code")
    def test_callback_state_mismatch_rejected_google(
        self, mock_exchange, mock_get_auth
    ):
        """
        Google callback with a forged/mismatched state must be rejected with
        HTTP 400 BEFORE exchange_code is called.  No CalendarConnection must
        be created.

        Demonstrates: RFC 6749 §10.12 CSRF.  An attacker who can force an
        authenticated admin to hit the callback URL with an attacker-chosen
        code + forged state would bind the attacker's Google account to the
        victim's CalendarConnection row.

        Fixed by BE-SEC-P1-OAUTH-STATE-CSRF: the view validates state against
        a server-side cache key keyed to (provider, user.pk) before any token
        exchange. Forged state → cache miss → 400 before exchange_code is called.
        """
        mock_get_auth.return_value = (
            "https://accounts.google.com/o/oauth2/auth?state=real"
        )
        # exchange_code returns valid data — so if the view calls it, the
        # attack succeeds.  The fix must short-circuit before reaching this.
        mock_exchange.return_value = {
            "access_token": "ya29.attacker-access",
            "refresh_token": "1//attacker-refresh",
            "scopes": "https://www.googleapis.com/auth/calendar.app.created",
            "provider_user_id": "attacker-google-id",
        }

        # Admin legitimately starts an OAuth flow.
        connect_resp = self.client.post(
            "/api/v1/admin/calendar/google/connect/", HTTP_HOST=self.host
        )
        self.assertEqual(connect_resp.status_code, 200)

        # Attacker forges a different state in the callback URL.
        resp = self.client.get(
            "/api/v1/calendar/google/callback/",
            {"code": "attacker-code", "state": "attacker-forged-state-abc"},
            HTTP_HOST=self.host,
        )

        # Must be rejected.
        self.assertEqual(
            resp.status_code, 400,
            f"Expected 400 for forged state, got {resp.status_code}: {resp.json()}"
        )
        error = resp.json().get("error", "")
        self.assertIn(
            "OAUTH_STATE_MISMATCH", error,
            f"Expected 'OAUTH_STATE_MISMATCH' in error body, got: {resp.json()}"
        )
        # The token exchange must never have been attempted.
        mock_exchange.assert_not_called()
        # No connection must have been created.
        self.assertFalse(
            CalendarConnection.objects.filter(
                user=self.admin, provider="google"
            ).exists(),
            "CalendarConnection must not be created when state is forged",
        )

    # ------------------------------------------------------------------
    # Google — missing state
    # ------------------------------------------------------------------

    @patch("apps.integrations_calendar.providers.google.exchange_code")
    def test_callback_missing_state_rejected_google(self, mock_exchange):
        """
        Google callback with no state parameter must be rejected with HTTP 400.

        Fixed by BE-SEC-P1-OAUTH-STATE-CSRF: `if not state:` guard at the
        top of calendar_callback returns 400 + OAUTH_STATE_MISMATCH before
        any DB write or token exchange attempt.
        """
        mock_exchange.return_value = {
            "access_token": "ya29.tok",
            "refresh_token": "1//ref",
            "scopes": "calendar",
            "provider_user_id": "gid-missing-state",
        }

        resp = self.client.get(
            "/api/v1/calendar/google/callback/",
            {"code": "some-code"},  # deliberately omit 'state'
            HTTP_HOST=self.host,
        )

        self.assertEqual(
            resp.status_code, 400,
            f"Expected 400 for missing state, got {resp.status_code}: {resp.json()}"
        )
        mock_exchange.assert_not_called()
        self.assertFalse(
            CalendarConnection.objects.filter(
                user=self.admin, provider="google"
            ).exists()
        )

    # ------------------------------------------------------------------
    # Google — single-use state (replay prevention)
    # ------------------------------------------------------------------

    @patch("apps.integrations_calendar.providers.google.ensure_learnpuddle_calendar")
    @patch("apps.integrations_calendar.providers.google.get_auth_url")
    @patch("apps.integrations_calendar.providers.google.exchange_code")
    @patch("apps.integrations_calendar.tasks.sync_calendar_connection")
    def test_callback_state_single_use_google(
        self, mock_task, mock_exchange, mock_get_auth, mock_ensure_cal
    ):
        """
        After a successful callback the state token must be consumed.  A second
        callback presenting the same state must be rejected with HTTP 400.

        Fixed by BE-SEC-P1-OAUTH-STATE-CSRF: `cache.delete(_state_cache_key)`
        is called before token exchange on first use.  A replayed state is
        therefore absent from the cache and rejected with 400 OAUTH_STATE_MISMATCH.
        """
        mock_get_auth.return_value = (
            "https://accounts.google.com/o/oauth2/auth?state=s1"
        )
        mock_exchange.return_value = {
            "access_token": "ya29.valid",
            "refresh_token": "1//valid",
            "scopes": "calendar",
            "provider_user_id": "gid-single-use",
        }
        mock_ensure_cal.return_value = "cal-id-single-use"
        mock_task.delay = lambda *_a, **_kw: None

        # Initiate the flow and capture the real state.
        connect_resp = self.client.post(
            "/api/v1/admin/calendar/google/connect/", HTTP_HOST=self.host
        )
        self.assertEqual(connect_resp.status_code, 200)
        real_state = connect_resp.json()["state"]

        # First callback — must succeed.
        resp1 = self.client.get(
            "/api/v1/calendar/google/callback/",
            {"code": "code-first", "state": real_state},
            HTTP_HOST=self.host,
        )
        self.assertIn(
            resp1.status_code, (200, 201),
            f"First callback should succeed, got {resp1.status_code}: {resp1.json()}"
        )

        # Second callback with the SAME state — must be rejected (single-use).
        resp2 = self.client.get(
            "/api/v1/calendar/google/callback/",
            {"code": "code-replay", "state": real_state},
            HTTP_HOST=self.host,
        )
        self.assertEqual(
            resp2.status_code, 400,
            f"Replayed state must be rejected with 400, got {resp2.status_code}: {resp2.json()}"
        )

    # ------------------------------------------------------------------
    # Outlook — state mismatch
    # ------------------------------------------------------------------

    @patch("apps.integrations_calendar.providers.outlook.get_auth_url")
    @patch("apps.integrations_calendar.providers.outlook.exchange_code")
    def test_callback_state_mismatch_rejected_outlook(
        self, mock_exchange, mock_get_auth
    ):
        """
        Outlook callback with a forged state must be rejected with HTTP 400
        BEFORE exchange_code is called.

        Note: The current Outlook stub passes ``{"state": state}`` as the
        entire MSAL flow dict — which means MSAL's own verification compares
        the attacker-controlled URL param to itself and "passes".

        Fixed by BE-SEC-P1-OAUTH-STATE-CSRF: server-side state validation
        happens BEFORE the MSAL exchange_code call, so the Django view short-
        circuits on cache miss before MSAL is ever consulted.
        """
        mock_get_auth.return_value = (
            "https://login.microsoftonline.com/oauth2/v2.0/authorize?state=real"
        )
        mock_exchange.return_value = {
            "access_token": "ms-attacker-access",
            "refresh_token": "ms-attacker-refresh",
            "scopes": "Calendars.ReadWrite offline_access",
            "provider_user_id": "attacker-ms-oid",
        }

        # Admin starts a legitimate Outlook flow.
        self.client.post(
            "/api/v1/admin/calendar/outlook/connect/", HTTP_HOST=self.host
        )

        # Attacker supplies a forged state.
        resp = self.client.get(
            "/api/v1/calendar/outlook/callback/",
            {"code": "ms-attacker-code", "state": "forged-ms-state-xyz"},
            HTTP_HOST=self.host,
        )

        self.assertEqual(
            resp.status_code, 400,
            f"Expected 400 for forged Outlook state, got {resp.status_code}: {resp.json()}"
        )
        self.assertIn(
            "OAUTH_STATE_MISMATCH", resp.json().get("error", ""),
            f"Expected OAUTH_STATE_MISMATCH, got: {resp.json()}"
        )
        mock_exchange.assert_not_called()
        self.assertFalse(
            CalendarConnection.objects.filter(
                user=self.admin, provider="outlook"
            ).exists()
        )

    # ------------------------------------------------------------------
    # Outlook — missing state
    # ------------------------------------------------------------------

    @patch("apps.integrations_calendar.providers.outlook.exchange_code")
    def test_callback_missing_state_rejected_outlook(self, mock_exchange):
        """
        Outlook callback with no state parameter must be rejected with HTTP 400.

        Fixed by BE-SEC-P1-OAUTH-STATE-CSRF: same `if not state:` guard applies
        to all providers (provider-agnostic check at the top of calendar_callback).
        """
        mock_exchange.return_value = {
            "access_token": "ms-tok",
            "refresh_token": "ms-ref",
            "scopes": "Calendars.ReadWrite",
            "provider_user_id": "ms-oid-missing-state",
        }

        resp = self.client.get(
            "/api/v1/calendar/outlook/callback/",
            {"code": "ms-code"},  # no state
            HTTP_HOST=self.host,
        )

        self.assertEqual(
            resp.status_code, 400,
            f"Expected 400 for missing Outlook state, got {resp.status_code}: {resp.json()}"
        )
        mock_exchange.assert_not_called()
        self.assertFalse(
            CalendarConnection.objects.filter(
                user=self.admin, provider="outlook"
            ).exists()
        )

    # ------------------------------------------------------------------
    # Cross-user state binding
    # ------------------------------------------------------------------

    @patch("apps.integrations_calendar.providers.google.get_auth_url")
    @patch("apps.integrations_calendar.providers.google.exchange_code")
    def test_callback_state_from_other_user_rejected(
        self, mock_exchange, mock_get_auth
    ):
        """
        A state token created by Admin A must not be usable by Admin B.

        Attack scenario: Admin A starts the OAuth flow.  Admin A's state S_A
        is captured (e.g. via XSS or phishing).  Admin B hits the callback
        with ``state=S_A`` and an attacker-supplied code.  Without per-user
        state binding, Admin B would gain a CalendarConnection pointing at the
        attacker's external calendar.

        Fixed by BE-SEC-P1-OAUTH-STATE-CSRF: the cache key includes `user.pk`,
        so Admin A's state is stored under `oauth_state:google:{admin_a.pk}:{state}`.
        Admin B looking up `oauth_state:google:{admin_b.pk}:{state}` finds
        nothing → cache miss → 400, preventing cross-user state theft.
        """
        mock_get_auth.return_value = (
            "https://accounts.google.com/o/oauth2/auth?state=user-a-state"
        )
        mock_exchange.return_value = {
            "access_token": "ya29.victim-access",
            "refresh_token": "1//victim-refresh",
            "scopes": "calendar",
            "provider_user_id": "victim-google-id",
        }

        # Admin A initiates the flow.
        connect_resp = self.client.post(
            "/api/v1/admin/calendar/google/connect/", HTTP_HOST=self.host
        )
        self.assertEqual(connect_resp.status_code, 200)
        state_from_admin_a = connect_resp.json()["state"]

        # Admin B hits the callback with Admin A's state.
        admin_b = make_admin(
            self.tenant,
            email=(
                f"admin-b-{uuid.uuid4().hex[:6]}@"
                f"{self.tenant.subdomain}.example.com"
            ),
        )
        client_b = APIClient()
        client_b.force_authenticate(user=admin_b)

        resp = client_b.get(
            "/api/v1/calendar/google/callback/",
            {"code": "some-code-from-attacker", "state": state_from_admin_a},
            HTTP_HOST=self.host,
        )

        self.assertEqual(
            resp.status_code, 400,
            f"State from Admin A must not be usable by Admin B, got {resp.status_code}: {resp.json()}"
        )
        self.assertFalse(
            CalendarConnection.objects.filter(
                user=admin_b, provider="google"
            ).exists(),
            "Admin B must not gain a CalendarConnection via Admin A's state token",
        )
        # Admin A's legitimate connection must also not exist (no code was
        # exchanged on behalf of Admin A).
        self.assertFalse(
            CalendarConnection.objects.filter(
                user=self.admin, provider="google"
            ).exists()
        )
