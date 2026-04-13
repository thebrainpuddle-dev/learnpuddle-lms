# apps/users/tests_auth_extended.py
#
# Extended authentication tests covering flows not yet exercised:
#   - Register teacher (admin endpoint)
#   - Password reset request (always returns 200 for privacy)
#   - Confirm password reset validation edge cases
#   - Email verification flow
#   - Notification preferences PATCH / GET
#   - Me endpoint PATCH (profile fields)
#   - Logout without refresh token
#   - Login with must_change_password flag
#   - Login with wrong password
#   - Login with inactive user
#   - Change password with wrong old_password
#   - Change password with mismatched new_password vs confirm
#   - Me endpoint GET
#   - Logout happy path with valid refresh token
#   - Refresh token endpoint

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User


HOST = "test.lms.com"


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class RegisterTeacherTestCase(TestCase):
    """Tests for POST /api/users/auth/register-teacher/."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Register School",
            slug="reg-school",
            subdomain="test",
            email="reg@test.com",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            email="admin@reg.test",
            password="admin123",
            first_name="Admin",
            last_name="Reg",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@reg.test",
            password="teacher123",
            first_name="Teacher",
            last_name="Reg",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )

    def _auth_admin(self):
        self.client.force_authenticate(user=self.admin)

    def _auth_teacher(self):
        self.client.force_authenticate(user=self.teacher)

    def _post(self, url, data=None, **kw):
        return self.client.post(url, data, format="json", HTTP_HOST=HOST, **kw)

    def test_admin_can_register_teacher(self):
        self._auth_admin()
        resp = self._post("/api/users/auth/register-teacher/", {
            "email": "newteacher@reg.test",
            "first_name": "New",
            "last_name": "Teacher",
            "password": "StrongPass123!",
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["email"], "newteacher@reg.test")
        self.assertEqual(resp.json()["role"], "TEACHER")

    def test_teacher_cannot_register_teacher(self):
        self._auth_teacher()
        resp = self._post("/api/users/auth/register-teacher/", {
            "email": "another@reg.test",
            "first_name": "Another",
            "last_name": "Teacher",
            "password": "StrongPass123!",
        })
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_cannot_register_teacher(self):
        resp = self._post("/api/users/auth/register-teacher/", {
            "email": "unauth@reg.test",
            "first_name": "Un",
            "last_name": "Auth",
            "password": "StrongPass123!",
        })
        self.assertEqual(resp.status_code, 401)

    def test_register_duplicate_email_returns_400(self):
        self._auth_admin()
        resp = self._post("/api/users/auth/register-teacher/", {
            "email": "teacher@reg.test",  # Already exists
            "first_name": "Dup",
            "last_name": "Email",
            "password": "StrongPass123!",
        })
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# Password reset request
# ---------------------------------------------------------------------------


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class PasswordResetRequestTestCase(TestCase):
    """Tests for POST /api/users/auth/request-password-reset/."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Reset School",
            slug="reset-school",
            subdomain="test",
            email="reset@test.com",
            is_active=True,
        )
        self.user = User.objects.create_user(
            email="user@reset.test",
            password="oldpass123",
            first_name="Reset",
            last_name="User",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )

    def _post(self, url, data=None, **kw):
        return self.client.post(url, data, format="json", HTTP_HOST=HOST, **kw)

    def test_request_reset_existing_email_returns_200(self):
        resp = self._post("/api/users/auth/request-password-reset/", {
            "email": "user@reset.test",
        })
        self.assertEqual(resp.status_code, 200)

    def test_request_reset_nonexistent_email_still_returns_200(self):
        """Should never reveal whether the email exists."""
        resp = self._post("/api/users/auth/request-password-reset/", {
            "email": "nonexistent@reset.test",
        })
        self.assertEqual(resp.status_code, 200)

    def test_request_reset_missing_email_returns_400(self):
        resp = self._post("/api/users/auth/request-password-reset/", {})
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# Confirm password reset edge cases
# ---------------------------------------------------------------------------


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class ConfirmPasswordResetEdgeCaseTestCase(TestCase):
    """Tests for POST /api/users/auth/confirm-password-reset/ edge cases."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Confirm School",
            slug="confirm-school",
            subdomain="test",
            email="confirm@test.com",
            is_active=True,
        )
        self.user = User.objects.create_user(
            email="user@confirm.test",
            password="oldpass123",
            first_name="Confirm",
            last_name="User",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )

    def _post(self, url, data=None, **kw):
        return self.client.post(url, data, format="json", HTTP_HOST=HOST, **kw)

    def test_missing_fields_returns_400(self):
        resp = self._post("/api/users/auth/confirm-password-reset/", {})
        self.assertEqual(resp.status_code, 400)

    def test_invalid_uid_returns_400(self):
        resp = self._post("/api/users/auth/confirm-password-reset/", {
            "uid": "baduid",
            "token": "badtoken",
            "new_password": "NewPass123!",
        })
        self.assertEqual(resp.status_code, 400)

    def test_invalid_token_returns_400(self):
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        resp = self._post("/api/users/auth/confirm-password-reset/", {
            "uid": uid,
            "token": "invalid-token-value",
            "new_password": "NewPass123!",
        })
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# Notification preferences
# ---------------------------------------------------------------------------


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class PreferencesTestCase(TestCase):
    """Tests for GET/PATCH /api/users/auth/preferences/."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Prefs School",
            slug="prefs-school",
            subdomain="test",
            email="prefs@test.com",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@prefs.test",
            password="prefs123",
            first_name="Prefs",
            last_name="Teacher",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )
        self.client.force_authenticate(user=self.teacher)

    def _get(self, url, **kw):
        return self.client.get(url, HTTP_HOST=HOST, **kw)

    def _patch(self, url, data=None, **kw):
        return self.client.patch(url, data, format="json", HTTP_HOST=HOST, **kw)

    def test_get_preferences_returns_200(self):
        resp = self._get("/api/users/auth/preferences/")
        self.assertEqual(resp.status_code, 200)

    def test_patch_preferences_updates_boolean(self):
        resp = self._patch("/api/users/auth/preferences/", {
            "email_courses": False,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["email_courses"])

    def test_patch_preferences_updates_editor_mode(self):
        resp = self._patch("/api/users/auth/preferences/", {
            "content_editor_mode": "MARKDOWN",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["content_editor_mode"], "MARKDOWN")

    def test_patch_preferences_ignores_unknown_keys(self):
        resp = self._patch("/api/users/auth/preferences/", {
            "unknown_key": True,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("unknown_key", resp.json())

    def test_unauthenticated_preferences_returns_401(self):
        self.client.force_authenticate(user=None)
        resp = self._get("/api/users/auth/preferences/")
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# Me endpoint PATCH (profile update)
# ---------------------------------------------------------------------------


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class MeEndpointPatchTestCase(TestCase):
    """Tests for PATCH /api/users/auth/me/."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Me School",
            slug="me-school",
            subdomain="test",
            email="me@test.com",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@me.test",
            password="me12345",
            first_name="Old",
            last_name="Name",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )
        self.client.force_authenticate(user=self.teacher)

    def _patch(self, url, data=None, **kw):
        return self.client.patch(url, data, format="json", HTTP_HOST=HOST, **kw)

    def test_patch_first_name(self):
        resp = self._patch("/api/users/auth/me/", {"first_name": "New"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["first_name"], "New")

    def test_patch_last_name(self):
        resp = self._patch("/api/users/auth/me/", {"last_name": "Updated"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["last_name"], "Updated")

    def test_patch_department(self):
        resp = self._patch("/api/users/auth/me/", {"department": "Science"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["department"], "Science")

    def test_patch_bio(self):
        resp = self._patch("/api/users/auth/me/", {"bio": "A short bio."})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["bio"], "A short bio.")

    def test_patch_disallowed_field_ignored(self):
        """Fields not in the allowed list should not be updated."""
        resp = self._patch("/api/users/auth/me/", {"role": "SUPER_ADMIN"})
        self.assertEqual(resp.status_code, 200)
        # Role should remain TEACHER
        self.assertEqual(resp.json()["role"], "TEACHER")

    def test_unauthenticated_me_patch_returns_401(self):
        self.client.force_authenticate(user=None)
        resp = self._patch("/api/users/auth/me/", {"first_name": "Hacker"})
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# Logout edge cases
# ---------------------------------------------------------------------------


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class LogoutEdgeCaseTestCase(TestCase):
    """Tests for POST /api/users/auth/logout/ edge cases."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Logout School",
            slug="logout-school",
            subdomain="test",
            email="logout@test.com",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@logout.test",
            password="logout123",
            first_name="Logout",
            last_name="Teacher",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )

    def _login(self):
        resp = self.client.post("/api/users/auth/login/", {
            "email": "teacher@logout.test",
            "password": "logout123",
        }, format="json", HTTP_HOST=HOST)
        tokens = resp.json()["tokens"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        return tokens

    def test_logout_without_refresh_token_returns_400(self):
        self._login()
        resp = self.client.post("/api/users/auth/logout/", {}, format="json", HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 400)

    def test_logout_with_invalid_refresh_token_returns_400(self):
        self._login()
        resp = self.client.post(
            "/api/users/auth/logout/",
            {"refresh_token": "invalid-token"},
            format="json",
            HTTP_HOST=HOST,
        )
        self.assertEqual(resp.status_code, 400)

    def test_logout_unauthenticated_returns_401(self):
        resp = self.client.post("/api/users/auth/logout/", {}, format="json", HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class EmailVerificationTestCase(TestCase):
    """Tests for POST /api/users/auth/verify-email/."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Verify School",
            slug="verify-school",
            subdomain="test",
            email="verify@test.com",
            is_active=True,
        )
        self.user = User.objects.create_user(
            email="user@verify.test",
            password="verify123",
            first_name="Verify",
            last_name="User",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )

    def _post(self, url, data=None, **kw):
        return self.client.post(url, data, format="json", HTTP_HOST=HOST, **kw)

    def test_verify_email_missing_fields_returns_400(self):
        resp = self._post("/api/users/auth/verify-email/", {})
        self.assertEqual(resp.status_code, 400)

    def test_verify_email_invalid_uid_returns_400(self):
        resp = self._post("/api/users/auth/verify-email/", {
            "uid": "invalid",
            "token": "invalid",
        })
        self.assertEqual(resp.status_code, 400)

    def test_verify_email_valid_token(self):
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        from utils.email_verification import email_verification_token

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = email_verification_token.make_token(self.user)

        resp = self._post("/api/users/auth/verify-email/", {
            "uid": uid,
            "token": token,
        })
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)

    def test_verify_email_already_verified_returns_200(self):
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        from utils.email_verification import email_verification_token

        self.user.email_verified = True
        self.user.save(update_fields=["email_verified"])

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = email_verification_token.make_token(self.user)

        resp = self._post("/api/users/auth/verify-email/", {
            "uid": uid,
            "token": token,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn("already verified", resp.json()["message"].lower())


# ---------------------------------------------------------------------------
# Must-change-password flag
# ---------------------------------------------------------------------------


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class MustChangePasswordTestCase(TestCase):
    """Tests for login behavior when must_change_password is set."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="MustChange School",
            slug="must-change-school",
            subdomain="test",
            email="mc@test.com",
            is_active=True,
        )
        self.user = User.objects.create_user(
            email="user@mc.test",
            password="temppass123",
            first_name="Must",
            last_name="Change",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )
        self.user.must_change_password = True
        self.user.save(update_fields=["must_change_password"])

    def test_login_with_must_change_password_includes_flag(self):
        resp = self.client.post("/api/users/auth/login/", {
            "email": "user@mc.test",
            "password": "temppass123",
        }, format="json", HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("must_change_password"))
        self.assertIn("tokens", data)

    def test_change_password_clears_flag(self):
        # Login first
        login_resp = self.client.post("/api/users/auth/login/", {
            "email": "user@mc.test",
            "password": "temppass123",
        }, format="json", HTTP_HOST=HOST)
        token = login_resp.json()["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        # Change password
        resp = self.client.post("/api/users/auth/change-password/", {
            "old_password": "temppass123",
            "new_password": "NewSecure456!",
            "new_password_confirm": "NewSecure456!",
        }, format="json", HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)

        # Verify flag is cleared
        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)


# ---------------------------------------------------------------------------
# Login failure cases
# ---------------------------------------------------------------------------


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class LoginFailureTestCase(TestCase):
    """Tests for POST /api/users/auth/login/ — failure scenarios."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Login Fail School",
            slug="login-fail-school",
            subdomain="test",
            email="loginfail@test.com",
            is_active=True,
        )
        self.user = User.objects.create_user(
            email="user@loginfail.test",
            password="correct123",
            first_name="Login",
            last_name="Fail",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )

    def _post(self, url, data=None, **kw):
        return self.client.post(url, data, format="json", HTTP_HOST=HOST, **kw)

    def test_login_wrong_password_returns_400(self):
        """Submitting a wrong password should return 400 (serializer validation error)."""
        resp = self._post("/api/users/auth/login/", {
            "email": "user@loginfail.test",
            "password": "wrongpassword",
        })
        self.assertIn(resp.status_code, (400, 401))

    def test_login_nonexistent_email_returns_400(self):
        resp = self._post("/api/users/auth/login/", {
            "email": "nobody@loginfail.test",
            "password": "anything123",
        })
        self.assertIn(resp.status_code, (400, 401))

    def test_login_inactive_user_returns_400(self):
        """An inactive user should not be able to log in."""
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        resp = self._post("/api/users/auth/login/", {
            "email": "user@loginfail.test",
            "password": "correct123",
        })
        self.assertIn(resp.status_code, (400, 401))

    def test_login_missing_password_returns_400(self):
        resp = self._post("/api/users/auth/login/", {
            "email": "user@loginfail.test",
        })
        self.assertEqual(resp.status_code, 400)

    def test_login_missing_email_returns_400(self):
        resp = self._post("/api/users/auth/login/", {
            "password": "correct123",
        })
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# Change password failure cases
# ---------------------------------------------------------------------------


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class ChangePasswordFailureTestCase(TestCase):
    """Tests for POST /api/users/auth/change-password/ — failure scenarios."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="ChgPwd School",
            slug="chgpwd-school",
            subdomain="test",
            email="chgpwd@test.com",
            is_active=True,
        )
        self.user = User.objects.create_user(
            email="user@chgpwd.test",
            password="OldPassword123!",
            first_name="Change",
            last_name="Pwd",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )
        self.client.force_authenticate(user=self.user)

    def _post(self, url, data=None, **kw):
        return self.client.post(url, data, format="json", HTTP_HOST=HOST, **kw)

    def test_wrong_old_password_returns_400(self):
        """Supplying incorrect old_password should fail validation."""
        resp = self._post("/api/users/auth/change-password/", {
            "old_password": "WrongOldPass!",
            "new_password": "NewSecure456!",
            "new_password_confirm": "NewSecure456!",
        })
        self.assertEqual(resp.status_code, 400)

    def test_mismatched_new_passwords_returns_400(self):
        """new_password and new_password_confirm must match."""
        resp = self._post("/api/users/auth/change-password/", {
            "old_password": "OldPassword123!",
            "new_password": "NewSecure456!",
            "new_password_confirm": "DifferentPass789!",
        })
        self.assertEqual(resp.status_code, 400)

    def test_missing_old_password_returns_400(self):
        resp = self._post("/api/users/auth/change-password/", {
            "new_password": "NewSecure456!",
            "new_password_confirm": "NewSecure456!",
        })
        self.assertEqual(resp.status_code, 400)

    def test_unauthenticated_change_password_returns_401(self):
        self.client.force_authenticate(user=None)
        resp = self._post("/api/users/auth/change-password/", {
            "old_password": "OldPassword123!",
            "new_password": "NewSecure456!",
            "new_password_confirm": "NewSecure456!",
        })
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# Me endpoint GET
# ---------------------------------------------------------------------------


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class MeEndpointGetTestCase(TestCase):
    """Tests for GET /api/users/auth/me/."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="MeGet School",
            slug="meget-school",
            subdomain="test",
            email="meget@test.com",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@meget.test",
            password="meget123",
            first_name="FirstGet",
            last_name="LastGet",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )

    def _get(self, url, **kw):
        return self.client.get(url, HTTP_HOST=HOST, **kw)

    def test_get_me_returns_user_data(self):
        self.client.force_authenticate(user=self.teacher)
        resp = self._get("/api/users/auth/me/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["email"], "teacher@meget.test")
        self.assertEqual(data["first_name"], "FirstGet")
        self.assertEqual(data["last_name"], "LastGet")
        self.assertEqual(data["role"], "TEACHER")

    def test_get_me_includes_expected_fields(self):
        self.client.force_authenticate(user=self.teacher)
        resp = self._get("/api/users/auth/me/")
        data = resp.json()
        for field in ("id", "email", "first_name", "last_name", "role", "is_active"):
            self.assertIn(field, data, msg=f"Missing field: {field}")

    def test_get_me_unauthenticated_returns_401(self):
        resp = self._get("/api/users/auth/me/")
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# Logout happy path
# ---------------------------------------------------------------------------


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class LogoutHappyPathTestCase(TestCase):
    """Tests for POST /api/users/auth/logout/ — success scenario."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="LogoutOK School",
            slug="logoutok-school",
            subdomain="test",
            email="logoutok@test.com",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@logoutok.test",
            password="logoutok123",
            first_name="Logout",
            last_name="OK",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )

    def _login(self):
        resp = self.client.post("/api/users/auth/login/", {
            "email": "teacher@logoutok.test",
            "password": "logoutok123",
        }, format="json", HTTP_HOST=HOST)
        tokens = resp.json()["tokens"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        return tokens

    def test_logout_with_valid_refresh_token_returns_200(self):
        tokens = self._login()
        resp = self.client.post(
            "/api/users/auth/logout/",
            {"refresh_token": tokens["refresh"]},
            format="json",
            HTTP_HOST=HOST,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("message", resp.json())

    def test_logout_blacklists_refresh_token(self):
        """After logout, the same refresh token should not produce a new access token."""
        tokens = self._login()
        # Logout
        self.client.post(
            "/api/users/auth/logout/",
            {"refresh_token": tokens["refresh"]},
            format="json",
            HTTP_HOST=HOST,
        )
        # Attempt to use the now-blacklisted refresh token
        resp = self.client.post(
            "/api/users/auth/refresh/",
            {"refresh_token": tokens["refresh"]},
            format="json",
            HTTP_HOST=HOST,
        )
        self.assertIn(resp.status_code, (400, 401))


# ---------------------------------------------------------------------------
# Refresh token endpoint
# ---------------------------------------------------------------------------


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class RefreshTokenTestCase(TestCase):
    """Tests for POST /api/users/auth/refresh/."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Refresh School",
            slug="refresh-school",
            subdomain="test",
            email="refresh@test.com",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@refresh.test",
            password="refresh123",
            first_name="Refresh",
            last_name="Teacher",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )

    def _post(self, url, data=None, **kw):
        return self.client.post(url, data, format="json", HTTP_HOST=HOST, **kw)

    def _login(self):
        resp = self._post("/api/users/auth/login/", {
            "email": "teacher@refresh.test",
            "password": "refresh123",
        })
        return resp.json()["tokens"]

    def test_refresh_with_valid_token_returns_new_access(self):
        tokens = self._login()
        resp = self._post("/api/users/auth/refresh/", {
            "refresh_token": tokens["refresh"],
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.json())
        # New access token should be a non-empty string
        self.assertTrue(len(resp.json()["access"]) > 0)

    def test_refresh_without_token_returns_400(self):
        resp = self._post("/api/users/auth/refresh/", {})
        self.assertEqual(resp.status_code, 400)

    def test_refresh_with_invalid_token_returns_401(self):
        resp = self._post("/api/users/auth/refresh/", {
            "refresh_token": "this-is-not-a-valid-jwt",
        })
        self.assertEqual(resp.status_code, 401)

    def test_refresh_with_blacklisted_token_returns_401(self):
        """A refresh token that was blacklisted (via logout) should be rejected."""
        tokens = self._login()
        # Blacklist via logout
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        self.client.post(
            "/api/users/auth/logout/",
            {"refresh_token": tokens["refresh"]},
            format="json",
            HTTP_HOST=HOST,
        )
        self.client.credentials()  # Clear auth header
        # Try refresh
        resp = self._post("/api/users/auth/refresh/", {
            "refresh_token": tokens["refresh"],
        })
        self.assertIn(resp.status_code, (400, 401))
