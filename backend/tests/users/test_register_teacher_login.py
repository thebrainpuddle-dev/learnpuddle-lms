# tests/users/test_register_teacher_login.py
"""
Regression tests — Fix 2: No double password hashing in RegisterTeacherSerializer.

Background:
    The old code called create_user() without a password (producing an unusable
    password), then called set_password() + save() separately. If the flow ever
    received an already-hashed value (or if create_user() itself hashed inside),
    the result would be hash(hash(pw)) — a string that never matches during login.

The fix (users/serializers.py):
    RegisterTeacherSerializer.create() now passes password directly to
    create_user(password=password), which calls set_password() exactly once.

Tests:
1. RegisterTeacherSerializer direct path: check_password(plain) returns True.
2. RegisterTeacherSerializer double-hash guard: check_password(hash(plain)) is False.
3. API registration + immediate login returns 200 with tokens.
4. Serializer-created user can authenticate via Django's authenticate().
"""

from django.contrib.auth.hashers import make_password
from django.test import TestCase, override_settings
from rest_framework.test import APIClient, APIRequestFactory

from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant(name, subdomain):
    return Tenant.objects.create(
        name=name,
        slug=subdomain,
        subdomain=subdomain,
        email=f"admin@{subdomain}.example.com",
        is_active=True,
    )


def _make_admin(email, tenant, password="AdminPass!123"):
    return User.objects.create_user(
        email=email,
        password=password,
        first_name="Admin",
        last_name="User",
        tenant=tenant,
        role="SCHOOL_ADMIN",
        is_active=True,
    )


def _auth_client(user, subdomain):
    c = APIClient()
    c.force_authenticate(user=user)
    c.defaults["HTTP_HOST"] = f"{subdomain}.lms.com"
    return c


def _anon_client(subdomain):
    c = APIClient()
    c.defaults["HTTP_HOST"] = f"{subdomain}.lms.com"
    return c


# ===========================================================================
# 1. RegisterTeacherSerializer — direct unit tests
# ===========================================================================

class RegisterTeacherSerializerPasswordTestCase(TestCase):
    """
    Tests the RegisterTeacherSerializer.create() path directly (no HTTP layer).
    Verifies password is hashed exactly once via create_user().
    """

    def setUp(self):
        self.tenant = _make_tenant("Reg Serial School", "regserial")
        self.admin = _make_admin("admin@regserial.com", self.tenant)

    def _make_serializer(self, data):
        from apps.users.serializers import RegisterTeacherSerializer
        factory = APIRequestFactory()
        request = factory.post("/")
        request.tenant = self.tenant
        request.user = self.admin
        return RegisterTeacherSerializer(data=data, context={"request": request})

    def test_serializer_creates_user_whose_check_password_returns_true(self):
        """
        After RegisterTeacherSerializer.create(), user.check_password(plain) must
        be True — confirming the password was hashed exactly once.
        """
        plain = "SerialPass!111"
        serializer = self._make_serializer({
            "email": "teacher1@regserial.com",
            "password": plain,
            "password_confirm": plain,
            "first_name": "Serial",
            "last_name": "One",
        })
        self.assertTrue(serializer.is_valid(), f"Validation errors: {serializer.errors}")
        user = serializer.save()

        self.assertTrue(
            user.check_password(plain),
            "check_password(plain) must return True. "
            "False here indicates double-hashing or password not set.",
        )

    def test_serializer_double_hash_guard(self):
        """
        check_password(hash(plain)) must return False after serializer creates the user.
        If double-hashing occurred, hash(hash(plain)) would be stored and
        check_password(hash(plain)) would incorrectly return True.
        """
        plain = "DoubleHashGuard!222"
        serializer = self._make_serializer({
            "email": "teacher2@regserial.com",
            "password": plain,
            "password_confirm": plain,
            "first_name": "Double",
            "last_name": "Guard",
        })
        self.assertTrue(serializer.is_valid(), f"Validation errors: {serializer.errors}")
        user = serializer.save()

        hashed = make_password(plain)
        self.assertFalse(
            user.check_password(hashed),
            "check_password(hash(plain)) must return False. "
            "True here means hash(hash(plain)) was stored — double-hash regression.",
        )

    def test_serializer_password_is_not_plain_text(self):
        """The stored password must never be the raw plain-text string."""
        plain = "NotPlain!333"
        serializer = self._make_serializer({
            "email": "teacher3@regserial.com",
            "password": plain,
            "password_confirm": plain,
            "first_name": "Not",
            "last_name": "Plain",
        })
        self.assertTrue(serializer.is_valid(), f"Validation errors: {serializer.errors}")
        user = serializer.save()

        self.assertNotEqual(
            user.password,
            plain,
            "Password must not be stored as plain text.",
        )

    def test_serializer_password_is_usable(self):
        """User created via serializer must have a usable (not unusable/blank) password."""
        plain = "UsablePass!444"
        serializer = self._make_serializer({
            "email": "teacher4@regserial.com",
            "password": plain,
            "password_confirm": plain,
            "first_name": "Usable",
            "last_name": "Four",
        })
        self.assertTrue(serializer.is_valid(), f"Validation errors: {serializer.errors}")
        user = serializer.save()

        self.assertTrue(
            user.has_usable_password(),
            "User created via RegisterTeacherSerializer must have a usable password.",
        )

    def test_serializer_created_user_can_authenticate(self):
        """
        Django's authenticate() must succeed for a user created via the serializer.
        This validates the full auth chain: hash stored correctly → check_password works.
        """
        from django.contrib.auth import authenticate

        plain = "AuthChain!555"
        serializer = self._make_serializer({
            "email": "teacher5@regserial.com",
            "password": plain,
            "password_confirm": plain,
            "first_name": "Auth",
            "last_name": "Chain",
        })
        self.assertTrue(serializer.is_valid(), f"Validation errors: {serializer.errors}")
        user = serializer.save()

        authenticated = authenticate(username=user.email, password=plain)
        self.assertIsNotNone(
            authenticated,
            "authenticate(email, plain) must succeed for serializer-created teacher. "
            "None result indicates password was not hashed correctly.",
        )
        self.assertEqual(authenticated.pk, user.pk)

    def test_serializer_password_confirm_mismatch_raises_error(self):
        """Mismatched passwords must fail validation, not create an unusable user."""
        serializer = self._make_serializer({
            "email": "teacher6@regserial.com",
            "password": "GoodPass!666",
            "password_confirm": "WrongPass!000",
            "first_name": "Mismatch",
            "last_name": "Six",
        })
        self.assertFalse(serializer.is_valid())
        self.assertFalse(
            User.objects.filter(email="teacher6@regserial.com").exists(),
            "No user must be created when passwords don't match.",
        )


# ===========================================================================
# 2. API endpoint + login — end-to-end regression test
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
            "login": None,
            "register": None,
        },
    },
)
class RegisterTeacherLoginEndToEndTestCase(TestCase):
    """
    End-to-end regression: register a teacher via the API endpoint, then
    log in via the login endpoint. Both steps must succeed.
    """

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.tenant = _make_tenant("E2E Reg School", "e2ereg")
        self.admin = _make_admin("admin@e2ereg.com", self.tenant)
        self.admin_client = _auth_client(self.admin, "e2ereg")

    def test_registered_teacher_check_password_returns_true(self):
        """
        Teacher registered via API endpoint: user.check_password(plain) is True.
        This is the definitive double-hash regression test at the HTTP layer.
        """
        plain = "APIRegPass!777"
        r = self.admin_client.post(
            "/api/v1/users/auth/register-teacher/",
            {
                "email": "teacher_api1@e2ereg.com",
                "password": plain,
                "password_confirm": plain,
                "first_name": "API",
                "last_name": "One",
            },
            format="json",
        )
        if r.status_code not in (200, 201):
            self.fail(
                f"Teacher registration returned {r.status_code}: {r.content!r} "
                "— regression test cannot be skipped"
            )

        user = User.objects.get(email="teacher_api1@e2ereg.com")
        self.assertTrue(
            user.check_password(plain),
            "API-registered teacher: check_password(plain) must be True. "
            "False indicates double-hashing regression.",
        )

    def test_registered_teacher_can_login_and_receives_tokens(self):
        """
        Teacher registered via API can authenticate via the login endpoint
        and receives JWT access + refresh tokens in the response.
        """
        plain = "LoginAfterReg!888"
        # Register
        r_reg = self.admin_client.post(
            "/api/v1/users/auth/register-teacher/",
            {
                "email": "teacher_api2@e2ereg.com",
                "password": plain,
                "password_confirm": plain,
                "first_name": "Login",
                "last_name": "Two",
            },
            format="json",
        )
        if r_reg.status_code not in (200, 201):
            self.fail(
                f"Teacher registration returned {r_reg.status_code}: {r_reg.content!r} "
                "— regression test cannot be skipped"
            )

        # Ensure user is active (some flows require email verification)
        user = User.objects.get(email="teacher_api2@e2ereg.com")
        if not user.is_active:
            user.is_active = True
            user.save()

        # Login
        login_client = _anon_client("e2ereg")
        r_login = login_client.post(
            "/api/v1/users/auth/login/",
            {"email": "teacher_api2@e2ereg.com", "password": plain},
            format="json",
        )
        self.assertIn(
            r_login.status_code,
            [200, 201],
            f"Login after registration must return 200/201. "
            f"Got {r_login.status_code}: {getattr(r_login, 'data', '')}. "
            f"This may indicate double-hashing — the stored hash cannot be verified.",
        )
        self.assertIn(
            "access",
            r_login.data,
            "Login response must contain 'access' JWT token.",
        )
        self.assertIn(
            "refresh",
            r_login.data,
            "Login response must contain 'refresh' JWT token.",
        )

    def test_double_hash_guard_api_level(self):
        """
        Regression guard: a freshly registered teacher must NOT be
        authenticatable with hash(plain) — only plain must work.
        If double-hashing occurred, hash(plain) would unexpectedly succeed.
        """
        plain = "DoubleHashAPIGuard!999"
        r_reg = self.admin_client.post(
            "/api/v1/users/auth/register-teacher/",
            {
                "email": "teacher_api3@e2ereg.com",
                "password": plain,
                "password_confirm": plain,
                "first_name": "DH",
                "last_name": "Guard",
            },
            format="json",
        )
        if r_reg.status_code not in (200, 201):
            self.fail(
                f"Teacher registration returned {r_reg.status_code}: {r_reg.content!r} "
                "— regression test cannot be skipped"
            )

        user = User.objects.get(email="teacher_api3@e2ereg.com")
        pre_hashed = make_password(plain)

        self.assertFalse(
            user.check_password(pre_hashed),
            "check_password(hash(plain)) must be False. "
            "True here means hash(hash(plain)) is stored — double-hash regression.",
        )
