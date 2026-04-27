# apps/progress/tests_leagues.py
#
# TASK-016 — 10-Tier League Leaderboards (TDD — RED first)
#
# Covers:
#   - 10 tier taxonomy constants
#   - League / LeagueMembership / LeagueRankSnapshot models
#   - Engine: auto-assignment on first activity, tenant isolation
#   - Weekly-reset Celery task: promote/demote math, idempotency, tenant scope
#   - API: teacher current league, teacher league history, admin overview
#   - Opt-in/opt-out respected

from datetime import date, timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.progress.gamification_models import (
    GamificationConfig,
    TeacherXPSummary,
    XPTransaction,
)
from apps.progress.league_models import (
    LEAGUE_TIERS,
    League,
    LeagueMembership,
    LeagueRankSnapshot,
)
from apps.progress.league_engine import (
    assign_teacher_to_league,
    close_league_week,
    get_current_league_for_teacher,
    get_or_create_tier_league,
)
from apps.progress.gamification_tasks import close_league_week_task
from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tenant(name="League School", subdomain="leagueschool"):
    return Tenant.objects.create(
        name=name,
        slug=subdomain,
        subdomain=subdomain,
        email=f"{subdomain}@test.com",
        is_active=True,
    )


import uuid as _uuid


def _teacher(tenant, email=None, first="T", last="Eacher"):
    email = email or f"t-{_uuid.uuid4().hex[:12]}@lg.test"
    return User.objects.create_user(
        email=email,
        password="pass123",
        first_name=first,
        last_name=last,
        tenant=tenant,
        role="TEACHER",
        is_active=True,
    )


def _admin(tenant):
    return User.objects.create_user(
        email="admin@lg.test",
        password="pass123",
        first_name="Admin",
        last_name="User",
        tenant=tenant,
        role="SCHOOL_ADMIN",
        is_active=True,
    )


def _summary(tenant, teacher, total_xp=0, opted_out=False, league_opted_out=False):
    summary, _ = TeacherXPSummary.all_objects.get_or_create(
        teacher=teacher,
        defaults={"tenant": tenant},
    )
    summary.total_xp = total_xp
    summary.opted_out = opted_out
    summary.league_opted_out = league_opted_out
    summary.save()
    return summary


def _week_start(today=None):
    today = today or timezone.localdate()
    return today - timedelta(days=today.weekday())  # Monday


# ---------------------------------------------------------------------------
# 1. Tier constants
# ---------------------------------------------------------------------------

class LeagueTierConstantsTest(TestCase):
    def test_ten_tiers_defined(self):
        self.assertEqual(len(LEAGUE_TIERS), 10, f"Expected 10 tiers, got {len(LEAGUE_TIERS)}")

    def test_tier_codes_unique(self):
        codes = [t["code"] for t in LEAGUE_TIERS]
        self.assertEqual(len(codes), len(set(codes)))

    def test_tier_ranks_are_1_through_10(self):
        ranks = sorted(t["rank"] for t in LEAGUE_TIERS)
        self.assertEqual(ranks, list(range(1, 11)))

    def test_bottom_tier_is_bronze_1(self):
        bottom = min(LEAGUE_TIERS, key=lambda t: t["rank"])
        self.assertEqual(bottom["code"], "bronze_1")

    def test_top_tier_is_diamond(self):
        top = max(LEAGUE_TIERS, key=lambda t: t["rank"])
        self.assertEqual(top["code"], "diamond")


# ---------------------------------------------------------------------------
# 2. Model tests
# ---------------------------------------------------------------------------

class LeagueModelTest(TestCase):
    def setUp(self):
        self.tenant = _tenant()
        self.teacher = _teacher(self.tenant, email="t1@lg.test")

    def test_league_create(self):
        league = League.all_objects.create(
            tenant=self.tenant,
            tier_code="bronze_1",
            tier_rank=1,
            week_start_date=_week_start(),
        )
        self.assertEqual(league.tier_code, "bronze_1")
        self.assertIsNone(league.closed_at)

    def test_league_membership_unique_per_teacher_per_week(self):
        league = League.all_objects.create(
            tenant=self.tenant,
            tier_code="silver_2",
            tier_rank=5,
            week_start_date=_week_start(),
        )
        LeagueMembership.all_objects.create(
            tenant=self.tenant,
            league=league,
            teacher=self.teacher,
        )
        # A teacher should only be in one league for a given week_start_date;
        # this is enforced at the DB level.
        from django.db.utils import IntegrityError
        with self.assertRaises(IntegrityError):
            LeagueMembership.all_objects.create(
                tenant=self.tenant,
                league=league,
                teacher=self.teacher,
            )

    def test_cross_tenant_isolation(self):
        other = _tenant(subdomain="leagueother")
        League.all_objects.create(
            tenant=self.tenant, tier_code="gold_1", tier_rank=7,
            week_start_date=_week_start(),
        )
        League.all_objects.create(
            tenant=other, tier_code="gold_1", tier_rank=7,
            week_start_date=_week_start(),
        )
        self.assertEqual(League.all_objects.count(), 2)

    def test_rank_snapshot_record(self):
        league = League.all_objects.create(
            tenant=self.tenant, tier_code="diamond", tier_rank=10,
            week_start_date=_week_start(),
        )
        snap = LeagueRankSnapshot.all_objects.create(
            tenant=self.tenant,
            league=league,
            teacher=self.teacher,
            tier_code="diamond",
            tier_rank=10,
            week_start_date=_week_start(),
            final_rank=1,
            weekly_xp=500,
            outcome="hold",
        )
        self.assertEqual(snap.outcome, "hold")


# ---------------------------------------------------------------------------
# 3. Engine — assignment
# ---------------------------------------------------------------------------

class LeagueAssignmentTest(TestCase):
    def setUp(self):
        self.tenant = _tenant(subdomain="assignmentschool")
        self.teacher = _teacher(self.tenant, email="asn@lg.test")
        _summary(self.tenant, self.teacher)

    def test_new_teacher_assigned_to_bottom_tier(self):
        membership = assign_teacher_to_league(self.teacher)
        self.assertIsNotNone(membership)
        self.assertEqual(membership.league.tier_code, "bronze_1")
        self.assertEqual(membership.league.tier_rank, 1)

    def test_assignment_is_idempotent_for_same_week(self):
        m1 = assign_teacher_to_league(self.teacher)
        m2 = assign_teacher_to_league(self.teacher)
        self.assertEqual(m1.id, m2.id)

    def test_get_current_league_returns_assigned_league(self):
        assign_teacher_to_league(self.teacher)
        current = get_current_league_for_teacher(self.teacher)
        self.assertIsNotNone(current)
        self.assertEqual(current.tier_code, "bronze_1")

    def test_opted_out_teacher_not_assigned(self):
        _summary(self.tenant, self.teacher, opted_out=True)
        m = assign_teacher_to_league(self.teacher)
        self.assertIsNone(m)

    def test_league_opted_out_teacher_not_assigned(self):
        _summary(self.tenant, self.teacher, league_opted_out=True)
        m = assign_teacher_to_league(self.teacher)
        self.assertIsNone(m)

    def test_cohort_fills_up_to_configured_size(self):
        # Create cohort_size teachers; all should fit in the same league.
        config, _ = GamificationConfig.objects.get_or_create(tenant=self.tenant)
        config.league_cohort_size = 5
        config.save()

        teachers = [_teacher(self.tenant, email=f"c{i}@lg.test") for i in range(5)]
        for t in teachers:
            _summary(self.tenant, t)
            assign_teacher_to_league(t)

        leagues = League.all_objects.filter(
            tenant=self.tenant, tier_code="bronze_1", week_start_date=_week_start(),
        )
        self.assertEqual(leagues.count(), 1)
        self.assertEqual(leagues.first().memberships.count(), 5)

    def test_cohort_overflow_creates_new_league(self):
        config, _ = GamificationConfig.objects.get_or_create(tenant=self.tenant)
        config.league_cohort_size = 3
        config.save()

        teachers = [_teacher(self.tenant, email=f"of{i}@lg.test") for i in range(4)]
        for t in teachers:
            _summary(self.tenant, t)
            assign_teacher_to_league(t)

        leagues = League.all_objects.filter(
            tenant=self.tenant, tier_code="bronze_1", week_start_date=_week_start(),
        )
        self.assertEqual(leagues.count(), 2)


# ---------------------------------------------------------------------------
# 4. Engine — promote/demote math (close_league_week)
# ---------------------------------------------------------------------------

class LeagueCloseWeekTest(TestCase):
    def setUp(self):
        self.tenant = _tenant(subdomain="promoteschool")
        config, _ = GamificationConfig.objects.get_or_create(tenant=self.tenant)
        config.league_cohort_size = 10
        config.league_promote_count = 3
        config.league_demote_count = 3
        config.leagues_enabled = True
        config.save()
        self.config = config

    def _make_league(self, tier_code, tier_rank, num_members, week_start=None):
        week_start = week_start or _week_start()
        league = League.all_objects.create(
            tenant=self.tenant,
            tier_code=tier_code,
            tier_rank=tier_rank,
            week_start_date=week_start,
        )
        memberships = []
        for i in range(num_members):
            t = _teacher(self.tenant, email=f"{tier_code}_{i}_{week_start}@lg.test")
            _summary(self.tenant, t, total_xp=i * 10)
            m = LeagueMembership.all_objects.create(
                tenant=self.tenant,
                league=league,
                teacher=t,
                weekly_xp=(num_members - i) * 100,  # teacher i=0 top, i=N-1 bottom
            )
            memberships.append(m)
        return league, memberships

    def test_top_n_promoted_middle_held_bottom_n_demoted(self):
        league, memberships = self._make_league("silver_2", 5, 10)
        week_start = _week_start()

        close_league_week(tenant=self.tenant, week_start_date=week_start)

        # Snapshots written for all 10 members
        snaps = LeagueRankSnapshot.all_objects.filter(
            tenant=self.tenant, league=league,
        ).order_by("final_rank")
        self.assertEqual(snaps.count(), 10)

        promoted = [s for s in snaps if s.outcome == "promote"]
        held = [s for s in snaps if s.outcome == "hold"]
        demoted = [s for s in snaps if s.outcome == "demote"]

        self.assertEqual(len(promoted), 3)
        self.assertEqual(len(held), 4)
        self.assertEqual(len(demoted), 3)

        # Old league is closed
        league.refresh_from_db()
        self.assertIsNotNone(league.closed_at)

        # Next-week memberships are created, in shifted tiers
        next_week = week_start + timedelta(days=7)
        promoted_teacher_ids = {s.teacher_id for s in promoted}
        demoted_teacher_ids = {s.teacher_id for s in demoted}

        next_memberships = LeagueMembership.all_objects.filter(
            tenant=self.tenant,
            league__week_start_date=next_week,
        ).select_related("league")

        for nm in next_memberships:
            if nm.teacher_id in promoted_teacher_ids:
                self.assertEqual(nm.league.tier_rank, 6)
            elif nm.teacher_id in demoted_teacher_ids:
                self.assertEqual(nm.league.tier_rank, 4)
            else:
                self.assertEqual(nm.league.tier_rank, 5)

    def test_bottom_tier_demotion_is_clamped(self):
        self._make_league("bronze_1", 1, 10)
        week_start = _week_start()
        close_league_week(tenant=self.tenant, week_start_date=week_start)

        # No snapshot has tier_rank < 1 next week (clamped)
        next_week = week_start + timedelta(days=7)
        min_rank = (
            LeagueMembership.all_objects.filter(
                tenant=self.tenant, league__week_start_date=next_week,
            )
            .values_list("league__tier_rank", flat=True)
            .order_by("league__tier_rank")
            .first()
        )
        self.assertGreaterEqual(min_rank, 1)

    def test_top_tier_promotion_is_clamped(self):
        self._make_league("diamond", 10, 10)
        week_start = _week_start()
        close_league_week(tenant=self.tenant, week_start_date=week_start)

        next_week = week_start + timedelta(days=7)
        max_rank = (
            LeagueMembership.all_objects.filter(
                tenant=self.tenant, league__week_start_date=next_week,
            )
            .values_list("league__tier_rank", flat=True)
            .order_by("-league__tier_rank")
            .first()
        )
        self.assertLessEqual(max_rank, 10)

    def test_close_week_is_idempotent(self):
        league, _ = self._make_league("gold_1", 7, 10)
        week_start = _week_start()

        summary_1 = close_league_week(tenant=self.tenant, week_start_date=week_start)
        summary_2 = close_league_week(tenant=self.tenant, week_start_date=week_start)

        self.assertEqual(summary_1["leagues_closed"], 1)
        self.assertEqual(summary_2["leagues_closed"], 0)  # already closed

        # Snapshot count stays at 10
        self.assertEqual(
            LeagueRankSnapshot.all_objects.filter(tenant=self.tenant).count(),
            10,
        )

    def test_close_week_is_tenant_scoped(self):
        # Tenant A
        self._make_league("silver_1", 4, 10)
        # Tenant B — should NOT be affected
        other = _tenant(subdomain="otherleague")
        GamificationConfig.objects.get_or_create(
            tenant=other,
            defaults={
                "league_cohort_size": 10,
                "league_promote_count": 3,
                "league_demote_count": 3,
                "leagues_enabled": True,
            },
        )
        # Create a league in tenant B manually
        b_league = League.all_objects.create(
            tenant=other, tier_code="silver_1", tier_rank=4,
            week_start_date=_week_start(),
        )

        close_league_week(tenant=self.tenant, week_start_date=_week_start())

        # Tenant B's league is untouched
        b_league.refresh_from_db()
        self.assertIsNone(b_league.closed_at)
        self.assertEqual(
            LeagueRankSnapshot.all_objects.filter(tenant=other).count(),
            0,
        )

    def test_small_cohort_scales_promote_count(self):
        """If cohort has < configured size, promote/demote counts scale down."""
        self._make_league("gold_2", 8, 4)  # only 4 members
        week_start = _week_start()
        close_league_week(tenant=self.tenant, week_start_date=week_start)

        promoted = LeagueRankSnapshot.all_objects.filter(
            tenant=self.tenant, outcome="promote",
        ).count()
        demoted = LeagueRankSnapshot.all_objects.filter(
            tenant=self.tenant, outcome="demote",
        ).count()

        # With 4 members and configured 3/3 promote/demote on a cohort of 10,
        # scaled: round(3 * 4 / 10) = 1 each.
        self.assertEqual(promoted, 1)
        self.assertEqual(demoted, 1)


# ---------------------------------------------------------------------------
# 5. Celery task — wraps engine, runs across all tenants
# ---------------------------------------------------------------------------

class LeagueWeeklyTaskTest(TestCase):
    def test_task_runs_without_error_when_no_leagues(self):
        _tenant(subdomain="emptyleague")
        summary = close_league_week_task.apply().result
        self.assertEqual(summary["leagues_closed"], 0)

    def test_task_closes_leagues_across_all_tenants(self):
        tenant_a = _tenant(subdomain="weeklytenanta")
        tenant_b = _tenant(subdomain="weeklytenantb")
        for t in (tenant_a, tenant_b):
            GamificationConfig.objects.get_or_create(
                tenant=t,
                defaults={
                    "league_cohort_size": 5,
                    "league_promote_count": 1,
                    "league_demote_count": 1,
                    "leagues_enabled": True,
                },
            )
            teacher = _teacher(t, email=f"weekly@{t.subdomain}.test")
            _summary(t, teacher, total_xp=10)
            league = League.all_objects.create(
                tenant=t, tier_code="bronze_2", tier_rank=2,
                week_start_date=_week_start(),
            )
            LeagueMembership.all_objects.create(
                tenant=t, league=league, teacher=teacher, weekly_xp=50,
            )

        summary = close_league_week_task.apply().result
        self.assertEqual(summary["leagues_closed"], 2)


# ---------------------------------------------------------------------------
# 6. API — teacher & admin endpoints
# ---------------------------------------------------------------------------

@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class LeagueApiTest(TestCase):
    def setUp(self):
        self.tenant = _tenant(subdomain="leagueapi")
        self.teacher = _teacher(self.tenant, email="apit@lg.test")
        _summary(self.tenant, self.teacher, total_xp=100)
        self.admin = _admin(self.tenant)

        self.client = APIClient()
        self.host = f"{self.tenant.subdomain}.lms.com"

    def test_teacher_can_fetch_current_league(self):
        assign_teacher_to_league(self.teacher)
        self.client.force_authenticate(user=self.teacher)
        resp = self.client.get(
            "/api/v1/gamification/league/",
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertIn("tier_code", data)
        self.assertEqual(data["tier_code"], "bronze_1")
        self.assertIn("members", data)
        self.assertIn("week_start_date", data)

    def test_teacher_without_league_is_lazy_assigned(self):
        """Teacher who hasn't been assigned is auto-enrolled on first fetch."""
        self.client.force_authenticate(user=self.teacher)
        resp = self.client.get(
            "/api/v1/gamification/league/",
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        # Fresh teacher lands in bronze_1.
        self.assertEqual(data["tier_code"], "bronze_1")

    def test_opted_out_teacher_gets_empty_league_response(self):
        """Teacher who opted out of leagues sees tier_code=None."""
        _summary(self.tenant, self.teacher, league_opted_out=True)
        self.client.force_authenticate(user=self.teacher)
        resp = self.client.get(
            "/api/v1/gamification/league/",
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json().get("tier_code"))

    def test_teacher_only_sees_own_cohort(self):
        other_tenant = _tenant(subdomain="otherapi")
        other_teacher = _teacher(other_tenant, email="o@lg.test")
        _summary(other_tenant, other_teacher, total_xp=200)
        assign_teacher_to_league(other_teacher)

        assign_teacher_to_league(self.teacher)
        self.client.force_authenticate(user=self.teacher)
        resp = self.client.get(
            "/api/v1/gamification/league/",
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        member_emails = [m.get("teacher_email") for m in data["members"]]
        self.assertNotIn("o@lg.test", member_emails)

    def test_admin_overview_lists_all_leagues(self):
        assign_teacher_to_league(self.teacher)
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(
            "/api/v1/gamification/admin/leagues/",
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertIn("leagues", data)
        # At least one league visible
        self.assertGreaterEqual(len(data["leagues"]), 1)

    def test_teacher_league_history_returns_snapshots(self):
        league = League.all_objects.create(
            tenant=self.tenant, tier_code="silver_1", tier_rank=4,
            week_start_date=_week_start() - timedelta(days=7),
        )
        LeagueRankSnapshot.all_objects.create(
            tenant=self.tenant,
            league=league,
            teacher=self.teacher,
            tier_code="silver_1",
            tier_rank=4,
            week_start_date=_week_start() - timedelta(days=7),
            final_rank=3,
            weekly_xp=450,
            outcome="promote",
        )
        self.client.force_authenticate(user=self.teacher)
        resp = self.client.get(
            "/api/v1/gamification/league/history/",
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["history"]), 1)
        self.assertEqual(data["history"][0]["outcome"], "promote")


# ---------------------------------------------------------------------------
# 7. LeagueRankSnapshot unique constraint + crash-safe get_or_create
# ---------------------------------------------------------------------------

class LeagueSnapshotConstraintTest(TestCase):
    """
    Verify the unique constraint on LeagueRankSnapshot(teacher, week_start_date)
    and the crash-safe get_or_create behaviour introduced in the 2026-04-22
    backend-engineer entry (Fix 4).

    If close_league_week crashes AFTER writing snapshots but BEFORE setting
    league.closed_at, a re-run must not raise IntegrityError.
    """

    def setUp(self):
        from apps.progress.gamification_models import GamificationConfig
        self.tenant = _tenant(subdomain="snapconstraint")
        self.teacher = _teacher(self.tenant, email="snap@lg.test")
        _summary(self.tenant, self.teacher)
        GamificationConfig.objects.get_or_create(
            tenant=self.tenant,
            defaults={
                "league_cohort_size": 10,
                "league_promote_count": 3,
                "league_demote_count": 3,
                "leagues_enabled": True,
            },
        )
        self.week_start = _week_start()

    # ------------------------------------------------------------------
    # Test 1: Unique constraint at model level
    # ------------------------------------------------------------------

    def test_duplicate_snapshot_raises_integrity_error(self):
        """
        Creating two LeagueRankSnapshot rows for the same (teacher, week_start_date)
        must raise IntegrityError — enforced by the DB constraint added in
        migration 0021.
        """
        from django.db.utils import IntegrityError

        league = League.all_objects.create(
            tenant=self.tenant,
            tier_code="bronze_1",
            tier_rank=1,
            week_start_date=self.week_start,
        )
        LeagueRankSnapshot.all_objects.create(
            tenant=self.tenant,
            league=league,
            teacher=self.teacher,
            tier_code="bronze_1",
            tier_rank=1,
            week_start_date=self.week_start,
            final_rank=1,
            weekly_xp=100,
            outcome="hold",
        )
        with self.assertRaises(IntegrityError):
            LeagueRankSnapshot.all_objects.create(
                tenant=self.tenant,
                league=league,
                teacher=self.teacher,
                tier_code="bronze_1",
                tier_rank=1,
                week_start_date=self.week_start,
                final_rank=1,
                weekly_xp=100,
                outcome="hold",
            )

    # ------------------------------------------------------------------
    # Test 2: Crash-safe re-run — pre-existing snapshot does not block close
    # ------------------------------------------------------------------

    def test_close_week_crash_retry_does_not_raise_integrity_error(self):
        """
        Simulate a crash-and-retry scenario:

        1. Create an open League with one member (the teacher).
        2. Pre-write the LeagueRankSnapshot as if close_league_week had
           crashed after writing snapshots but before setting closed_at.
        3. Call close_league_week — it must complete without IntegrityError,
           using get_or_create semantics on the snapshot.

        This directly tests the `.create()` → `get_or_create()` change
        introduced alongside migration 0021.
        """
        league = League.all_objects.create(
            tenant=self.tenant,
            tier_code="bronze_1",
            tier_rank=1,
            week_start_date=self.week_start,
        )
        LeagueMembership.all_objects.create(
            tenant=self.tenant,
            league=league,
            teacher=self.teacher,
            weekly_xp=50,
        )
        # Simulate partial crash: snapshot already written, but league NOT closed.
        LeagueRankSnapshot.all_objects.create(
            tenant=self.tenant,
            league=league,
            teacher=self.teacher,
            tier_code="bronze_1",
            tier_rank=1,
            week_start_date=self.week_start,
            final_rank=1,
            weekly_xp=50,
            outcome="hold",
        )
        self.assertIsNone(league.closed_at)

        # Re-run close_league_week — must NOT raise.
        try:
            summary = close_league_week(
                tenant=self.tenant, week_start_date=self.week_start
            )
        except Exception as exc:  # noqa: BLE001
            self.fail(
                f"close_league_week raised {type(exc).__name__} on crash-retry: {exc}"
            )

        # League is now closed.
        league.refresh_from_db()
        self.assertIsNotNone(
            league.closed_at,
            "league.closed_at should be set after close_league_week completes",
        )
        # Summary: 1 league closed; 0 new snapshots (the existing one was reused).
        self.assertEqual(summary["leagues_closed"], 1)
        self.assertEqual(
            summary["snapshots_written"],
            0,
            "snapshots_written must be 0 when get_or_create finds the existing snapshot",
        )

    # ------------------------------------------------------------------
    # Test 3: Normal close still counts snapshots_written correctly
    # ------------------------------------------------------------------

    def test_close_week_counts_new_snapshots_correctly(self):
        """
        In the normal (no-crash) path, snapshots_written equals the number
        of members in the league — each is genuinely new.
        """
        league = League.all_objects.create(
            tenant=self.tenant,
            tier_code="silver_1",
            tier_rank=4,
            week_start_date=self.week_start,
        )
        t2 = _teacher(self.tenant, email="snap2@lg.test")
        _summary(self.tenant, t2)

        LeagueMembership.all_objects.create(
            tenant=self.tenant, league=league, teacher=self.teacher, weekly_xp=200,
        )
        LeagueMembership.all_objects.create(
            tenant=self.tenant, league=league, teacher=t2, weekly_xp=100,
        )

        summary = close_league_week(
            tenant=self.tenant, week_start_date=self.week_start
        )

        self.assertEqual(summary["leagues_closed"], 1)
        self.assertEqual(
            summary["snapshots_written"],
            2,
            "snapshots_written must equal number of league members on first run",
        )
