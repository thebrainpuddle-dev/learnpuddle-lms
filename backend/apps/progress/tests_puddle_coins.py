# apps/progress/tests_puddle_coins.py
#
# TASK-019 — Puddle Coins virtual currency (TDD).
#
# Covers:
#   - Models: tenant FK + TenantManager, signed amount, EARN dedup,
#             spend rows may repeat.
#   - Engine: earn_coins idempotency, spend_coins happy path,
#             spend_coins overdraft raises, get_balance matches ledger,
#             concurrency simulation.
#   - Signals: challenge completion → earn, league promotion → earn,
#              streak milestone → earn, level-up → earn, opt-out blocks.
#   - API: GET balance, GET history, POST purchase (success + insufficient),
#          cross-tenant isolation.

import uuid
from datetime import date, timedelta

from django.db import IntegrityError, transaction as dj_transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.progress.challenge_engine import issue_challenge_rewards
from apps.progress.challenge_models import (
    Challenge,
    ChallengeParticipation,
)
from apps.progress.coin_engine import (
    InsufficientCoinsError,
    earn_coins,
    get_balance,
    spend_coins,
)
from apps.progress.gamification_engine import (
    award_xp,
    get_or_create_config,
)
from apps.progress.gamification_models import (
    CoinTransaction,
    StreakFreezeToken,
    TeacherCoinBalance,
    TeacherStreak,
    TeacherXPSummary,
)
from apps.progress.league_engine import (
    assign_teacher_to_league,
    close_league_week,
)
from apps.progress.league_models import LeagueMembership
from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CTR = {"n": 0}


def _u():
    _CTR["n"] += 1
    return _CTR["n"]


def _tenant(subdomain=None, name="Coin School"):
    sub = subdomain or f"coin{_u()}"
    return Tenant.objects.create(
        name=name, slug=sub, subdomain=sub,
        email=f"{sub}@test.com", is_active=True,
    )


def _teacher(tenant, idx=None):
    idx = idx if idx is not None else _u()
    return User.objects.create_user(
        email=f"t{idx}-{tenant.subdomain}@test.com",
        password="pass123",
        first_name="T", last_name=str(idx),
        tenant=tenant, role="TEACHER", is_active=True,
    )


def _admin(tenant, idx=None):
    idx = idx if idx is not None else _u()
    return User.objects.create_user(
        email=f"a{idx}-{tenant.subdomain}@test.com",
        password="pass123",
        first_name="A", last_name=str(idx),
        tenant=tenant, role="SCHOOL_ADMIN", is_active=True,
    )


# ===========================================================================
# 1. Model tests
# ===========================================================================


class CoinModelTest(TestCase):
    def setUp(self):
        self.tenant = _tenant()
        self.teacher = _teacher(self.tenant)

    def test_coin_transaction_requires_tenant_and_signed_amount(self):
        txn = CoinTransaction.all_objects.create(
            tenant=self.tenant, teacher=self.teacher,
            amount=25, reason="challenge_reward",
        )
        self.assertEqual(txn.tenant, self.tenant)
        self.assertEqual(txn.amount, 25)

        spend = CoinTransaction.all_objects.create(
            tenant=self.tenant, teacher=self.teacher,
            amount=-10, reason="purchase_streak_freeze",
        )
        self.assertEqual(spend.amount, -10)

    def test_tenant_manager_isolates_ledger(self):
        other = _tenant(subdomain="coinother")
        other_teacher = _teacher(other)
        CoinTransaction.all_objects.create(
            tenant=self.tenant, teacher=self.teacher,
            amount=10, reason="challenge_reward",
            reference_id=uuid.uuid4(), reference_type="challenge",
        )
        CoinTransaction.all_objects.create(
            tenant=other, teacher=other_teacher,
            amount=20, reason="challenge_reward",
            reference_id=uuid.uuid4(), reference_type="challenge",
        )
        self.assertEqual(
            CoinTransaction.all_objects.filter(tenant=self.tenant).count(),
            1,
        )
        self.assertEqual(
            CoinTransaction.all_objects.filter(tenant=other).count(),
            1,
        )

    def test_earn_unique_constraint_suppresses_duplicates(self):
        ref = uuid.uuid4()
        CoinTransaction.all_objects.create(
            tenant=self.tenant, teacher=self.teacher,
            amount=25, reason="challenge_reward",
            reference_id=ref, reference_type="challenge",
        )
        with self.assertRaises(IntegrityError):
            with dj_transaction.atomic():
                CoinTransaction.all_objects.create(
                    tenant=self.tenant, teacher=self.teacher,
                    amount=25, reason="challenge_reward",
                    reference_id=ref, reference_type="challenge",
                )

    def test_spend_rows_can_repeat(self):
        # Two spends of the same amount / reason must be allowed because
        # the unique constraint is scoped to positive amounts only.
        CoinTransaction.all_objects.create(
            tenant=self.tenant, teacher=self.teacher,
            amount=-50, reason="purchase_streak_freeze",
        )
        CoinTransaction.all_objects.create(
            tenant=self.tenant, teacher=self.teacher,
            amount=-50, reason="purchase_streak_freeze",
        )
        self.assertEqual(
            CoinTransaction.all_objects.filter(
                teacher=self.teacher, reason="purchase_streak_freeze",
            ).count(),
            2,
        )

    def test_balance_recompute_from_ledger(self):
        CoinTransaction.all_objects.create(
            tenant=self.tenant, teacher=self.teacher,
            amount=100, reason="level_up",
            reference_id=uuid.uuid4(), reference_type="level",
        )
        CoinTransaction.all_objects.create(
            tenant=self.tenant, teacher=self.teacher,
            amount=-30, reason="purchase_streak_freeze",
        )
        bal, _ = TeacherCoinBalance.all_objects.get_or_create(
            teacher=self.teacher, defaults={'tenant': self.tenant},
        )
        bal.recompute_from_transactions()
        self.assertEqual(bal.balance, 70)
        self.assertEqual(bal.lifetime_earned, 100)
        self.assertEqual(bal.lifetime_spent, 30)


# ===========================================================================
# 2. Engine tests
# ===========================================================================


class CoinEngineTest(TestCase):
    def setUp(self):
        self.tenant = _tenant()
        self.teacher = _teacher(self.tenant)
        self.config = get_or_create_config(self.tenant)

    def test_earn_coins_happy_path_updates_balance(self):
        txn = earn_coins(
            teacher=self.teacher,
            reason="challenge_reward",
            reference_id=uuid.uuid4(),
            reference_type="challenge",
            description="Test challenge",
        )
        self.assertIsNotNone(txn)
        # Default config challenge coin amount is 25.
        self.assertEqual(txn.amount, 25)

        balance = get_balance(self.teacher)
        self.assertEqual(balance.balance, 25)
        self.assertEqual(balance.lifetime_earned, 25)

    def test_earn_coins_is_idempotent_on_same_reference(self):
        ref = uuid.uuid4()
        first = earn_coins(
            teacher=self.teacher, reason="challenge_reward",
            reference_id=ref, reference_type="challenge",
        )
        dupe = earn_coins(
            teacher=self.teacher, reason="challenge_reward",
            reference_id=ref, reference_type="challenge",
        )
        self.assertIsNotNone(first)
        self.assertIsNone(dupe)
        self.assertEqual(
            CoinTransaction.all_objects.filter(teacher=self.teacher).count(),
            1,
        )

    def test_earn_coins_respects_opt_out(self):
        TeacherXPSummary.all_objects.create(
            tenant=self.tenant, teacher=self.teacher, opted_out=True,
        )
        result = earn_coins(
            teacher=self.teacher, reason="challenge_reward",
            reference_id=uuid.uuid4(), reference_type="challenge",
        )
        self.assertIsNone(result)
        self.assertEqual(
            CoinTransaction.all_objects.filter(teacher=self.teacher).count(),
            0,
        )

    def test_spend_coins_happy_path(self):
        earn_coins(
            teacher=self.teacher, reason="level_up",
            reference_id=uuid.uuid4(), reference_type="level",
        )
        # Default level_up reward is 100.
        txn = spend_coins(
            teacher=self.teacher, amount=40, reason="purchase_streak_freeze",
        )
        self.assertEqual(txn.amount, -40)

        balance = get_balance(self.teacher)
        self.assertEqual(balance.balance, 60)
        self.assertEqual(balance.lifetime_spent, 40)

    def test_spend_coins_overdraft_raises(self):
        with self.assertRaises(InsufficientCoinsError) as ctx:
            spend_coins(
                teacher=self.teacher, amount=50,
                reason="purchase_streak_freeze",
            )
        self.assertEqual(ctx.exception.balance, 0)
        self.assertEqual(ctx.exception.amount, 50)

        # No transaction created on failure.
        self.assertEqual(
            CoinTransaction.all_objects.filter(teacher=self.teacher).count(),
            0,
        )

    def test_get_balance_matches_ledger_after_many_txns(self):
        for i in range(5):
            earn_coins(
                teacher=self.teacher, reason="challenge_reward",
                reference_id=uuid.uuid4(), reference_type="challenge",
            )
        spend_coins(
            teacher=self.teacher, amount=30,
            reason="purchase_streak_freeze",
        )
        balance = get_balance(self.teacher)
        # 5 * 25 - 30 = 95
        self.assertEqual(balance.balance, 95)
        self.assertEqual(balance.lifetime_earned, 125)
        self.assertEqual(balance.lifetime_spent, 30)

    def test_spend_coins_serialises_under_concurrent_access(self):
        """
        Two simulated concurrent spend attempts should never drive the
        balance below zero. select_for_update() inside spend_coins
        guarantees serialization; the second request (in any interleave)
        must see the updated balance and either succeed (if sufficient)
        or raise InsufficientCoinsError.
        """
        # Seed 100 coins.
        for i in range(4):
            earn_coins(
                teacher=self.teacher, reason="challenge_reward",
                reference_id=uuid.uuid4(), reference_type="challenge",
            )
        # 100 coins now. Spend twice at 60 — second must fail.
        spend_coins(
            teacher=self.teacher, amount=60,
            reason="purchase_streak_freeze",
        )
        with self.assertRaises(InsufficientCoinsError):
            spend_coins(
                teacher=self.teacher, amount=60,
                reason="purchase_streak_freeze",
            )
        balance = get_balance(self.teacher)
        self.assertEqual(balance.balance, 40)


# ===========================================================================
# 3. Signal wiring tests
# ===========================================================================


class CoinSignalTest(TestCase):
    def setUp(self):
        self.tenant = _tenant()
        self.teacher = _teacher(self.tenant)
        self.admin = _admin(self.tenant)
        self.config = get_or_create_config(self.tenant)

    def test_challenge_completion_earns_coins(self):
        # Build a trivially-completable challenge.
        now = timezone.now()
        challenge = Challenge.all_objects.create(
            tenant=self.tenant,
            title="Test",
            description="",
            challenge_type="DAILY",
            goal_type="complete_lessons",
            goal_target=1,
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(hours=1),
            reward_xp=0,
            is_active=True,
            created_by=self.admin,
        )
        participation = ChallengeParticipation.all_objects.create(
            tenant=self.tenant,
            challenge=challenge,
            teacher=self.teacher,
            progress_value=1,
            completed_at=now,
        )
        issue_challenge_rewards(participation)

        self.assertTrue(
            CoinTransaction.all_objects.filter(
                teacher=self.teacher,
                reason="challenge_reward",
                reference_id=challenge.id,
                amount__gt=0,
            ).exists(),
        )

    def test_streak_milestone_earns_coins(self):
        streak, _ = TeacherStreak.all_objects.get_or_create(
            teacher=self.teacher, defaults={'tenant': self.tenant},
        )
        # Walk the streak up to the default milestone (7 days) by
        # recording activity on consecutive days.
        start = date(2026, 1, 1)
        for i in range(7):
            streak.record_activity(date=start + timedelta(days=i))

        self.assertEqual(streak.current_streak, 7)
        self.assertTrue(
            CoinTransaction.all_objects.filter(
                teacher=self.teacher,
                reason="streak_milestone",
                amount__gt=0,
            ).exists(),
        )

    def test_level_up_earns_coins(self):
        # BADGE_LEVELS has level 2 at min_points=500 (Apprentice). Award
        # enough XP to cross the threshold.
        award_xp(
            teacher=self.teacher,
            reason="admin_adjust",
            xp_amount=600,
            description="bulk",
        )
        self.assertTrue(
            CoinTransaction.all_objects.filter(
                teacher=self.teacher,
                reason="level_up",
                amount__gt=0,
            ).exists(),
        )

    def test_level_up_coin_is_idempotent_on_repeat_award(self):
        # 600 XP → BADGE_LEVELS jumps from L1 to L3 (crosses L2 + L3 both),
        # earning 2 distinct level-up coin txns (one per level crossed).
        award_xp(
            teacher=self.teacher, reason="admin_adjust",
            xp_amount=600, description="first",
        )
        first_count = CoinTransaction.all_objects.filter(
            teacher=self.teacher, reason="level_up",
        ).count()
        self.assertEqual(first_count, 2)
        # A second award that keeps them at the same level must not earn
        # additional level-up coins.
        award_xp(
            teacher=self.teacher, reason="admin_adjust",
            xp_amount=5, description="nudge",
        )
        self.assertEqual(
            CoinTransaction.all_objects.filter(
                teacher=self.teacher, reason="level_up",
            ).count(),
            first_count,
        )

    def test_league_promote_earns_coins(self):
        # Build a cohort of 3 with teacher as top earner.
        teachers = [self.teacher] + [_teacher(self.tenant) for _ in range(2)]
        for t in teachers:
            award_xp(
                teacher=t, reason="admin_adjust",
                xp_amount=10, description="seed",
            )
            assign_teacher_to_league(t)
        # Give self.teacher the highest weekly_xp.
        LeagueMembership.all_objects.filter(teacher=self.teacher).update(
            weekly_xp=500,
        )

        # Drop existing coin txns to isolate promote earn.
        CoinTransaction.all_objects.filter(teacher=self.teacher).delete()

        close_league_week(self.tenant)

        self.assertTrue(
            CoinTransaction.all_objects.filter(
                teacher=self.teacher,
                reason="league_promote",
                amount__gt=0,
            ).exists(),
        )


# ===========================================================================
# 4. API tests
# ===========================================================================


@override_settings(ALLOWED_HOSTS=["*"])
class CoinApiTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = _tenant(subdomain="coinapi")
        self.host = f"{self.tenant.subdomain}.lms.com"
        self.teacher = _teacher(self.tenant)
        self.config = get_or_create_config(self.tenant)

        # Seed 200 coins for spend tests.
        for i in range(8):
            earn_coins(
                teacher=self.teacher, reason="challenge_reward",
                reference_id=uuid.uuid4(), reference_type="challenge",
            )  # 8 * 25 = 200.

    def _login(self, user):
        self.client.defaults["HTTP_HOST"] = self.host
        resp = self.client.post(
            "/api/users/auth/login/",
            {"email": user.email, "password": "pass123"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        access = resp.json()["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def test_get_balance_endpoint(self):
        self._login(self.teacher)
        resp = self.client.get(
            "/api/v1/gamification/coins/", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data["balance"], 200)
        self.assertEqual(data["lifetime_earned"], 200)

    def test_get_history_endpoint(self):
        self._login(self.teacher)
        resp = self.client.get(
            "/api/v1/gamification/coins/history/", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertIn("results", data)
        self.assertEqual(len(data["results"]), 8)

    def test_purchase_streak_freeze_success(self):
        self._login(self.teacher)
        resp = self.client.post(
            "/api/v1/gamification/coins/purchase/streak-freeze/",
            {}, format="json", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        # Default price is 50, starting balance 200 → 150 remaining.
        self.assertEqual(data["balance"]["balance"], 150)
        self.assertIsNotNone(data["token"]["id"])
        self.assertEqual(data["token"]["source"], "purchase")

        # Token is now in the teacher's inventory.
        self.assertEqual(
            StreakFreezeToken.all_objects.filter(
                teacher=self.teacher, consumed_at__isnull=True,
            ).count(),
            1,
        )

    def test_purchase_streak_freeze_insufficient_coins(self):
        # Reset balance to zero.
        CoinTransaction.all_objects.filter(teacher=self.teacher).delete()
        bal = get_balance(self.teacher)
        bal.recompute_from_transactions()

        self._login(self.teacher)
        resp = self.client.post(
            "/api/v1/gamification/coins/purchase/streak-freeze/",
            {}, format="json", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        body = resp.json()
        self.assertEqual(body.get("balance"), 0)
        self.assertEqual(body.get("price"), 50)

    def test_get_balance_includes_price_streak_freeze_field(self):
        """
        GET /api/v1/gamification/coins/ must include ``price_streak_freeze``
        so the frontend Shop card can display the purchase price without an
        extra config call.

        Specifically verifies the BE-FOLLOWUPS-2026-04-20 requirement:
        assert ``price_streak_freeze`` key is present and equals
        ``GamificationConfig.coin_price_streak_freeze`` (default 50).
        """
        self._login(self.teacher)
        resp = self.client.get(
            "/api/v1/gamification/coins/", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        # Field must be present.
        self.assertIn("price_streak_freeze", data, "price_streak_freeze missing from balance response")
        # Default coin_price_streak_freeze is 50 (per GamificationConfig default).
        self.assertEqual(data["price_streak_freeze"], 50)
        # Verify it tracks the live config value — bump it and re-check.
        self.config.coin_price_streak_freeze = 75
        self.config.save(update_fields=["coin_price_streak_freeze"])
        resp2 = self.client.get(
            "/api/v1/gamification/coins/", HTTP_HOST=self.host,
        )
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json()["price_streak_freeze"], 75)

    def test_cross_tenant_isolation_on_history(self):
        other = _tenant(subdomain="coinother2")
        other_teacher = _teacher(other)
        earn_coins(
            teacher=other_teacher, reason="challenge_reward",
            reference_id=uuid.uuid4(), reference_type="challenge",
        )

        self._login(self.teacher)
        resp = self.client.get(
            "/api/v1/gamification/coins/history/", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # Only self.teacher's 8 txns — other tenant's row must not leak.
        self.assertEqual(len(data["results"]), 8)
        for row in data["results"]:
            self.assertNotEqual(
                row.get("reference_id"), None,
            )

    def test_unauthenticated_balance_returns_401(self):
        """Coin balance endpoint must reject unauthenticated requests."""
        anon_client = APIClient()
        resp = anon_client.get(
            "/api/v1/gamification/coins/", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 401)

    def test_unauthenticated_purchase_returns_401(self):
        """Purchase endpoint must reject unauthenticated requests."""
        anon_client = APIClient()
        resp = anon_client.post(
            "/api/v1/gamification/coins/purchase/streak-freeze/",
            {}, format="json", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 401)

    def test_purchase_at_inventory_cap_returns_400(self):
        """
        When the teacher already holds ``freeze_token_max_inventory`` tokens,
        attempting to purchase another must return 400 with a ``cap`` key.

        Covers the branch in ``teacher_purchase_streak_freeze`` that checks
        ``available >= config.freeze_token_max_inventory`` before debiting coins.
        """
        from apps.progress.gamification_models import StreakFreezeToken

        # Set cap to 1 so a single existing token triggers the limit.
        self.config.freeze_token_max_inventory = 1
        self.config.save(update_fields=["freeze_token_max_inventory"])

        # Mint one token directly (bypassing the coin path).
        StreakFreezeToken.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            source="admin_grant",
        )

        self._login(self.teacher)
        resp = self.client.post(
            "/api/v1/gamification/coins/purchase/streak-freeze/",
            {}, format="json", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        body = resp.json()
        self.assertIn("cap", body,
                      "'cap' key expected in inventory-cap error response")
        # Balance must not have changed — no coins debited.
        from apps.progress.coin_engine import get_balance
        balance = get_balance(self.teacher)
        self.assertEqual(balance.balance, 200,
                         "Coins must not be debited when purchase is blocked by inventory cap")
