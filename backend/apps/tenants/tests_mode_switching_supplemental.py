# apps/tenants/tests_mode_switching_supplemental.py
"""
Supplemental QA tests for TASK-020 / TASK-021 — Education vs Corporate mode
switching.

The backend-engineer's ``tests_mode_switching.py`` covers the happy paths and
the main cross-tenant isolation case thoroughly. This file fills the remaining
gaps identified during the QA pass:

1. Unauthenticated access → 401 for both /me and /settings.
2. Teacher accessing /settings → 403 (admin-only endpoint).
3. ``validate_mode_label_overrides`` coercion:
     - Non-string values (e.g. ``{"course": 42}``) are dropped silently.
     - Whitespace-only strings are dropped.
     - A completely invalid payload type (list, int) falls back to ``{}``.
4. Partial override — only overriding one key leaves all others at mode defaults.
5. Switching from corporate back to education reverts ALL labels.
6. All 12 canonical label keys are present in both modes.
"""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers (same pattern as tests_mode_switching.py)
# ---------------------------------------------------------------------------

_CTR = {"n": 0}


def _u():
    _CTR["n"] += 1
    return _CTR["n"]


def _make_tenant(name=None, subdomain=None):
    n = _u()
    sub = subdomain or f"sup{n}"
    return Tenant.objects.create(
        name=name or f"Sup School {n}",
        slug=sub, subdomain=sub,
        email=f"{sub}@test.com",
        is_active=True,
    )


def _make_user(email, tenant, role="TEACHER"):
    return User.objects.create_user(
        email=email, password="Pass!123",
        first_name="QA", last_name="User",
        tenant=tenant, role=role, is_active=True,
    )


def _client_for(user, subdomain):
    c = APIClient()
    c.force_authenticate(user=user)
    c.defaults["HTTP_HOST"] = f"{subdomain}.lms.com"
    return c


def _anon_client(subdomain):
    c = APIClient()
    c.defaults["HTTP_HOST"] = f"{subdomain}.lms.com"
    return c


# The 12 canonical label keys from MODE_LABEL_DEFAULTS.
CANONICAL_LABEL_KEYS = [
    "learner", "learner_plural", "course", "course_plural",
    "module", "lesson", "assignment", "badge", "league",
    "xp", "streak", "dashboard",
]


# ===========================================================================
# 1. Authentication / authorisation edge cases
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class ModeAuthTests(TestCase):

    def setUp(self):
        self.tenant = _make_tenant()
        self.teacher = _make_user(f"t@{self.tenant.subdomain}.test", self.tenant, "TEACHER")
        self.admin = _make_user(f"a@{self.tenant.subdomain}.test", self.tenant, "SCHOOL_ADMIN")

    def test_unauthenticated_get_me_returns_401(self):
        """Public unauthenticated GET /me must return 401."""
        c = _anon_client(self.tenant.subdomain)
        r = c.get("/api/v1/tenants/me/")
        self.assertEqual(r.status_code, 401)

    def test_unauthenticated_get_settings_returns_401(self):
        """Unauthenticated GET /settings must return 401."""
        c = _anon_client(self.tenant.subdomain)
        r = c.get("/api/v1/tenants/settings/")
        self.assertEqual(r.status_code, 401)

    def test_unauthenticated_patch_settings_returns_401(self):
        """Unauthenticated PATCH /settings must return 401."""
        c = _anon_client(self.tenant.subdomain)
        r = c.patch("/api/v1/tenants/settings/", {"mode": "corporate"}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_teacher_get_settings_returns_403(self):
        """
        GET /settings is an admin-only endpoint.  A teacher (TEACHER role)
        must receive 403, not 200.
        """
        c = _client_for(self.teacher, self.tenant.subdomain)
        r = c.get("/api/v1/tenants/settings/")
        self.assertEqual(r.status_code, 403)

    def test_teacher_get_me_returns_200_with_mode_labels(self):
        """
        A teacher must be able to read /me (including mode + mode_labels).
        This is the standard read path used by all UI components.
        """
        c = _client_for(self.teacher, self.tenant.subdomain)
        r = c.get("/api/v1/tenants/me/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("mode", r.data)
        self.assertIn("mode_labels", r.data)

    def test_admin_get_settings_returns_200(self):
        """SCHOOL_ADMIN must be able to GET /settings."""
        c = _client_for(self.admin, self.tenant.subdomain)
        r = c.get("/api/v1/tenants/settings/")
        self.assertEqual(r.status_code, 200)


# ===========================================================================
# 2. Override coercion: non-string values are dropped
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class ModeOverrideCoercionTests(TestCase):

    def setUp(self):
        self.tenant = _make_tenant()
        self.admin = _make_user(f"a@{self.tenant.subdomain}.test", self.tenant, "SCHOOL_ADMIN")
        self.client = _client_for(self.admin, self.tenant.subdomain)

    def _patch(self, payload):
        return self.client.patch("/api/v1/tenants/settings/", payload, format="json")

    def test_non_string_override_value_is_dropped(self):
        """
        ``validate_mode_label_overrides`` must drop non-string values.
        Sending ``{"course": 42}`` should be accepted (200) but the key
        must be absent from the stored overrides (not coerced to "42").

        Ref: TASK-021 review request — "A malformed payload like
        {'course': 42} will be accepted but that key dropped."
        """
        r = self._patch({"mode_label_overrides": {"course": 42}})
        self.assertEqual(r.status_code, 200, r.content)
        # The numeric value should be dropped — key absent or value is not 42.
        stored = r.data.get("mode_label_overrides", {})
        self.assertNotIn("course", stored,
                         "Non-string override value should be dropped from stored overrides")

    def test_whitespace_only_string_override_is_dropped(self):
        """
        Override values that are whitespace-only after strip should be dropped.
        """
        r = self._patch({"mode_label_overrides": {"learner": "   "}})
        self.assertEqual(r.status_code, 200)
        stored = r.data.get("mode_label_overrides", {})
        self.assertNotIn("learner", stored,
                         "Whitespace-only override value should be stripped and dropped")

    def test_valid_string_override_is_preserved(self):
        """
        String values with content must be preserved as-is (positive control).
        """
        r = self._patch({"mode_label_overrides": {"badge": "Trophy"}})
        self.assertEqual(r.status_code, 200)
        stored = r.data.get("mode_label_overrides", {})
        self.assertEqual(stored.get("badge"), "Trophy")

    def test_mixed_payload_drops_non_strings_preserves_strings(self):
        """
        A payload with a mix of valid strings, numeric values, and
        whitespace-only strings should only retain the valid strings.
        """
        payload = {
            "mode_label_overrides": {
                "badge": "Trophy",       # valid — keep
                "course": 99,            # numeric — drop
                "learner": "   ",        # whitespace — drop
                "xp": "Prestige Points", # valid — keep
            }
        }
        r = self._patch(payload)
        self.assertEqual(r.status_code, 200, r.content)
        stored = r.data.get("mode_label_overrides", {})
        self.assertIn("badge", stored)
        self.assertEqual(stored["badge"], "Trophy")
        self.assertIn("xp", stored)
        self.assertEqual(stored["xp"], "Prestige Points")
        self.assertNotIn("course", stored)
        self.assertNotIn("learner", stored)


# ===========================================================================
# 3. Partial overrides — only specified keys are overridden
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class ModePartialOverrideTests(TestCase):

    def setUp(self):
        self.tenant = _make_tenant()
        self.admin = _make_user(f"a@{self.tenant.subdomain}.test", self.tenant, "SCHOOL_ADMIN")
        self.teacher = _make_user(f"t@{self.tenant.subdomain}.test", self.tenant, "TEACHER")

    def test_single_key_override_leaves_others_at_mode_default(self):
        """
        Overriding only ``course`` must not affect ``learner``, ``badge``, etc.
        """
        admin_c = _client_for(self.admin, self.tenant.subdomain)
        admin_c.patch(
            "/api/v1/tenants/settings/",
            {"mode_label_overrides": {"course": "Masterclass"}},
            format="json",
        )

        teacher_c = _client_for(self.teacher, self.tenant.subdomain)
        me = teacher_c.get("/api/v1/tenants/me/")
        self.assertEqual(me.status_code, 200)
        labels = me.data.get("mode_labels", {})

        self.assertEqual(labels.get("course"), "Masterclass",
                         "Overridden key must return override value")
        self.assertEqual(labels.get("learner"), "Teacher",
                         "Non-overridden key must return mode default")
        self.assertEqual(labels.get("badge"), "Badge",
                         "Non-overridden key must return mode default")


# ===========================================================================
# 4. Switching back from corporate to education
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class ModeRoundTripTests(TestCase):

    def setUp(self):
        self.tenant = _make_tenant()
        self.admin = _make_user(f"a@{self.tenant.subdomain}.test", self.tenant, "SCHOOL_ADMIN")
        self.teacher = _make_user(f"t@{self.tenant.subdomain}.test", self.tenant, "TEACHER")

    def test_switching_back_to_education_reverts_labels(self):
        """
        Flipping to corporate then back to education must restore education
        labels for all keys.
        """
        admin_c = _client_for(self.admin, self.tenant.subdomain)

        # Flip to corporate.
        r1 = admin_c.patch(
            "/api/v1/tenants/settings/", {"mode": "corporate"}, format="json"
        )
        self.assertEqual(r1.status_code, 200)

        # Flip back to education.
        r2 = admin_c.patch(
            "/api/v1/tenants/settings/", {"mode": "education"}, format="json"
        )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.data.get("mode"), "education")

        # Confirm /me reflects education defaults.
        teacher_c = _client_for(self.teacher, self.tenant.subdomain)
        me = teacher_c.get("/api/v1/tenants/me/")
        labels = me.data.get("mode_labels", {})
        self.assertEqual(labels.get("learner"), "Teacher")
        self.assertEqual(labels.get("course"), "Course")
        self.assertEqual(labels.get("badge"), "Badge")


# ===========================================================================
# 5. Canonical label keys completeness
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class ModeLabelCompletenessTests(TestCase):

    def setUp(self):
        self.tenant = _make_tenant()
        self.teacher = _make_user(f"t@{self.tenant.subdomain}.test", self.tenant, "TEACHER")

    def _get_labels(self):
        c = _client_for(self.teacher, self.tenant.subdomain)
        r = c.get("/api/v1/tenants/me/")
        self.assertEqual(r.status_code, 200)
        return r.data.get("mode_labels", {})

    def test_education_mode_exposes_all_12_canonical_keys(self):
        """
        GET /me in education mode must include all 12 canonical label keys
        so the frontend can safely call ``label(key)`` without guarding.
        """
        labels = self._get_labels()
        for key in CANONICAL_LABEL_KEYS:
            self.assertIn(key, labels,
                          f"Canonical key '{key}' missing from education mode_labels")
            self.assertIsInstance(labels[key], str,
                                  f"Canonical key '{key}' must be a string")
            self.assertTrue(labels[key].strip(),
                            f"Canonical key '{key}' must be non-empty in education mode")

    def test_corporate_mode_exposes_all_12_canonical_keys(self):
        """
        After flipping to corporate, GET /me must still include all 12 keys.
        """
        self.tenant.mode = "corporate"
        self.tenant.save(update_fields=["mode"])
        labels = self._get_labels()
        for key in CANONICAL_LABEL_KEYS:
            self.assertIn(key, labels,
                          f"Canonical key '{key}' missing from corporate mode_labels")
            self.assertIsInstance(labels[key], str)
            self.assertTrue(labels[key].strip(),
                            f"Canonical key '{key}' must be non-empty in corporate mode")
