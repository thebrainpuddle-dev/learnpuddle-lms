# tests/users/test_auth_views.py
"""
Tests for user authentication endpoints.

Covers:
- POST /api/v1/users/auth/login/     — JWT token issuance
- POST /api/v1/users/auth/logout/    — token blacklisting
- POST /api/v1/users/auth/refresh/   — access token rotation
- GET/PATCH /api/v1/users/auth/me/   — profile retrieval + update
- POST /api/v1/users/auth/change-password/
- POST /api/v1/users/auth/request-password-reset/
- POST /api/v1/users/auth/confirm-password-reset/
- GET/PATCH /api/v1/users/auth/preferences/
- POST /api/v1/users/auth/register-teacher/  — admin endpoint
"""

from django.test import TestCase, override_settings
from django.core import mail
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant(name, subdomain, email="tenant@example.com"):
    return Tenant.objects.create(
        name=name, slug=subdomain, subdomain=subdomain,
        email=email, is_active=True,
    )


def _make_user(email, tenant, role="TEACHER", password="Pass!123", is_active=True):
    return User.objects.create_user(
        email=email, password=password,
        first_name="Test", last_name="User",
        tenant=tenant, role=role, is_active=is_active,
    )


def _anon_client(tenant_subdomain):
    """Return an unauthenticated APIClient configured for the given tenant."""
    c = APIClient()
    c.defaults["HTTP_HOST"] = f"{tenant_subdomain}.lms.com"
    return c


def _auth_client(user, tenant_subdomain):
    """Return a force-authenticated APIClient for the given tenant."""
    c = APIClient()
    c.force_authenticate(user=user)
    c.defaults["HTTP_HOST"] = f"{tenant_subdomain}.lms.com"
    return c


# ===========================================================================
# Login
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": [
            "rest_framework_simplejwt.authentication.JWTAuthentication",
        ],
        "DEFAULT_PERMISSION_CLASSES": [
            "rest_framework.permissions.IsAuthenticated",
        ],
        # Use None to disable throttling (rate=None → allow_request always True)
        "DEFAULT_THROTTLE_RATES": {
            "login": None,
            "password_reset": None,
            "register": None,
            "email_verify": None,
            "resend_verify": None,
        },
    },
)
class LoginViewTestCase(TestCase):
    """
    Tests for POST /api/v1/users/auth/login/
    """

    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # Prevent throttle bleed-over between tests
        self.tenant = _make_tenant("Login School", "login")
        self.user = _make_user("teacher@login.com", self.tenant, role="TEACHER")
        self.admin = _make_user("admin@login.com", self.tenant, role="SCHOOL_ADMIN")
        self.client = _anon_client("login")

    def test_login_with_valid_credentials_returns_200_and_tokens(self):
        r = self.client.post(
            "/api/v1/users/auth/login/",
            {"email": "teacher@login.com", "password": "Pass!123"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("tokens", r.data)
        self.assertIn("access", r.data["tokens"])
        self.assertIn("refresh", r.data["tokens"])

    def test_login_returns_user_data(self):
        r = self.client.post(
            "/api/v1/users/auth/login/",
            {"email": "teacher@login.com", "password": "Pass!123"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("user", r.data)
        self.assertEqual(r.data["user"]["email"], "teacher@login.com")

    def test_login_with_identifier_field_works(self):
        """Login supports 'identifier' as alias for 'email'."""
        r = self.client.post(
            "/api/v1/users/auth/login/",
            {"identifier": "teacher@login.com", "password": "Pass!123"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("tokens", r.data)

    def test_login_with_wrong_password_returns_400(self):
        r = self.client.post(
            "/api/v1/users/auth/login/",
            {"email": "teacher@login.com", "password": "WrongPassword!"},
            format="json",
        )
        self.assertIn(r.status_code, [400, 401])

    def test_login_with_nonexistent_email_returns_400(self):
        r = self.client.post(
            "/api/v1/users/auth/login/",
            {"email": "nobody@login.com", "password": "Pass!123"},
            format="json",
        )
        self.assertIn(r.status_code, [400, 401])

    def test_login_with_inactive_user_returns_error(self):
        inactive = _make_user(
            "inactive@login.com", self.tenant, is_active=False
        )
        r = self.client.post(
            "/api/v1/users/auth/login/",
            {"email": "inactive@login.com", "password": "Pass!123"},
            format="json",
        )
        self.assertIn(r.status_code, [400, 401])

    def test_login_without_password_returns_400(self):
        r = self.client.post(
            "/api/v1/users/auth/login/",
            {"email": "teacher@login.com"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_login_without_identifier_returns_400(self):
        r = self.client.post(
            "/api/v1/users/auth/login/",
            {"password": "Pass!123"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_login_sets_last_login_timestamp(self):
        self.assertIsNone(self.user.last_login)
        self.client.post(
            "/api/v1/users/auth/login/",
            {"email": "teacher@login.com", "password": "Pass!123"},
            format="json",
        )
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_login)

    def test_login_with_must_change_password_flag_includes_warning(self):
        self.user.must_change_password = True
        self.user.save(update_fields=["must_change_password"])
        r = self.client.post(
            "/api/v1/users/auth/login/",
            {"email": "teacher@login.com", "password": "Pass!123"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data.get("must_change_password"))


# ===========================================================================
# Logout
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": [
            "rest_framework_simplejwt.authentication.JWTAuthentication",
        ],
        "DEFAULT_PERMISSION_CLASSES": [
            "rest_framework.permissions.IsAuthenticated",
        ],
        "DEFAULT_THROTTLE_RATES": {
            "login": None, "password_reset": None,
            "register": None, "email_verify": None, "resend_verify": None,
        },
    },
)
class LogoutViewTestCase(TestCase):
    """
    Tests for POST /api/v1/users/auth/logout/
    """

    def setUp(self):
        self.tenant = _make_tenant("Logout School", "logout")
        self.user = _make_user("teacher@logout.com", self.tenant)

    def test_logout_with_valid_refresh_token_returns_200(self):
        refresh = RefreshToken.for_user(self.user)
        c = _auth_client(self.user, "logout")
        r = c.post(
            "/api/v1/users/auth/logout/",
            {"refresh_token": str(refresh)},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("message", r.data)

    def test_logout_without_refresh_token_returns_400(self):
        c = _auth_client(self.user, "logout")
        r = c.post(
            "/api/v1/users/auth/logout/",
            {},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_logout_requires_authentication(self):
        refresh = RefreshToken.for_user(self.user)
        c = _anon_client("logout")
        r = c.post(
            "/api/v1/users/auth/logout/",
            {"refresh_token": str(refresh)},
            format="json",
        )
        self.assertEqual(r.status_code, 401)

    def test_logout_blacklists_refresh_token(self):
        """After logout, the same refresh token must not issue a new access token."""
        refresh = RefreshToken.for_user(self.user)
        refresh_str = str(refresh)

        # Logout
        c = _auth_client(self.user, "logout")
        c.post(
            "/api/v1/users/auth/logout/",
            {"refresh_token": refresh_str},
            format="json",
        )

        # Try to use the blacklisted refresh token
        r = c.post(
            "/api/v1/users/auth/refresh/",
            {"refresh_token": refresh_str},
            format="json",
        )
        self.assertEqual(r.status_code, 401)

    def test_logout_with_invalid_token_returns_400(self):
        c = _auth_client(self.user, "logout")
        r = c.post(
            "/api/v1/users/auth/logout/",
            {"refresh_token": "not.a.real.jwt.token"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)


# ===========================================================================
# Token Refresh
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
    REST_FRAMEWORK={
        "DEFAULT_THROTTLE_RATES": {
            "login": None, "password_reset": None,
            "register": None, "email_verify": None, "resend_verify": None,
        },
    },
)
class RefreshTokenViewTestCase(TestCase):
    """
    Tests for POST /api/v1/users/auth/refresh/
    """

    def setUp(self):
        self.tenant = _make_tenant("Refresh School", "refresh")
        self.user = _make_user("user@refresh.com", self.tenant)

    def test_refresh_with_valid_token_returns_new_access_token(self):
        refresh = RefreshToken.for_user(self.user)
        c = _anon_client("refresh")
        r = c.post(
            "/api/v1/users/auth/refresh/",
            {"refresh_token": str(refresh)},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.data)
        # Access token should be a JWT (3 parts separated by .)
        self.assertEqual(len(r.data["access"].split(".")), 3)

    def test_refresh_with_no_token_returns_400(self):
        c = _anon_client("refresh")
        r = c.post("/api/v1/users/auth/refresh/", {}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_refresh_with_garbage_token_returns_401(self):
        c = _anon_client("refresh")
        r = c.post(
            "/api/v1/users/auth/refresh/",
            {"refresh_token": "garbage.not.a.token"},
            format="json",
        )
        self.assertEqual(r.status_code, 401)

    def test_refresh_does_not_require_authentication(self):
        """The refresh endpoint is intentionally public (no auth required)."""
        refresh = RefreshToken.for_user(self.user)
        c = APIClient()  # No auth, no host header needed
        r = c.post(
            "/api/v1/users/auth/refresh/",
            {"refresh_token": str(refresh)},
            format="json",
        )
        self.assertEqual(r.status_code, 200)


# ===========================================================================
# Me (Profile)
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class MeViewTestCase(TestCase):
    """
    Tests for GET/PATCH /api/v1/users/auth/me/
    """

    def setUp(self):
        self.tenant = _make_tenant("Me School", "me")
        self.user = _make_user("me@me.com", self.tenant)

    def test_get_me_returns_current_user_data(self):
        c = _auth_client(self.user, "me")
        r = c.get("/api/v1/users/auth/me/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["email"], "me@me.com")

    def test_get_me_requires_authentication(self):
        c = _anon_client("me")
        r = c.get("/api/v1/users/auth/me/")
        self.assertEqual(r.status_code, 401)

    def test_patch_me_updates_first_name(self):
        c = _auth_client(self.user, "me")
        r = c.patch(
            "/api/v1/users/auth/me/",
            {"first_name": "Updated"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["first_name"], "Updated")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Updated")

    def test_patch_me_updates_department(self):
        c = _auth_client(self.user, "me")
        r = c.patch(
            "/api/v1/users/auth/me/",
            {"department": "Mathematics"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.department, "Mathematics")

    def test_patch_me_updates_bio(self):
        c = _auth_client(self.user, "me")
        r = c.patch(
            "/api/v1/users/auth/me/",
            {"bio": "A passionate educator."},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.bio, "A passionate educator.")

    def test_patch_me_ignores_unknown_fields(self):
        """PATCH must silently ignore fields not in the allowlist."""
        c = _auth_client(self.user, "me")
        r = c.patch(
            "/api/v1/users/auth/me/",
            {"role": "SUPER_ADMIN", "is_active": False},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        # Role must NOT have changed
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, "TEACHER")
        self.assertTrue(self.user.is_active)


# ===========================================================================
# Change Password
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
    REST_FRAMEWORK={
        "DEFAULT_THROTTLE_RATES": {
            "login": None,
            "password_reset": None,
            "register": None,
            "email_verify": None,
            "resend_verify": None,
        },
    },
)
class ChangePasswordViewTestCase(TestCase):
    """
    Tests for POST /api/v1/users/auth/change-password/
    Serializer requires: old_password, new_password, new_password_confirm
    """

    def setUp(self):
        self.tenant = _make_tenant("Passwd School", "passwd")
        self.user = _make_user("user@passwd.com", self.tenant, password="OldPass!123")
        self.user.must_change_password = True
        self.user.save(update_fields=["must_change_password"])

    def test_change_password_with_correct_old_password_returns_200(self):
        c = _auth_client(self.user, "passwd")
        r = c.post(
            "/api/v1/users/auth/change-password/",
            {
                "old_password": "OldPass!123",
                "new_password": "NewPass!456XYZ",  # 14 chars, meets min_length=12
                "new_password_confirm": "NewPass!456XYZ",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 200)

    def test_change_password_clears_must_change_password_flag(self):
        c = _auth_client(self.user, "passwd")
        c.post(
            "/api/v1/users/auth/change-password/",
            {
                "old_password": "OldPass!123",
                "new_password": "NewPass!456XYZ",  # 14 chars, meets min_length=12
                "new_password_confirm": "NewPass!456XYZ",
            },
            format="json",
        )
        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)

    def test_change_password_requires_authentication(self):
        c = _anon_client("passwd")
        r = c.post(
            "/api/v1/users/auth/change-password/",
            {
                "old_password": "OldPass!123",
                "new_password": "NewPass!456",
                "new_password_confirm": "NewPass!456",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 401)

    def test_change_password_mismatched_confirm_returns_400(self):
        c = _auth_client(self.user, "passwd")
        r = c.post(
            "/api/v1/users/auth/change-password/",
            {
                "old_password": "OldPass!123",
                "new_password": "NewPass!456",
                "new_password_confirm": "DifferentPass!999",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_change_password_without_confirm_returns_400(self):
        c = _auth_client(self.user, "passwd")
        r = c.post(
            "/api/v1/users/auth/change-password/",
            {"old_password": "OldPass!123", "new_password": "NewPass!456"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_change_password_new_password_is_actually_set(self):
        c = _auth_client(self.user, "passwd")
        c.post(
            "/api/v1/users/auth/change-password/",
            {
                "old_password": "OldPass!123",
                "new_password": "BrandNew!789",
                "new_password_confirm": "BrandNew!789",
            },
            format="json",
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("BrandNew!789"))
        self.assertFalse(self.user.check_password("OldPass!123"))


# ===========================================================================
# Password Reset
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    REST_FRAMEWORK={
        "DEFAULT_THROTTLE_RATES": {
            "login": None, "password_reset": None,
            "register": None, "email_verify": None, "resend_verify": None,
        },
    },
)
class PasswordResetViewTestCase(TestCase):
    """
    Tests for:
    - POST /api/v1/users/auth/request-password-reset/
    - POST /api/v1/users/auth/confirm-password-reset/
    """

    def setUp(self):
        self.tenant = _make_tenant("Reset School", "reset")
        self.user = _make_user("user@reset.com", self.tenant)
        self.client = _anon_client("reset")

    def test_request_reset_returns_200_for_existing_email(self):
        """Must always return 200 to prevent email enumeration."""
        r = self.client.post(
            "/api/v1/users/auth/request-password-reset/",
            {"email": "user@reset.com"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("message", r.data)

    def test_request_reset_returns_200_for_nonexistent_email(self):
        """Must still return 200 for unknown email (anti-enumeration)."""
        r = self.client.post(
            "/api/v1/users/auth/request-password-reset/",
            {"email": "nobody@reset.com"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)

    def test_request_reset_without_email_returns_400(self):
        r = self.client.post(
            "/api/v1/users/auth/request-password-reset/",
            {},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_confirm_reset_without_required_fields_returns_400(self):
        r = self.client.post(
            "/api/v1/users/auth/confirm-password-reset/",
            {"uid": "abc"},  # Missing token and new_password
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_confirm_reset_with_invalid_uid_returns_400(self):
        r = self.client.post(
            "/api/v1/users/auth/confirm-password-reset/",
            {"uid": "invalid", "token": "invalid", "new_password": "NewPass!789"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_confirm_reset_with_valid_token_resets_password(self):
        """Full flow: request reset → extract token from email → confirm reset."""
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        r = self.client.post(
            "/api/v1/users/auth/confirm-password-reset/",
            {"uid": uid, "token": token, "new_password": "NewValid!999"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewValid!999"))


# ===========================================================================
# Preferences
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class PreferencesViewTestCase(TestCase):
    """
    Tests for GET/PATCH /api/v1/users/auth/preferences/
    """

    def setUp(self):
        self.tenant = _make_tenant("Prefs School", "prefs")
        self.user = _make_user("user@prefs.com", self.tenant)

    def test_get_preferences_returns_200(self):
        c = _auth_client(self.user, "prefs")
        r = c.get("/api/v1/users/auth/preferences/")
        self.assertEqual(r.status_code, 200)

    def test_get_preferences_requires_authentication(self):
        c = _anon_client("prefs")
        r = c.get("/api/v1/users/auth/preferences/")
        self.assertEqual(r.status_code, 401)

    def test_patch_preferences_updates_email_courses(self):
        c = _auth_client(self.user, "prefs")
        r = c.patch(
            "/api/v1/users/auth/preferences/",
            {"email_courses": True},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.notification_preferences.get("email_courses"))

    def test_patch_preferences_ignores_unknown_keys(self):
        c = _auth_client(self.user, "prefs")
        r = c.patch(
            "/api/v1/users/auth/preferences/",
            {"evil_setting": True, "email_courses": False},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertNotIn("evil_setting", self.user.notification_preferences)

    def test_patch_preferences_updates_content_editor_mode(self):
        c = _auth_client(self.user, "prefs")
        r = c.patch(
            "/api/v1/users/auth/preferences/",
            {"content_editor_mode": "MARKDOWN"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(
            self.user.notification_preferences.get("content_editor_mode"), "MARKDOWN"
        )


# ===========================================================================
# Register Teacher (Admin endpoint)
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    REST_FRAMEWORK={
        "DEFAULT_THROTTLE_RATES": {
            "login": None, "password_reset": None,
            "register": None, "email_verify": None, "resend_verify": None,
        },
    },
)
class RegisterTeacherViewTestCase(TestCase):
    """
    Tests for POST /api/v1/users/auth/register-teacher/
    This is an admin-only endpoint.
    """

    def setUp(self):
        self.tenant = _make_tenant("Reg School", "reg")
        self.admin = _make_user("admin@reg.com", self.tenant, role="SCHOOL_ADMIN")
        self.teacher = _make_user("teacher@reg.com", self.tenant, role="TEACHER")

    def test_register_teacher_as_admin_returns_201(self):
        c = _auth_client(self.admin, "reg")
        r = c.post(
            "/api/v1/users/auth/register-teacher/",
            {
                "email": "newteacher@reg.com",
                "first_name": "New",
                "last_name": "Teacher",
                "password": "TeachPass!789",
                "password_confirm": "TeachPass!789",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["email"], "newteacher@reg.com")

    def test_register_teacher_creates_user_with_teacher_role(self):
        c = _auth_client(self.admin, "reg")
        c.post(
            "/api/v1/users/auth/register-teacher/",
            {
                "email": "newrole@reg.com",
                "first_name": "New",
                "last_name": "Role",
                "password": "TeachPass!789",
                "password_confirm": "TeachPass!789",
            },
            format="json",
        )
        new_user = User.objects.get(email="newrole@reg.com")
        self.assertEqual(new_user.role, "TEACHER")

    def test_register_teacher_assigns_to_correct_tenant(self):
        c = _auth_client(self.admin, "reg")
        c.post(
            "/api/v1/users/auth/register-teacher/",
            {
                "email": "tenant@reg.com",
                "first_name": "Tenant",
                "last_name": "User",
                "password": "TeachPass!789",
                "password_confirm": "TeachPass!789",
            },
            format="json",
        )
        new_user = User.objects.get(email="tenant@reg.com")
        self.assertEqual(new_user.tenant_id, self.tenant.id)

    def test_register_teacher_as_teacher_returns_403(self):
        """Teachers must not be able to register other teachers."""
        c = _auth_client(self.teacher, "reg")
        r = c.post(
            "/api/v1/users/auth/register-teacher/",
            {
                "email": "shouldfail@reg.com",
                "first_name": "Fail",
                "last_name": "User",
                "password": "TeachPass!789",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 403)

    def test_register_teacher_requires_authentication(self):
        c = _anon_client("reg")
        r = c.post(
            "/api/v1/users/auth/register-teacher/",
            {"email": "anon@reg.com", "password": "AnonPass!789"},
            format="json",
        )
        self.assertEqual(r.status_code, 401)

    def test_register_teacher_with_duplicate_email_returns_400(self):
        """Cannot register two users with the same email."""
        c = _auth_client(self.admin, "reg")
        c.post(
            "/api/v1/users/auth/register-teacher/",
            {
                "email": "dup@reg.com",
                "first_name": "First",
                "last_name": "User",
                "password": "TeachPass!789",
                "password_confirm": "TeachPass!789",
            },
            format="json",
        )
        # Second registration with same email
        r = c.post(
            "/api/v1/users/auth/register-teacher/",
            {
                "email": "dup@reg.com",
                "first_name": "Second",
                "last_name": "User",
                "password": "TeachPass!789",
                "password_confirm": "TeachPass!789",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 400)
