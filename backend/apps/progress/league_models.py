# apps/progress/league_models.py
#
# 10-tier League models for the LearnPuddle gamification system (TASK-016).
#
# League         — one cohort per tenant × tier × ISO-week.
# LeagueMembership — teacher ∈ league + weekly XP + final rank.
# LeagueRankSnapshot — immutable end-of-week record.

import uuid

from django.db import models

from utils.tenant_manager import TenantManager


# ---------------------------------------------------------------------------
# Tier taxonomy — 10 tiers, ascending prestige.
#
# Index:
#   1 Bronze I         (bottom)
#   2 Bronze II
#   3 Bronze III
#   4 Silver I
#   5 Silver II
#   6 Silver III
#   7 Gold I
#   8 Gold II
#   9 Gold III
#  10 Diamond          (top)
# ---------------------------------------------------------------------------

LEAGUE_TIERS = [
    {"code": "bronze_1",  "name": "Bronze I",    "rank": 1},
    {"code": "bronze_2",  "name": "Bronze II",   "rank": 2},
    {"code": "bronze_3",  "name": "Bronze III",  "rank": 3},
    {"code": "silver_1",  "name": "Silver I",    "rank": 4},
    {"code": "silver_2",  "name": "Silver II",   "rank": 5},
    {"code": "silver_3",  "name": "Silver III",  "rank": 6},
    {"code": "gold_1",    "name": "Gold I",      "rank": 7},
    {"code": "gold_2",    "name": "Gold II",     "rank": 8},
    {"code": "gold_3",    "name": "Gold III",    "rank": 9},
    {"code": "diamond",   "name": "Diamond",     "rank": 10},
]

LEAGUE_TIER_CHOICES = [(t["code"], t["name"]) for t in LEAGUE_TIERS]

LEAGUE_TIER_BY_CODE = {t["code"]: t for t in LEAGUE_TIERS}
LEAGUE_TIER_BY_RANK = {t["rank"]: t for t in LEAGUE_TIERS}

LEAGUE_OUTCOME_CHOICES = [
    ("promote", "Promote"),
    ("hold", "Hold"),
    ("demote", "Demote"),
]

LEAGUE_BOTTOM_RANK = 1
LEAGUE_TOP_RANK = 10


def get_tier_by_rank(rank: int):
    """Return the tier dict for a given 1-based rank, clamped to [1,10]."""
    rank = max(LEAGUE_BOTTOM_RANK, min(LEAGUE_TOP_RANK, rank))
    return LEAGUE_TIER_BY_RANK[rank]


# ---------------------------------------------------------------------------
# League (cohort)
# ---------------------------------------------------------------------------

class League(models.Model):
    """
    A single weekly cohort in a given tier, for a given tenant.

    Multiple leagues can exist for the same (tenant, tier, week) when the
    tenant has more than ``league_cohort_size`` members in that tier — each
    additional block of members gets its own League row.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="leagues",
    )
    tier_code = models.CharField(max_length=20, choices=LEAGUE_TIER_CHOICES)
    tier_rank = models.PositiveSmallIntegerField(
        help_text="Denormalized 1..10 for fast sorting.",
    )
    week_start_date = models.DateField(
        help_text="ISO-week Monday on which this league opened (UTC).",
    )
    closed_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Set when the weekly-reset task runs and snapshots this league.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "progress_leagues"
        indexes = [
            models.Index(fields=["tenant", "week_start_date", "tier_rank"]),
            models.Index(fields=["tenant", "closed_at"]),
        ]
        ordering = ["-week_start_date", "tier_rank"]

    def __str__(self):
        return (
            f"League[{self.tier_code}] tenant={self.tenant_id} "
            f"week={self.week_start_date}"
        )


# ---------------------------------------------------------------------------
# LeagueMembership
# ---------------------------------------------------------------------------

class LeagueMembership(models.Model):
    """
    A teacher's membership in a specific League cohort.

    One row per teacher per (tenant, week_start_date). Tracks the XP the
    teacher has earned *during this league's week*, and — after the weekly
    reset runs — the final rank and outcome.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="league_memberships",
    )
    league = models.ForeignKey(
        League,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    teacher = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="league_memberships",
    )
    weekly_xp = models.PositiveIntegerField(default=0)
    final_rank = models.PositiveIntegerField(null=True, blank=True)
    outcome = models.CharField(
        max_length=10,
        choices=LEAGUE_OUTCOME_CHOICES,
        null=True, blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "progress_league_memberships"
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "league"],
                name="uniq_league_membership_per_teacher_per_league",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "league", "weekly_xp"]),
            models.Index(fields=["tenant", "teacher"]),
        ]

    def __str__(self):
        return (
            f"Membership teacher={self.teacher_id} "
            f"league={self.league_id} xp={self.weekly_xp}"
        )


# ---------------------------------------------------------------------------
# LeagueRankSnapshot
# ---------------------------------------------------------------------------

class LeagueRankSnapshot(models.Model):
    """
    Immutable end-of-week record of how a teacher finished in a league.

    Written by the weekly-reset task. Never mutated.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="league_rank_snapshots",
    )
    league = models.ForeignKey(
        League,
        on_delete=models.CASCADE,
        related_name="snapshots",
    )
    teacher = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="league_rank_snapshots",
    )
    tier_code = models.CharField(max_length=20, choices=LEAGUE_TIER_CHOICES)
    tier_rank = models.PositiveSmallIntegerField()
    week_start_date = models.DateField()
    final_rank = models.PositiveIntegerField()
    weekly_xp = models.PositiveIntegerField(default=0)
    outcome = models.CharField(max_length=10, choices=LEAGUE_OUTCOME_CHOICES)

    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "progress_league_rank_snapshots"
        ordering = ["-week_start_date", "tier_rank", "final_rank"]
        indexes = [
            models.Index(fields=["tenant", "teacher", "-week_start_date"]),
            models.Index(fields=["tenant", "week_start_date", "tier_rank"]),
        ]
        constraints = [
            # Defence-in-depth: the weekly-reset task should only ever write one
            # snapshot per teacher per week, but enforce it at the DB level so a
            # double-run or race doesn't produce silent duplicates.
            models.UniqueConstraint(
                fields=["teacher", "week_start_date"],
                name="unique_league_rank_snapshot_per_teacher_per_week",
            ),
        ]

    def __str__(self):
        return (
            f"Snapshot teacher={self.teacher_id} "
            f"tier={self.tier_code} rank={self.final_rank} "
            f"outcome={self.outcome}"
        )
