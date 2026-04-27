# apps/progress/tests_badge_rarity.py
#
# Phase 4 — Badge Rarity Tier Tests (TDD — RED first)
#
# Covers:
#   - 6 rarity tiers: common, uncommon, rare, epic, legendary, mythic
#   - 6 badge categories including 'social_learning'
#   - BadgeDefinition.rarity field (model + serializer)
#   - Admin badge create/list/update endpoints expose rarity
#   - Teacher badge list endpoint returns rarity

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.progress.gamification_models import (
    BADGE_CATEGORY_CHOICES,
    BADGE_RARITY_CHOICES,
    BadgeDefinition,
    TeacherBadge,
)
from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_tenant(name="Rarity School", subdomain="rarityschool"):
    return Tenant.objects.create(
        name=name,
        slug=subdomain,
        subdomain=subdomain,
        email=f"{subdomain}@test.com",
        is_active=True,
    )


def _create_admin(tenant, email="admin@rarity.test"):
    return User.objects.create_user(
        email=email,
        password="pass123",
        first_name="Admin",
        last_name="User",
        tenant=tenant,
        role="SCHOOL_ADMIN",
        is_active=True,
    )


def _create_teacher(tenant, email="teacher@rarity.test"):
    return User.objects.create_user(
        email=email,
        password="pass123",
        first_name="Teacher",
        last_name="User",
        tenant=tenant,
        role="TEACHER",
        is_active=True,
    )


def _create_badge(tenant, name="Test Badge", rarity="common"):
    return BadgeDefinition.all_objects.create(
        tenant=tenant,
        name=name,
        description="Test badge",
        icon="star",
        color="#6C63FF",
        category="milestone",
        rarity=rarity,
        criteria_type="manual",
        criteria_value=0,
        is_active=True,
    )


# ---------------------------------------------------------------------------
# 1. Model-level tests
# ---------------------------------------------------------------------------

class BadgeRarityModelTest(TestCase):
    """BadgeDefinition.rarity field must exist with correct choices."""

    def setUp(self):
        self.tenant = _create_tenant()

    def test_badge_definition_has_rarity_field(self):
        """BadgeDefinition must have a rarity field."""
        badge = _create_badge(self.tenant, rarity="common")
        self.assertEqual(badge.rarity, "common")

    def test_rarity_choices_has_six_tiers(self):
        """BADGE_RARITY_CHOICES must define exactly 6 rarity tiers."""
        keys = [choice[0] for choice in BADGE_RARITY_CHOICES]
        self.assertEqual(len(keys), 6, f"Expected 6 rarity tiers, got {len(keys)}: {keys}")

    def test_rarity_choices_includes_all_six_tiers(self):
        """All 6 expected rarity tier keys must be present."""
        expected = {"common", "uncommon", "rare", "epic", "legendary", "mythic"}
        actual = {choice[0] for choice in BADGE_RARITY_CHOICES}
        self.assertEqual(actual, expected)

    def test_badge_category_choices_has_six_categories(self):
        """BADGE_CATEGORY_CHOICES must define exactly 6 categories."""
        keys = [choice[0] for choice in BADGE_CATEGORY_CHOICES]
        self.assertEqual(len(keys), 6, f"Expected 6 categories, got {len(keys)}: {keys}")

    def test_badge_category_choices_includes_social_learning(self):
        """BADGE_CATEGORY_CHOICES must include 'social_learning'."""
        keys = {choice[0] for choice in BADGE_CATEGORY_CHOICES}
        self.assertIn("social_learning", keys)

    def test_rarity_defaults_to_common(self):
        """New badges must default to 'common' rarity."""
        badge = BadgeDefinition.all_objects.create(
            tenant=self.tenant,
            name="Default Rarity Badge",
            category="milestone",
            criteria_type="manual",
        )
        self.assertEqual(badge.rarity, "common")

    def test_all_six_rarity_values_are_saveable(self):
        """Each of the 6 rarity tiers must save without error."""
        rarities = ["common", "uncommon", "rare", "epic", "legendary", "mythic"]
        for i, rarity in enumerate(rarities):
            badge = _create_badge(self.tenant, name=f"Badge {rarity}", rarity=rarity)
            badge.refresh_from_db()
            self.assertEqual(badge.rarity, rarity, f"Rarity '{rarity}' did not round-trip correctly")

    def test_social_learning_category_is_saveable(self):
        """Badges with category='social_learning' must save without error."""
        badge = BadgeDefinition.all_objects.create(
            tenant=self.tenant,
            name="Social Learning Badge",
            category="social_learning",
            criteria_type="manual",
        )
        badge.refresh_from_db()
        self.assertEqual(badge.category, "social_learning")


# ---------------------------------------------------------------------------
# 2. Admin API tests — badge create/list/update expose rarity
# ---------------------------------------------------------------------------

@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class BadgeRarityAdminApiTest(TestCase):
    """Admin badge CRUD must expose and accept the rarity field."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = _create_tenant()
        self.admin = _create_admin(self.tenant)
        self.client.force_authenticate(user=self.admin)
        # Simulate tenant middleware
        self.client.defaults["HTTP_HOST"] = f"{self.tenant.subdomain}.lms.com"

    def _badge_list_url(self):
        return "/api/v1/gamification/admin/badges/"

    def _badge_create_url(self):
        return "/api/v1/gamification/admin/badges/create/"

    def _badge_update_url(self, badge_id):
        return f"/api/v1/gamification/admin/badges/{badge_id}/update/"

    def test_badge_list_includes_rarity(self):
        """GET /admin/badges/ must include 'rarity' in each badge object."""
        _create_badge(self.tenant, name="Common Badge", rarity="common")
        resp = self.client.get(self._badge_list_url(),
                               HTTP_HOST=f"{self.tenant.subdomain}.lms.com")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data.get("results", data)
        if isinstance(results, list) and results:
            self.assertIn("rarity", results[0], "rarity field missing from badge list response")

    def test_badge_create_with_rarity(self):
        """POST /admin/badges/create/ must accept and persist rarity field."""
        payload = {
            "name": "Epic Achievement",
            "description": "An epic badge",
            "icon": "trophy",
            "color": "#F7B731",
            "category": "milestone",
            "rarity": "epic",
            "criteria_type": "manual",
            "criteria_value": 0,
            "is_active": True,
            "sort_order": 1,
        }
        resp = self.client.post(self._badge_create_url(), payload, format="json",
                                HTTP_HOST=f"{self.tenant.subdomain}.lms.com")
        self.assertEqual(resp.status_code, 201, resp.json())
        data = resp.json()
        self.assertEqual(data.get("rarity"), "epic")

    def test_badge_create_with_social_learning_category(self):
        """POST /admin/badges/create/ must accept 'social_learning' as category."""
        payload = {
            "name": "Peer Mentor",
            "category": "social_learning",
            "rarity": "uncommon",
            "criteria_type": "manual",
            "criteria_value": 0,
        }
        resp = self.client.post(self._badge_create_url(), payload, format="json",
                                HTTP_HOST=f"{self.tenant.subdomain}.lms.com")
        self.assertEqual(resp.status_code, 201, resp.json())
        self.assertEqual(resp.json().get("category"), "social_learning")

    def test_badge_create_defaults_rarity_to_common(self):
        """POST /admin/badges/create/ without rarity should default to 'common'."""
        payload = {
            "name": "Default Rarity Badge",
            "category": "milestone",
            "criteria_type": "manual",
            "criteria_value": 0,
        }
        resp = self.client.post(self._badge_create_url(), payload, format="json",
                                HTTP_HOST=f"{self.tenant.subdomain}.lms.com")
        self.assertEqual(resp.status_code, 201, resp.json())
        self.assertEqual(resp.json().get("rarity"), "common")

    def test_badge_update_rarity(self):
        """PATCH /admin/badges/{id}/update/ must update rarity field."""
        badge = _create_badge(self.tenant, name="Upgrade Badge", rarity="common")
        resp = self.client.patch(
            self._badge_update_url(badge.id),
            {"rarity": "legendary"},
            format="json",
            HTTP_HOST=f"{self.tenant.subdomain}.lms.com",
        )
        self.assertEqual(resp.status_code, 200, resp.json())
        badge.refresh_from_db()
        self.assertEqual(badge.rarity, "legendary")

    def test_badge_create_with_invalid_rarity_returns_400(self):
        """POST /admin/badges/create/ with invalid rarity must return 400."""
        payload = {
            "name": "Bad Rarity Badge",
            "category": "milestone",
            "rarity": "godmode",  # invalid
            "criteria_type": "manual",
            "criteria_value": 0,
        }
        resp = self.client.post(self._badge_create_url(), payload, format="json",
                                HTTP_HOST=f"{self.tenant.subdomain}.lms.com")
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# 3. Teacher badge list returns rarity
# ---------------------------------------------------------------------------

@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class BadgeRarityTeacherApiTest(TestCase):
    """Teacher badge list endpoint must include rarity in badge definitions."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = _create_tenant(subdomain="rarityteacher")
        self.teacher = _create_teacher(self.tenant)
        self.client.force_authenticate(user=self.teacher)
        self.host = f"{self.tenant.subdomain}.lms.com"

    def test_teacher_badge_definitions_include_rarity(self):
        """GET /gamification/badge-definitions/ must include rarity."""
        _create_badge(self.tenant, name="Rare Badge", rarity="rare")
        resp = self.client.get(
            "/api/v1/gamification/badge-definitions/",
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data.get("results", data)
        if isinstance(results, list) and results:
            self.assertIn("rarity", results[0], "rarity missing from teacher badge definitions")

    def test_teacher_earned_badges_include_rarity(self):
        """GET /gamification/badges/ must expose rarity inside the nested badge definition."""
        badge = _create_badge(self.tenant, name="Earned Epic", rarity="epic")
        TeacherBadge.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            badge=badge,
            awarded_reason="test award",
        )
        resp = self.client.get(
            "/api/v1/gamification/badges/",
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data.get("results", data)
        self.assertEqual(len(results), 1, "Expected exactly 1 earned badge")
        nested_badge = results[0].get("badge", {})
        self.assertIn("rarity", nested_badge, "rarity missing from earned badge nested definition")
        self.assertEqual(nested_badge["rarity"], "epic")

    def test_teacher_badge_definitions_multiple_rarities(self):
        """GET /gamification/badge-definitions/ returns correct rarity value for each tier."""
        _create_badge(self.tenant, name="Common One", rarity="common")
        _create_badge(self.tenant, name="Legendary One", rarity="legendary")
        _create_badge(self.tenant, name="Mythic One", rarity="mythic")
        resp = self.client.get(
            "/api/v1/gamification/badge-definitions/",
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data.get("results", data)
        self.assertEqual(len(results), 3)
        actual_rarities = {r["rarity"] for r in results}
        self.assertEqual(actual_rarities, {"common", "legendary", "mythic"})

    def test_teacher_cannot_see_other_tenant_badge_definitions(self):
        """Teacher from tenant A must not see badge definitions belonging to tenant B."""
        tenant_b = _create_tenant(name="Rarity School B", subdomain="rarityschoolb")
        _create_badge(tenant_b, name="Tenant B Mythic Badge", rarity="mythic")
        # This teacher's client uses tenant A's host — should only see tenant A data
        resp = self.client.get(
            "/api/v1/gamification/badge-definitions/",
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data.get("results", data)
        names = [r["name"] for r in results]
        self.assertNotIn(
            "Tenant B Mythic Badge",
            names,
            "Tenant B badge definition leaked into tenant A's response",
        )
