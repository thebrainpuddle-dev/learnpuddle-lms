# apps/progress/tests_gamification_config_fields.py
"""
Tests for GamificationConfigSerializer field coverage.

Specifically verifies the BE-FOLLOWUPS-2026-04-20 requirement:
``GET /api/v1/gamification/admin/config/`` must expose the 7 new freeze/coin
config fields added in the follow-up serialiser patch:

  grace_period_hours, weekend_mode_available,
  freeze_token_earn_every_n_days, freeze_token_expires_days,
  freeze_token_max_inventory, coins_per_streak_milestone,
  coin_price_streak_freeze

Also verifies that an admin ``PATCH /api/v1/gamification/admin/config/update/``
round-trips each field correctly.
"""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.progress.gamification_engine import get_or_create_config
from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CTR = {"n": 0}


def _u():
    _CTR["n"] += 1
    return _CTR["n"]


def _make_tenant(name=None, subdomain=None):
    n = _u()
    sub = subdomain or f"cfgtst{n}"
    return Tenant.objects.create(
        name=name or f"Config School {n}",
        slug=sub, subdomain=sub,
        email=f"{sub}@test.com", is_active=True,
    )


def _make_user(email, tenant, role="SCHOOL_ADMIN"):
    return User.objects.create_user(
        email=email, password="Pass!123",
        first_name="Admin", last_name="User",
        tenant=tenant, role=role, is_active=True,
    )


def _admin_client(tenant, admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
    return client


# ---------------------------------------------------------------------------
# New fields that must be present in the config endpoint response
# ---------------------------------------------------------------------------

NEW_FREEZE_COIN_FIELDS = [
    # Streak-freeze token config (TASK-015)
    "grace_period_hours",
    "weekend_mode_available",
    "freeze_token_earn_every_n_days",
    "freeze_token_expires_days",
    "freeze_token_max_inventory",
    # Puddle Coin config (TASK-019)
    "coins_per_streak_milestone",
    "coin_price_streak_freeze",
]

# Core pre-existing fields that must remain present (non-regression)
CORE_FIELDS = [
    "id",
    "xp_per_content_completion",
    "xp_per_course_completion",
    "xp_per_assignment_submission",
    "xp_per_quiz_submission",
    "xp_per_streak_day",
    "streak_freeze_max",
    "leaderboard_enabled",
    "leaderboard_anonymize",
    "opt_out_allowed",
    "is_active",
    "created_at",
    "updated_at",
]


@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class GamificationConfigFieldsGetTest(TestCase):
    """
    GET /api/v1/gamification/admin/config/ must expose all new freeze/coin
    fields alongside the pre-existing core fields.
    """

    def setUp(self):
        self.tenant = _make_tenant()
        self.admin = _make_user(f"cfg-admin@{self.tenant.subdomain}.test", self.tenant)
        self.client = _admin_client(self.tenant, self.admin)
        # Ensure config row exists with defaults.
        self.config = get_or_create_config(self.tenant)

    def test_config_get_returns_200(self):
        resp = self.client.get("/api/v1/gamification/admin/config/")
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_config_get_includes_all_new_freeze_coin_fields(self):
        """Each of the 7 new fields must be present in the response."""
        resp = self.client.get("/api/v1/gamification/admin/config/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for field in NEW_FREEZE_COIN_FIELDS:
            self.assertIn(
                field, data,
                f"Missing field '{field}' in GET /admin/config/ response",
            )

    def test_config_get_includes_core_fields(self):
        """Pre-existing core fields must not have been dropped."""
        resp = self.client.get("/api/v1/gamification/admin/config/")
        data = resp.json()
        for field in CORE_FIELDS:
            self.assertIn(field, data, f"Core field '{field}' missing from config response")

    def test_config_get_new_field_default_values(self):
        """Verify the default values for the new fields match GamificationConfig defaults."""
        resp = self.client.get("/api/v1/gamification/admin/config/")
        data = resp.json()
        # Default coin_price_streak_freeze = 50 (from GamificationConfig definition)
        self.assertEqual(data["coin_price_streak_freeze"], 50)
        # Default freeze_token_max_inventory = 3
        self.assertEqual(data["freeze_token_max_inventory"], 3)
        # Default weekend_mode_available = False
        self.assertFalse(data["weekend_mode_available"])

    def test_config_get_requires_admin_role(self):
        """Non-admin (teacher) must be blocked with 403."""
        teacher = _make_user(
            f"t@{self.tenant.subdomain}.test", self.tenant, role="TEACHER"
        )
        teacher_client = _admin_client(self.tenant, teacher)
        resp = teacher_client.get("/api/v1/gamification/admin/config/")
        self.assertEqual(resp.status_code, 403)

    def test_config_get_requires_auth(self):
        """Unauthenticated request must be blocked with 401."""
        anon_client = APIClient()
        anon_client.defaults["HTTP_HOST"] = f"{self.tenant.subdomain}.lms.com"
        resp = anon_client.get("/api/v1/gamification/admin/config/")
        self.assertEqual(resp.status_code, 401)

    def test_config_get_cross_tenant_isolation(self):
        """An admin from tenant B must not read tenant A's config."""
        other_tenant = _make_tenant(subdomain=f"cfg-other{_u()}")
        other_admin = _make_user(
            f"oa@{other_tenant.subdomain}.test", other_tenant, role="SCHOOL_ADMIN"
        )
        cross_client = _admin_client(other_tenant, other_admin)
        # Hit tenant A's subdomain with tenant B's credentials → 403.
        cross_client.defaults["HTTP_HOST"] = f"{self.tenant.subdomain}.lms.com"
        resp = cross_client.get("/api/v1/gamification/admin/config/")
        self.assertEqual(resp.status_code, 403)


@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class GamificationConfigFieldsPatchTest(TestCase):
    """
    PATCH /api/v1/gamification/admin/config/update/ must round-trip each
    new freeze/coin field correctly.
    """

    def setUp(self):
        self.tenant = _make_tenant()
        self.admin = _make_user(f"patch-admin@{self.tenant.subdomain}.test", self.tenant)
        self.client = _admin_client(self.tenant, self.admin)
        self.config = get_or_create_config(self.tenant)

    def _patch(self, payload):
        return self.client.patch(
            "/api/v1/gamification/admin/config/update/",
            payload,
            format="json",
        )

    def test_patch_coin_price_streak_freeze(self):
        resp = self._patch({"coin_price_streak_freeze": 75})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["coin_price_streak_freeze"], 75)
        self.config.refresh_from_db()
        self.assertEqual(self.config.coin_price_streak_freeze, 75)

    def test_patch_freeze_token_max_inventory(self):
        resp = self._patch({"freeze_token_max_inventory": 5})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["freeze_token_max_inventory"], 5)
        self.config.refresh_from_db()
        self.assertEqual(self.config.freeze_token_max_inventory, 5)

    def test_patch_grace_period_hours(self):
        resp = self._patch({"grace_period_hours": 48})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["grace_period_hours"], 48)

    def test_patch_weekend_mode_available(self):
        resp = self._patch({"weekend_mode_available": True})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["weekend_mode_available"])

    def test_patch_freeze_token_earn_every_n_days(self):
        resp = self._patch({"freeze_token_earn_every_n_days": 14})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["freeze_token_earn_every_n_days"], 14)

    def test_patch_freeze_token_expires_days(self):
        resp = self._patch({"freeze_token_expires_days": 60})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["freeze_token_expires_days"], 60)

    def test_patch_coins_per_streak_milestone(self):
        resp = self._patch({"coins_per_streak_milestone": 20})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["coins_per_streak_milestone"], 20)

    def test_patch_multiple_new_fields_in_one_request(self):
        """All 7 new fields can be updated atomically in a single PATCH."""
        payload = {
            "grace_period_hours": 72,
            "weekend_mode_available": True,
            "freeze_token_earn_every_n_days": 21,
            "freeze_token_expires_days": 90,
            "freeze_token_max_inventory": 10,
            "coins_per_streak_milestone": 30,
            "coin_price_streak_freeze": 100,
        }
        resp = self._patch(payload)
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        for field, value in payload.items():
            self.assertEqual(
                data[field], value,
                f"Field '{field}' mismatch after PATCH: got {data[field]!r}",
            )

    def test_patch_partial_update_preserves_other_fields(self):
        """Patching one field must not reset unrelated fields."""
        # Set a known baseline.
        self.config.coin_price_streak_freeze = 80
        self.config.freeze_token_max_inventory = 7
        self.config.save(update_fields=["coin_price_streak_freeze", "freeze_token_max_inventory"])

        # Patch only one of the two fields.
        resp = self._patch({"coin_price_streak_freeze": 90})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["coin_price_streak_freeze"], 90)
        # Unrelated field must be preserved.
        self.assertEqual(data["freeze_token_max_inventory"], 7)

    def test_patch_requires_admin_role(self):
        teacher = _make_user(
            f"t2@{self.tenant.subdomain}.test", self.tenant, role="TEACHER"
        )
        teacher_client = _admin_client(self.tenant, teacher)
        resp = teacher_client.patch(
            "/api/v1/gamification/admin/config/update/",
            {"coin_price_streak_freeze": 999},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)
