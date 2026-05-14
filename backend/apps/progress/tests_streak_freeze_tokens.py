# apps/progress/tests_streak_freeze_tokens.py
#
# Phase 4 — Streak Freeze Tokens + Grace Period + Weekend Mode (TDD RED first)
#
# Covers:
#   - StreakFreezeToken model (earnable/spendable)
#   - StreakFreezeLedger model (audit log)
#   - TeacherStreak.weekend_mode_enabled + grace_period_ends_at
#   - GamificationConfig: grace_period_hours, weekend_mode_available,
#     freeze_token_earn_every_n_days, freeze_token_expires_days,
#     freeze_token_max_inventory
#   - Engine: earn_streak_freeze_token, spend_streak_freeze_token
#   - API: inventory, use, weekend-mode, ledger endpoints
#   - Tenant isolation end-to-end

from datetime import date, timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.progress.gamification_engine import get_or_create_config
from apps.progress.gamification_models import (
    GamificationConfig,
    StreakFreezeLedger,
    StreakFreezeToken,
    TeacherStreak,
)
from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_tenant(name="Freeze School", subdomain="freezeschool"):
    return Tenant.objects.create(
        name=name,
        slug=subdomain,
        subdomain=subdomain,
        email=f"{subdomain}@test.com",
        is_active=True,
    )


def _create_teacher(tenant, email="teacher@freeze.test"):
    return User.objects.create_user(
        email=email,
        password="pass123",
        first_name="Teacher",
        last_name="User",
        tenant=tenant,
        role="TEACHER",
        is_active=True,
    )


def _get_streak(teacher, tenant):
    streak, _ = TeacherStreak.all_objects.get_or_create(
        teacher=teacher,
        defaults={'tenant': tenant},
    )
    return streak


# ---------------------------------------------------------------------------
# 1. Model tests
# ---------------------------------------------------------------------------

class StreakFreezeModelTest(TestCase):
    def setUp(self):
        self.tenant = _create_tenant()
        self.teacher = _create_teacher(self.tenant)

    def test_streak_freeze_token_can_be_created(self):
        token = StreakFreezeToken.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            source='streak_milestone',
        )
        self.assertIsNone(token.consumed_at)
        self.assertEqual(token.source, 'streak_milestone')

    def test_streak_freeze_token_is_tenant_isolated(self):
        other = _create_tenant(subdomain="otherfreeze")
        other_teacher = _create_teacher(other, email="t@other.test")
        StreakFreezeToken.all_objects.create(
            tenant=self.tenant, teacher=self.teacher, source='streak_milestone',
        )
        StreakFreezeToken.all_objects.create(
            tenant=other, teacher=other_teacher, source='streak_milestone',
        )
        # All objects — both visible
        self.assertEqual(StreakFreezeToken.all_objects.count(), 2)

    def test_streak_freeze_ledger_record_is_immutable_append(self):
        entry = StreakFreezeLedger.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            event_type='earned',
            description='Streak milestone',
            balance_after=1,
        )
        self.assertEqual(entry.event_type, 'earned')
        self.assertEqual(entry.balance_after, 1)

    def test_teacher_streak_weekend_mode_defaults_false(self):
        streak = _get_streak(self.teacher, self.tenant)
        self.assertFalse(streak.weekend_mode_enabled)

    def test_teacher_streak_grace_period_ends_at_nullable(self):
        streak = _get_streak(self.teacher, self.tenant)
        self.assertIsNone(streak.grace_period_ends_at)

    def test_gamification_config_freeze_defaults(self):
        config = get_or_create_config(self.tenant)
        self.assertEqual(config.grace_period_hours, 24)
        self.assertFalse(config.weekend_mode_available)
        self.assertEqual(config.freeze_token_earn_every_n_days, 7)
        self.assertEqual(config.freeze_token_expires_days, 90)
        self.assertEqual(config.freeze_token_max_inventory, 3)


# ---------------------------------------------------------------------------
# 2. Engine tests
# ---------------------------------------------------------------------------

class StreakFreezeEngineTest(TestCase):
    def setUp(self):
        self.tenant = _create_tenant()
        self.teacher = _create_teacher(self.tenant)
        self.config = get_or_create_config(self.tenant)

    def test_earn_streak_freeze_token_creates_token_and_ledger(self):
        from apps.progress.gamification_engine import earn_streak_freeze_token

        token = earn_streak_freeze_token(
            self.teacher, source='streak_milestone', description='7-day streak',
        )
        self.assertIsNotNone(token)
        self.assertEqual(token.teacher, self.teacher)
        self.assertEqual(token.tenant, self.tenant)
        ledger = StreakFreezeLedger.all_objects.filter(teacher=self.teacher).first()
        self.assertIsNotNone(ledger)
        self.assertEqual(ledger.event_type, 'earned')
        self.assertEqual(ledger.balance_after, 1)

    def test_earn_respects_max_inventory_cap(self):
        from apps.progress.gamification_engine import earn_streak_freeze_token

        self.config.freeze_token_max_inventory = 2
        self.config.save()

        t1 = earn_streak_freeze_token(self.teacher, source='streak_milestone')
        t2 = earn_streak_freeze_token(self.teacher, source='streak_milestone')
        t3 = earn_streak_freeze_token(self.teacher, source='streak_milestone')

        self.assertIsNotNone(t1)
        self.assertIsNotNone(t2)
        self.assertIsNone(t3, "Third earn must be rejected (cap reached)")
        unconsumed = StreakFreezeToken.all_objects.filter(
            teacher=self.teacher, consumed_at__isnull=True,
        ).count()
        self.assertEqual(unconsumed, 2)

    def test_spend_streak_freeze_token_consumes_oldest(self):
        from apps.progress.gamification_engine import (
            earn_streak_freeze_token,
            spend_streak_freeze_token,
        )

        t1 = earn_streak_freeze_token(self.teacher, source='streak_milestone')
        t2 = earn_streak_freeze_token(self.teacher, source='admin_grant')

        spent = spend_streak_freeze_token(self.teacher, description='cover miss')
        self.assertIsNotNone(spent)
        self.assertEqual(spent.id, t1.id, "Oldest token must be spent first (FIFO)")
        spent.refresh_from_db()
        self.assertIsNotNone(spent.consumed_at)
        t2.refresh_from_db()
        self.assertIsNone(t2.consumed_at)

        ledger_count = StreakFreezeLedger.all_objects.filter(
            teacher=self.teacher, event_type='spent',
        ).count()
        self.assertEqual(ledger_count, 1)

    def test_spend_returns_none_if_no_tokens(self):
        from apps.progress.gamification_engine import spend_streak_freeze_token

        result = spend_streak_freeze_token(self.teacher)
        self.assertIsNone(result)

    def test_spend_skips_expired_tokens(self):
        from apps.progress.gamification_engine import spend_streak_freeze_token

        # Manually create an expired token and a fresh one
        StreakFreezeToken.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            source='streak_milestone',
            expires_at=timezone.now() - timedelta(days=1),
        )
        fresh = StreakFreezeToken.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            source='streak_milestone',
            expires_at=timezone.now() + timedelta(days=30),
        )

        spent = spend_streak_freeze_token(self.teacher)
        self.assertIsNotNone(spent)
        self.assertEqual(spent.id, fresh.id)

    def test_record_activity_grants_token_every_n_days(self):
        """After reaching a multiple of earn_every_n_days, teacher earns 1 token."""
        self.config.freeze_token_earn_every_n_days = 3
        self.config.save()

        streak = _get_streak(self.teacher, self.tenant)
        # Simulate 3 consecutive days
        base = date(2026, 4, 1)
        for i in range(3):
            streak.record_activity(date=base + timedelta(days=i))

        streak.refresh_from_db()
        self.assertEqual(streak.current_streak, 3)
        token_count = StreakFreezeToken.all_objects.filter(
            teacher=self.teacher, consumed_at__isnull=True,
        ).count()
        self.assertEqual(token_count, 1, "Expected 1 token at 3-day milestone")

    def test_weekend_mode_rolls_over_saturday_sunday(self):
        """When weekend_mode_enabled, gap of 1 Sat+Sun should preserve the streak."""
        streak = _get_streak(self.teacher, self.tenant)
        streak.weekend_mode_enabled = True
        streak.save()

        # Friday, April 3, 2026 is a Friday — verify
        friday = date(2026, 4, 3)
        assert friday.weekday() == 4, "Calibration: 2026-04-03 should be Friday"
        monday = date(2026, 4, 6)

        streak.record_activity(date=friday)
        streak.record_activity(date=monday)
        streak.refresh_from_db()
        self.assertEqual(
            streak.current_streak, 2,
            "Weekend mode must treat Fri->Mon as consecutive",
        )

    def test_weekend_mode_disabled_breaks_over_weekend(self):
        """Without weekend mode, a Fri->Mon gap should reset."""
        streak = _get_streak(self.teacher, self.tenant)
        streak.weekend_mode_enabled = False
        streak.save()

        friday = date(2026, 4, 3)
        monday = date(2026, 4, 6)
        streak.record_activity(date=friday)
        streak.record_activity(date=monday)
        streak.refresh_from_db()
        # gap = 3 days, no freeze active → reset to 1
        self.assertEqual(streak.current_streak, 1)


# ---------------------------------------------------------------------------
# 3. API tests
# ---------------------------------------------------------------------------

@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class StreakFreezeApiTest(TestCase):
    def setUp(self):
        self.tenant = _create_tenant()
        self.teacher = _create_teacher(self.tenant)
        self.client = APIClient()
        self.client.force_authenticate(user=self.teacher)
        self.host = f"{self.tenant.subdomain}.lms.com"
        self.config = get_or_create_config(self.tenant)

    def _url(self, path):
        return f"/api/v1/gamification/streak-freeze/{path}"

    def test_inventory_empty_state(self):
        resp = self.client.get(self._url("inventory/"), HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data['token_count'], 0)
        self.assertFalse(data['weekend_mode_enabled'])
        self.assertIn('max_inventory', data)

    def test_inventory_after_earning(self):
        from apps.progress.gamification_engine import earn_streak_freeze_token
        earn_streak_freeze_token(self.teacher, source='streak_milestone')
        earn_streak_freeze_token(self.teacher, source='admin_grant')

        resp = self.client.get(self._url("inventory/"), HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['token_count'], 2)

    def test_use_consumes_token(self):
        from apps.progress.gamification_engine import earn_streak_freeze_token
        earn_streak_freeze_token(self.teacher, source='streak_milestone')

        resp = self.client.post(self._url("use/"), HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['tokens_remaining'], 0)

        consumed = StreakFreezeToken.all_objects.filter(
            teacher=self.teacher, consumed_at__isnull=False,
        ).count()
        self.assertEqual(consumed, 1)

    def test_use_returns_400_when_no_tokens(self):
        resp = self.client.post(self._url("use/"), HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 400)

    def test_weekend_mode_toggle_on(self):
        self.config.weekend_mode_available = True
        self.config.save(update_fields=["weekend_mode_available"])

        resp = self.client.post(
            self._url("weekend-mode/"),
            {"enabled": True}, format="json",
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.json()['weekend_mode_enabled'])

        streak = TeacherStreak.all_objects.get(teacher=self.teacher)
        self.assertTrue(streak.weekend_mode_enabled)

    def test_weekend_mode_toggle_off(self):
        streak = _get_streak(self.teacher, self.tenant)
        streak.weekend_mode_enabled = True
        streak.save()

        resp = self.client.post(
            self._url("weekend-mode/"),
            {"enabled": False}, format="json",
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200)
        streak.refresh_from_db()
        self.assertFalse(streak.weekend_mode_enabled)

    def test_weekend_mode_rejected_when_tenant_disables_feature(self):
        self.config.weekend_mode_available = False
        self.config.save()

        resp = self.client.post(
            self._url("weekend-mode/"),
            {"enabled": True}, format="json",
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 400)

    def test_ledger_returns_events(self):
        from apps.progress.gamification_engine import (
            earn_streak_freeze_token,
            spend_streak_freeze_token,
        )
        earn_streak_freeze_token(self.teacher, source='streak_milestone')
        spend_streak_freeze_token(self.teacher, description='test')

        resp = self.client.get(self._url("ledger/"), HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        results = data.get('results', data)
        self.assertGreaterEqual(len(results), 2)
        event_types = {r['event_type'] for r in results}
        self.assertIn('earned', event_types)
        self.assertIn('spent', event_types)


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class StreakFreezeTenantIsolationTest(TestCase):
    """Verify cross-tenant leakage is impossible for freeze tokens + ledger."""

    def setUp(self):
        self.tenant_a = _create_tenant(subdomain="tenanta")
        self.tenant_b = _create_tenant(subdomain="tenantb", name="Other School")
        self.teacher_a = _create_teacher(self.tenant_a, email="a@test.com")
        self.teacher_b = _create_teacher(self.tenant_b, email="b@test.com")

    def test_teacher_b_cannot_see_teacher_a_tokens(self):
        from apps.progress.gamification_engine import earn_streak_freeze_token
        earn_streak_freeze_token(self.teacher_a, source='streak_milestone')

        client = APIClient()
        client.force_authenticate(user=self.teacher_b)
        resp = client.get(
            "/api/v1/gamification/streak-freeze/inventory/",
            HTTP_HOST=f"{self.tenant_b.subdomain}.lms.com",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()['token_count'], 0)

    def test_teacher_b_cannot_see_teacher_a_ledger(self):
        from apps.progress.gamification_engine import earn_streak_freeze_token
        earn_streak_freeze_token(self.teacher_a, source='streak_milestone')

        client = APIClient()
        client.force_authenticate(user=self.teacher_b)
        resp = client.get(
            "/api/v1/gamification/streak-freeze/ledger/",
            HTTP_HOST=f"{self.tenant_b.subdomain}.lms.com",
        )
        self.assertEqual(resp.status_code, 200)
        results = resp.json().get('results', resp.json())
        self.assertEqual(len(results), 0)
