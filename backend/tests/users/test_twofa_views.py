# tests/users/test_twofa_views.py
"""
Tests for apps/users/twofa_views.py — 2FA/MFA endpoints.

Endpoints under test (prefix: /api/v1/users/):
  GET  auth/2fa/status/        — twofa_status
  POST auth/2fa/setup/         — twofa_setup_start
  POST auth/2fa/confirm/       — twofa_setup_confirm
  POST auth/2fa/disable/       — twofa_disable
  POST auth/2fa/backup-codes/  — twofa_regenerate_backup_codes
  POST auth/2fa/verify/        — twofa_verify (public, challenge-token flow)

Coverage strategy:
- Authentication requirements (401 for all protected endpoints)
- 2FA status when disabled vs enabled
- Setup flow: start → confirm with valid/invalid code
- Backup code generation
- Disable flow: requires password + TOTP code (or backup code)
- verify flow: challenge token + TOTP code → JWT tokens
- Tenant-required check (disable blocked when tenant requires 2FA)
"""

import uuid

import pytest
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from unittest.mock import patch, MagicMock

from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant(name, subdomain, require_2fa=False):
    return Tenant.objects.create(
        name=name, slug=subdomain, subdomain=subdomain,
        email=f"admin@{subdomain}.example.com", is_active=True,
        require_2fa=require_2fa,
    )


def _make_user(email, tenant, role="TEACHER", password="Pass!123"):
    return User.objects.create_user(
        email=email, password=password,
        first_name="Test", last_name="User",
        tenant=tenant, role=role, is_active=True,
    )


def _auth_client(user, tenant_subdomain):
    c = APIClient()
    c.force_authenticate(user=user)
    c.defaults["HTTP_HOST"] = f"{tenant_subdomain}.lms.com"
    return c


def _anon_client(tenant_subdomain):
    c = APIClient()
    c.defaults["HTTP_HOST"] = f"{tenant_subdomain}.lms.com"
    return c


@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
    OTP_TOTP_ISSUER="TestPlatform",
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": [
            "rest_framework_simplejwt.authentication.JWTAuthentication",
        ],
        "DEFAULT_PERMISSION_CLASSES": [
            "rest_framework.permissions.IsAuthenticated",
        ],
        "DEFAULT_THROTTLE_RATES": {
            "twofa_verify": None,
        },
    },
)
class TwoFAStatusTestCase(TestCase):
    """Tests for GET /api/v1/users/auth/2fa/status/"""

    def setUp(self):
        cache.clear()
        self.tenant = _make_tenant("Status School", "status2fa")
        self.user = _make_user("user@status2fa.com", self.tenant)
        self.client = _auth_client(self.user, "status2fa")

    def tearDown(self):
        cache.clear()

    def test_status_requires_authentication(self):
        """2FA status endpoint requires an authenticated user."""
        c = _anon_client("status2fa")
        r = c.get("/api/v1/users/auth/2fa/status/")
        self.assertEqual(r.status_code, 401)

    def test_status_returns_200_for_authenticated_user(self):
        """Authenticated user gets 200 for status endpoint."""
        r = self.client.get("/api/v1/users/auth/2fa/status/")
        self.assertEqual(r.status_code, 200)

    def test_status_shows_2fa_disabled_initially(self):
        """A fresh user has no TOTP device — enabled must be False."""
        r = self.client.get("/api/v1/users/auth/2fa/status/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["enabled"])
        self.assertFalse(r.data["totp_configured"])

    def test_status_includes_required_flag(self):
        """Response must include 'required' field indicating tenant policy."""
        r = self.client.get("/api/v1/users/auth/2fa/status/")
        self.assertIn("required", r.data)

    def test_status_includes_can_disable_flag(self):
        """Response must include 'can_disable' field."""
        r = self.client.get("/api/v1/users/auth/2fa/status/")
        self.assertIn("can_disable", r.data)

    def test_status_required_true_when_tenant_requires_2fa(self):
        """When tenant.require_2fa=True, required must be True in response."""
        tenant = _make_tenant("Required 2FA School", "req2fa", require_2fa=True)
        user = _make_user("user@req2fa.com", tenant)
        client = _auth_client(user, "req2fa")
        r = client.get("/api/v1/users/auth/2fa/status/")
        self.assertTrue(r.data.get("required"))

    def test_status_can_disable_false_when_tenant_requires_2fa(self):
        """When tenant requires 2FA, can_disable must be False."""
        tenant = _make_tenant("Can Disable False School", "nocancel2fa", require_2fa=True)
        user = _make_user("user@nocancel2fa.com", tenant)
        client = _auth_client(user, "nocancel2fa")
        r = client.get("/api/v1/users/auth/2fa/status/")
        self.assertFalse(r.data.get("can_disable"))

    def test_status_backup_codes_remaining_zero_without_2fa(self):
        """Without any 2FA setup, backup_codes_remaining must be 0."""
        r = self.client.get("/api/v1/users/auth/2fa/status/")
        self.assertEqual(r.data.get("backup_codes_remaining"), 0)


@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
    OTP_TOTP_ISSUER="TestPlatform",
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": [
            "rest_framework_simplejwt.authentication.JWTAuthentication",
        ],
        "DEFAULT_PERMISSION_CLASSES": [
            "rest_framework.permissions.IsAuthenticated",
        ],
        "DEFAULT_THROTTLE_RATES": {
            "twofa_verify": None,
        },
    },
)
class TwoFASetupStartTestCase(TestCase):
    """Tests for POST /api/v1/users/auth/2fa/setup/"""

    def setUp(self):
        cache.clear()
        self.tenant = _make_tenant("Setup School", "setup2fa")
        self.user = _make_user("user@setup2fa.com", self.tenant)
        self.client = _auth_client(self.user, "setup2fa")

    def tearDown(self):
        cache.clear()

    def test_setup_requires_authentication(self):
        c = _anon_client("setup2fa")
        r = c.post("/api/v1/users/auth/2fa/setup/")
        self.assertEqual(r.status_code, 401)

    def test_setup_start_returns_200(self):
        r = self.client.post("/api/v1/users/auth/2fa/setup/")
        self.assertEqual(r.status_code, 200)

    def test_setup_returns_secret(self):
        """Setup start must return a base32 secret."""
        r = self.client.post("/api/v1/users/auth/2fa/setup/")
        self.assertEqual(r.status_code, 200)
        secret = r.data.get("secret", "")
        self.assertGreater(len(secret), 10, "Secret must be non-trivial")

    def test_setup_returns_provisioning_uri(self):
        """Setup start must return an otpauth:// provisioning URI."""
        r = self.client.post("/api/v1/users/auth/2fa/setup/")
        self.assertEqual(r.status_code, 200)
        uri = r.data.get("provisioning_uri", "")
        self.assertTrue(uri.startswith("otpauth://"), f"Expected otpauth:// URI, got: {uri}")

    def test_setup_returns_device_id(self):
        """Setup start must return a device_id for confirm step."""
        r = self.client.post("/api/v1/users/auth/2fa/setup/")
        device_id = r.data.get("device_id")
        self.assertIsNotNone(device_id)

    def test_setup_start_idempotent_removes_existing_unconfirmed(self):
        """
        Calling setup twice removes the first unconfirmed device
        and creates a fresh one (prevents orphaned devices).
        """
        from django_otp.plugins.otp_totp.models import TOTPDevice
        # First call
        r1 = self.client.post("/api/v1/users/auth/2fa/setup/")
        self.assertEqual(r1.status_code, 200)
        first_device_id = r1.data.get("device_id")

        # Second call should succeed and create a NEW device
        r2 = self.client.post("/api/v1/users/auth/2fa/setup/")
        self.assertEqual(r2.status_code, 200)
        second_device_id = r2.data.get("device_id")

        # The first unconfirmed device should be gone
        self.assertFalse(
            TOTPDevice.objects.filter(id=first_device_id, confirmed=False).exists(),
            "Old unconfirmed device should have been deleted",
        )

    def test_setup_start_blocked_if_2fa_already_enabled(self):
        """
        If TOTP is already confirmed, setup start must return 400.
        """
        from django_otp.plugins.otp_totp.models import TOTPDevice
        # Manually create a confirmed device
        TOTPDevice.objects.create(
            user=self.user,
            name="Existing Device",
            confirmed=True,
        )
        r = self.client.post("/api/v1/users/auth/2fa/setup/")
        self.assertEqual(r.status_code, 400)
        self.assertIn("already enabled", r.data.get("error", "").lower())


@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
    OTP_TOTP_ISSUER="TestPlatform",
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": [
            "rest_framework_simplejwt.authentication.JWTAuthentication",
        ],
        "DEFAULT_PERMISSION_CLASSES": [
            "rest_framework.permissions.IsAuthenticated",
        ],
        "DEFAULT_THROTTLE_RATES": {
            "twofa_verify": None,
        },
    },
)
class TwoFASetupConfirmTestCase(TestCase):
    """Tests for POST /api/v1/users/auth/2fa/confirm/"""

    def setUp(self):
        cache.clear()
        self.tenant = _make_tenant("Confirm School", "confirm2fa")
        self.user = _make_user("user@confirm2fa.com", self.tenant)
        self.client = _auth_client(self.user, "confirm2fa")

    def tearDown(self):
        cache.clear()

    def test_confirm_requires_authentication(self):
        c = _anon_client("confirm2fa")
        r = c.post("/api/v1/users/auth/2fa/confirm/", {"code": "123456"}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_confirm_without_pending_setup_returns_400(self):
        """Confirm with no pending (unconfirmed) device must return 400."""
        r = self.client.post(
            "/api/v1/users/auth/2fa/confirm/", {"code": "123456"}, format="json"
        )
        self.assertEqual(r.status_code, 400)

    def test_confirm_missing_code_returns_400(self):
        """Empty/missing code must return 400."""
        r = self.client.post(
            "/api/v1/users/auth/2fa/confirm/", {}, format="json"
        )
        self.assertEqual(r.status_code, 400)

    def test_confirm_short_code_returns_400(self):
        """A code that is not 6 digits must return 400."""
        r = self.client.post(
            "/api/v1/users/auth/2fa/confirm/", {"code": "123"}, format="json"
        )
        self.assertEqual(r.status_code, 400)

    def test_confirm_invalid_code_for_existing_device_returns_400(self):
        """
        With an unconfirmed device, submitting a wrong TOTP code returns 400.
        We mock verify_token to return False.
        """
        from django_otp.plugins.otp_totp.models import TOTPDevice

        device = TOTPDevice.objects.create(
            user=self.user,
            name="Pending Device",
            confirmed=False,
        )
        with patch.object(device.__class__, "verify_token", return_value=False):
            # We need to patch on the queryset fetch
            with patch("apps.users.twofa_views.TOTPDevice.objects") as mock_mgr:
                mock_qs = MagicMock()
                mock_mgr.filter.return_value = mock_qs
                mock_qs.first.return_value = device
                with patch.object(device, "verify_token", return_value=False):
                    device.verify_token = lambda code: False
                    r = self.client.post(
                        "/api/v1/users/auth/2fa/confirm/",
                        {"code": "000000"},
                        format="json",
                    )
        self.assertEqual(r.status_code, 400)

    def test_confirm_valid_code_returns_200_with_backup_codes(self):
        """
        With a valid TOTP code, confirm returns 200 and backup_codes.
        We mock verify_token to return True.
        """
        from django_otp.plugins.otp_totp.models import TOTPDevice

        device = TOTPDevice.objects.create(
            user=self.user,
            name="Pending Device (valid)",
            confirmed=False,
        )
        with patch.object(TOTPDevice, "verify_token", return_value=True):
            r = self.client.post(
                "/api/v1/users/auth/2fa/confirm/",
                {"code": "123456"},
                format="json",
            )
        self.assertEqual(r.status_code, 200)
        self.assertIn("backup_codes", r.data)
        self.assertIsInstance(r.data["backup_codes"], list)
        self.assertGreater(len(r.data["backup_codes"]), 0)

    def test_confirm_valid_code_marks_device_confirmed(self):
        """After successful confirm, the TOTP device must be confirmed."""
        from django_otp.plugins.otp_totp.models import TOTPDevice

        device = TOTPDevice.objects.create(
            user=self.user,
            name="Confirm Pending",
            confirmed=False,
        )
        with patch.object(TOTPDevice, "verify_token", return_value=True):
            self.client.post(
                "/api/v1/users/auth/2fa/confirm/",
                {"code": "123456"},
                format="json",
            )
        device.refresh_from_db()
        self.assertTrue(device.confirmed)


@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
    OTP_TOTP_ISSUER="TestPlatform",
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": [
            "rest_framework_simplejwt.authentication.JWTAuthentication",
        ],
        "DEFAULT_PERMISSION_CLASSES": [
            "rest_framework.permissions.IsAuthenticated",
        ],
        "DEFAULT_THROTTLE_RATES": {
            "twofa_verify": None,
        },
    },
)
class TwoFADisableTestCase(TestCase):
    """Tests for POST /api/v1/users/auth/2fa/disable/"""

    def setUp(self):
        cache.clear()
        self.tenant = _make_tenant("Disable School", "disable2fa")
        self.user = _make_user("user@disable2fa.com", self.tenant, password="Pass!123")
        self.client = _auth_client(self.user, "disable2fa")

        # Create a confirmed TOTP device
        from django_otp.plugins.otp_totp.models import TOTPDevice
        self.device = TOTPDevice.objects.create(
            user=self.user,
            name="Disable Test Device",
            confirmed=True,
        )

    def tearDown(self):
        cache.clear()

    def test_disable_requires_authentication(self):
        c = _anon_client("disable2fa")
        r = c.post(
            "/api/v1/users/auth/2fa/disable/",
            {"code": "123456", "password": "Pass!123"},
            format="json",
        )
        self.assertEqual(r.status_code, 401)

    def test_disable_with_wrong_password_returns_400(self):
        """Invalid password must return 400."""
        with patch.object(
            self.device.__class__, "verify_token", return_value=True
        ):
            r = self.client.post(
                "/api/v1/users/auth/2fa/disable/",
                {"code": "123456", "password": "WrongPassword!"},
                format="json",
            )
        self.assertEqual(r.status_code, 400)
        self.assertIn("password", r.data.get("error", "").lower())

    def test_disable_blocked_when_tenant_requires_2fa(self):
        """Cannot disable 2FA if the tenant requires it."""
        tenant = _make_tenant("Mandatory 2FA", "mandatory2fa", require_2fa=True)
        user = _make_user("user@mandatory2fa.com", tenant, password="Pass!123")
        client = _auth_client(user, "mandatory2fa")

        from django_otp.plugins.otp_totp.models import TOTPDevice
        TOTPDevice.objects.create(user=user, name="Mandatory Device", confirmed=True)

        r = client.post(
            "/api/v1/users/auth/2fa/disable/",
            {"code": "123456", "password": "Pass!123"},
            format="json",
        )
        self.assertEqual(r.status_code, 403)
        self.assertIn("requires", r.data.get("error", "").lower())

    def test_disable_with_no_2fa_returns_400(self):
        """Trying to disable when 2FA is not enabled should return 400."""
        # Delete the device
        self.device.delete()
        r = self.client.post(
            "/api/v1/users/auth/2fa/disable/",
            {"code": "123456", "password": "Pass!123"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_disable_with_invalid_totp_code_returns_400(self):
        """Wrong TOTP code returns 400."""
        from django_otp.plugins.otp_totp.models import TOTPDevice
        with patch.object(TOTPDevice, "verify_token", return_value=False):
            from django_otp.plugins.otp_static.models import StaticDevice
            with patch.object(StaticDevice, "verify_token", return_value=False):
                r = self.client.post(
                    "/api/v1/users/auth/2fa/disable/",
                    {"code": "000000", "password": "Pass!123"},
                    format="json",
                )
        self.assertEqual(r.status_code, 400)

    def test_disable_with_valid_code_and_password_returns_200(self):
        """Valid password + valid TOTP code should successfully disable 2FA."""
        from django_otp.plugins.otp_totp.models import TOTPDevice
        with patch.object(TOTPDevice, "verify_token", return_value=True):
            r = self.client.post(
                "/api/v1/users/auth/2fa/disable/",
                {"code": "123456", "password": "Pass!123"},
                format="json",
            )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data.get("success"))

    def test_disable_removes_totp_device(self):
        """After successful disable, the TOTP device should be deleted."""
        from django_otp.plugins.otp_totp.models import TOTPDevice
        with patch.object(TOTPDevice, "verify_token", return_value=True):
            self.client.post(
                "/api/v1/users/auth/2fa/disable/",
                {"code": "123456", "password": "Pass!123"},
                format="json",
            )
        remaining = TOTPDevice.objects.filter(user=self.user, confirmed=True).count()
        self.assertEqual(remaining, 0)


@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
    OTP_TOTP_ISSUER="TestPlatform",
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": [
            "rest_framework_simplejwt.authentication.JWTAuthentication",
        ],
        "DEFAULT_PERMISSION_CLASSES": [
            "rest_framework.permissions.IsAuthenticated",
        ],
        "DEFAULT_THROTTLE_RATES": {
            "twofa_verify": None,
        },
    },
)
class TwoFAVerifyTestCase(TestCase):
    """
    Tests for POST /api/v1/users/auth/2fa/verify/ — the login challenge flow.
    This endpoint is public (no JWT auth required) but uses a short-lived
    cache token to identify the pending-login user.
    """

    def setUp(self):
        cache.clear()
        self.tenant = _make_tenant("Verify School", "verify2fa")
        self.user = _make_user("user@verify2fa.com", self.tenant)
        self.client = _anon_client("verify2fa")

        # Create a confirmed TOTP device
        from django_otp.plugins.otp_totp.models import TOTPDevice
        self.device = TOTPDevice.objects.create(
            user=self.user,
            name="Verify Test Device",
            confirmed=True,
        )

    def tearDown(self):
        cache.clear()

    def _store_challenge(self, user_id=None):
        """Helper: store a 2FA challenge token in cache."""
        token = str(uuid.uuid4())
        cache.set(f"2fa_challenge:{token}", str(user_id or self.user.id), timeout=300)
        return token

    def test_verify_missing_challenge_token_returns_400(self):
        r = self.client.post(
            "/api/v1/users/auth/2fa/verify/",
            {"code": "123456"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_verify_missing_code_returns_400(self):
        token = self._store_challenge()
        r = self.client.post(
            "/api/v1/users/auth/2fa/verify/",
            {"challenge_token": token},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_verify_with_invalid_challenge_token_returns_400(self):
        """Non-existent challenge token must return 400."""
        r = self.client.post(
            "/api/v1/users/auth/2fa/verify/",
            {"challenge_token": "does-not-exist", "code": "123456"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("invalid or expired", r.data.get("error", "").lower())

    def test_verify_with_expired_challenge_token_returns_400(self):
        """After cache expiry, the challenge token must return 400."""
        token = str(uuid.uuid4())
        # Don't store the token — it effectively expired
        r = self.client.post(
            "/api/v1/users/auth/2fa/verify/",
            {"challenge_token": token, "code": "123456"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_verify_with_wrong_totp_code_returns_400(self):
        """Wrong TOTP code must return 400."""
        token = self._store_challenge()
        from django_otp.plugins.otp_totp.models import TOTPDevice
        from django_otp.plugins.otp_static.models import StaticDevice
        with patch.object(TOTPDevice, "verify_token", return_value=False):
            with patch.object(StaticDevice, "verify_token", return_value=False):
                r = self.client.post(
                    "/api/v1/users/auth/2fa/verify/",
                    {"challenge_token": token, "code": "000000"},
                    format="json",
                )
        self.assertEqual(r.status_code, 400)
        self.assertIn("invalid", r.data.get("error", "").lower())

    def test_verify_with_valid_totp_code_returns_200_with_tokens(self):
        """Correct TOTP code must return 200 with JWT access and refresh tokens."""
        token = self._store_challenge()
        from django_otp.plugins.otp_totp.models import TOTPDevice
        with patch.object(TOTPDevice, "verify_token", return_value=True):
            r = self.client.post(
                "/api/v1/users/auth/2fa/verify/",
                {"challenge_token": token, "code": "123456"},
                format="json",
            )
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.data)
        self.assertIn("refresh", r.data)

    def test_verify_deletes_challenge_token_on_success(self):
        """After successful verify, the challenge token must be invalidated."""
        token = self._store_challenge()
        from django_otp.plugins.otp_totp.models import TOTPDevice
        with patch.object(TOTPDevice, "verify_token", return_value=True):
            self.client.post(
                "/api/v1/users/auth/2fa/verify/",
                {"challenge_token": token, "code": "123456"},
                format="json",
            )
        # Token must be gone from cache
        self.assertIsNone(cache.get(f"2fa_challenge:{token}"))

    def test_verify_with_backup_code_returns_200(self):
        """A valid backup (static) code must also succeed the 2FA verify."""
        from django_otp.plugins.otp_totp.models import TOTPDevice
        from django_otp.plugins.otp_static.models import StaticDevice
        token = self._store_challenge()
        with patch.object(TOTPDevice, "verify_token", return_value=False):
            with patch.object(StaticDevice, "verify_token", return_value=True):
                r = self.client.post(
                    "/api/v1/users/auth/2fa/verify/",
                    {"challenge_token": token, "code": "ABCD1234"},
                    format="json",
                )
        self.assertEqual(r.status_code, 200)
        self.assertIn("backup_code_used", r.data)
        self.assertTrue(r.data["backup_code_used"])

    def test_verify_does_not_leak_user_info_on_invalid_challenge(self):
        """
        Security: the error message for invalid challenge tokens must not
        reveal whether the user ID exists or not.
        """
        r = self.client.post(
            "/api/v1/users/auth/2fa/verify/",
            {"challenge_token": "nonexistent-token-xxx", "code": "123456"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)
        error_msg = r.data.get("error", "")
        # Must not contain "user not found", "does not exist", or similar
        self.assertNotIn("user not found", error_msg.lower())
        self.assertNotIn("does not exist", error_msg.lower())


@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
    OTP_TOTP_ISSUER="TestPlatform",
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": [
            "rest_framework_simplejwt.authentication.JWTAuthentication",
        ],
        "DEFAULT_PERMISSION_CLASSES": [
            "rest_framework.permissions.IsAuthenticated",
        ],
        "DEFAULT_THROTTLE_RATES": {
            "twofa_verify": None,
        },
    },
)
class TwoFARegenerateBackupCodesTestCase(TestCase):
    """Tests for POST /api/v1/users/auth/2fa/backup-codes/"""

    def setUp(self):
        cache.clear()
        self.tenant = _make_tenant("Backup School", "backup2fa")
        self.user = _make_user("user@backup2fa.com", self.tenant)
        self.client = _auth_client(self.user, "backup2fa")

        from django_otp.plugins.otp_totp.models import TOTPDevice
        self.device = TOTPDevice.objects.create(
            user=self.user,
            name="Backup Test Device",
            confirmed=True,
        )

    def tearDown(self):
        cache.clear()

    def test_backup_codes_requires_authentication(self):
        c = _anon_client("backup2fa")
        r = c.post("/api/v1/users/auth/2fa/backup-codes/", {"code": "123456"}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_backup_codes_requires_active_2fa(self):
        """Regenerating backup codes without 2FA enabled must return 400."""
        self.device.confirmed = False
        self.device.save()
        r = self.client.post(
            "/api/v1/users/auth/2fa/backup-codes/", {"code": "123456"}, format="json"
        )
        self.assertEqual(r.status_code, 400)

    def test_backup_codes_with_invalid_totp_code_returns_400(self):
        """Wrong TOTP code must return 400."""
        from django_otp.plugins.otp_totp.models import TOTPDevice
        with patch.object(TOTPDevice, "verify_token", return_value=False):
            r = self.client.post(
                "/api/v1/users/auth/2fa/backup-codes/",
                {"code": "000000"},
                format="json",
            )
        self.assertEqual(r.status_code, 400)

    def test_backup_codes_regeneration_returns_200_with_codes(self):
        """Valid TOTP code triggers backup code regeneration and returns codes list."""
        from django_otp.plugins.otp_totp.models import TOTPDevice
        with patch.object(TOTPDevice, "verify_token", return_value=True):
            r = self.client.post(
                "/api/v1/users/auth/2fa/backup-codes/",
                {"code": "123456"},
                format="json",
            )
        self.assertEqual(r.status_code, 200)
        codes = r.data.get("backup_codes", [])
        self.assertIsInstance(codes, list)
        self.assertGreater(len(codes), 0)

    def test_backup_codes_returns_warning_message(self):
        """Response must include a warning about saving codes."""
        from django_otp.plugins.otp_totp.models import TOTPDevice
        with patch.object(TOTPDevice, "verify_token", return_value=True):
            r = self.client.post(
                "/api/v1/users/auth/2fa/backup-codes/",
                {"code": "123456"},
                format="json",
            )
        self.assertIn("warning", r.data)
