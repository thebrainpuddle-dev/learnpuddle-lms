# apps/progress/league_engine.py
#
# Engine for the 10-tier League Leaderboard system (TASK-016).
#
# Responsibilities:
#   - Lazy-assign teachers to leagues on activity
#   - Weekly close: rank members, snapshot, promote/demote, open next week's
#     cohorts
#   - Tenant-scoped and tenant-isolated at every step

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from .gamification_engine import get_or_create_config
from .gamification_models import TeacherXPSummary
from .league_models import (
    LEAGUE_BOTTOM_RANK,
    LEAGUE_TIER_BY_RANK,
    LEAGUE_TOP_RANK,
    League,
    LeagueMembership,
    LeagueRankSnapshot,
    get_tier_by_rank,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso_week_start(today: Optional[date] = None) -> date:
    """Return the Monday of the ISO week containing ``today`` (UTC).

    Always uses UTC regardless of the ``TIME_ZONE`` Django setting so that
    league-week boundaries are consistent across tenants and server locale changes.
    """
    today = today or timezone.now().astimezone(timezone.utc).date()
    return today - timedelta(days=today.weekday())


def _is_teacher_eligible(teacher) -> bool:
    """
    Check whether a teacher should be enrolled in leagues.

    Returns False if:
      - Teacher has no tenant,
      - Gamification is inactive,
      - Leagues are disabled tenant-wide,
      - Teacher's ``TeacherXPSummary.opted_out`` is True,
      - Teacher's ``TeacherXPSummary.league_opted_out`` is True,
      - Teacher has the SUPER_ADMIN or SCHOOL_ADMIN role (they don't compete).
    """
    tenant = getattr(teacher, "tenant", None)
    if not tenant:
        return False

    role = getattr(teacher, "role", None)
    if role in ("SUPER_ADMIN", "SCHOOL_ADMIN"):
        return False

    config = get_or_create_config(tenant)
    if not config.is_active or not config.leagues_enabled:
        return False

    summary = (
        TeacherXPSummary.all_objects.filter(teacher=teacher).first()
    )
    if summary is None:
        # No summary yet — create a default one so downstream code works.
        summary, _ = TeacherXPSummary.all_objects.get_or_create(
            teacher=teacher, defaults={"tenant": tenant},
        )

    if summary.opted_out:
        return False
    if summary.league_opted_out:
        return False
    return True


# ---------------------------------------------------------------------------
# Lazy assignment — called on first activity of a teacher each week.
# ---------------------------------------------------------------------------

def get_current_league_for_teacher(teacher, week_start_date: Optional[date] = None):
    """Return the teacher's active (not-closed) league for the given week, or None."""
    week_start_date = week_start_date or _iso_week_start()
    return (
        League.all_objects.filter(
            tenant=teacher.tenant,
            week_start_date=week_start_date,
            memberships__teacher=teacher,
            closed_at__isnull=True,
        )
        .distinct()
        .first()
    )


def get_or_create_tier_league(tenant, tier_rank: int, week_start_date: date):
    """
    Return a League cohort in the given tier that still has room, creating one
    if none exists.

    Uses ``GamificationConfig.league_cohort_size`` as the cap.
    """
    config = get_or_create_config(tenant)
    tier = get_tier_by_rank(tier_rank)

    # Find any open (not-closed) league in this tier/week with room.
    existing = (
        League.all_objects.filter(
            tenant=tenant,
            tier_code=tier["code"],
            tier_rank=tier["rank"],
            week_start_date=week_start_date,
            closed_at__isnull=True,
        )
        .annotate(member_count=Count("memberships"))
        .filter(member_count__lt=config.league_cohort_size)
        .order_by("created_at")
        .first()
    )
    if existing:
        return existing

    # All full (or none exist) → open a fresh cohort.
    return League.all_objects.create(
        tenant=tenant,
        tier_code=tier["code"],
        tier_rank=tier["rank"],
        week_start_date=week_start_date,
    )


@transaction.atomic
def assign_teacher_to_league(teacher, week_start_date: Optional[date] = None):
    """
    Ensure the teacher is enrolled in a league cohort for the given week.

    If eligible and not yet assigned: assigns to bottom tier (new teachers) or
    whatever tier their most-recent snapshot promoted/demoted them to.

    Returns the LeagueMembership, or None if the teacher isn't eligible.
    """
    if not _is_teacher_eligible(teacher):
        return None

    week_start_date = week_start_date or _iso_week_start()

    existing = LeagueMembership.all_objects.filter(
        tenant=teacher.tenant,
        teacher=teacher,
        league__week_start_date=week_start_date,
        league__tenant=teacher.tenant,
    ).first()
    if existing:
        return existing

    tier_rank = _resolve_starting_tier_rank(teacher, week_start_date)
    league = get_or_create_tier_league(
        teacher.tenant, tier_rank, week_start_date,
    )
    membership = LeagueMembership.all_objects.create(
        tenant=teacher.tenant,
        league=league,
        teacher=teacher,
        weekly_xp=0,
    )
    logger.info(
        "Assigned teacher %s to league %s (tier=%s, week=%s)",
        teacher.id, league.id, league.tier_code, week_start_date,
    )
    return membership


def _resolve_starting_tier_rank(teacher, week_start_date: date) -> int:
    """
    Determine which tier a teacher belongs in at the start of ``week_start_date``.

    Looks at the teacher's most-recent ``LeagueRankSnapshot``:
      - If the outcome was 'promote' → one tier up (clamped to top).
      - If 'demote' → one tier down (clamped to bottom).
      - If 'hold' → same tier.
      - If no history → bottom tier (Bronze I).
    """
    last_snap = (
        LeagueRankSnapshot.all_objects.filter(
            tenant=teacher.tenant, teacher=teacher,
        )
        .order_by("-week_start_date")
        .first()
    )
    if last_snap is None:
        return LEAGUE_BOTTOM_RANK

    base = last_snap.tier_rank
    if last_snap.outcome == "promote":
        return min(LEAGUE_TOP_RANK, base + 1)
    if last_snap.outcome == "demote":
        return max(LEAGUE_BOTTOM_RANK, base - 1)
    return base


# ---------------------------------------------------------------------------
# Weekly close — called from Celery beat
# ---------------------------------------------------------------------------

def _scale_count(configured: int, configured_cohort: int, actual_size: int) -> int:
    """
    Scale a promote/demote count for cohorts smaller than configured.

    For cohorts at or above the configured size, return ``configured``.
    For smaller cohorts, scale proportionally and round; below 3 members, no
    one moves.
    """
    if actual_size >= configured_cohort:
        return configured
    if actual_size < 3:
        return 0
    scaled = round(configured * actual_size / configured_cohort)
    return max(1, scaled)


@transaction.atomic
def close_league_week(
    tenant,
    week_start_date: Optional[date] = None,
):
    """
    Close all open leagues for a tenant & week. Idempotent.

    Steps:
      1. Find all open (closed_at IS NULL) League rows for this tenant/week.
      2. For each league:
         a. Rank members by ``weekly_xp`` desc (ties: total XP desc, then
            membership created_at asc).
         b. Compute promote/hold/demote buckets from config.
         c. Write LeagueRankSnapshot for each member.
         d. Create next-week membership for each teacher in the shifted tier
            (clamped at [1,10]).
         e. Set ``league.closed_at``.

    Returns a summary dict.
    """
    week_start_date = week_start_date or _iso_week_start()
    next_week = week_start_date + timedelta(days=7)
    config = get_or_create_config(tenant)

    summary = {
        "tenant_id": str(tenant.id),
        "week_start_date": week_start_date.isoformat(),
        "leagues_closed": 0,
        "snapshots_written": 0,
        "promoted": 0,
        "held": 0,
        "demoted": 0,
    }

    leagues = League.all_objects.filter(
        tenant=tenant,
        week_start_date=week_start_date,
        closed_at__isnull=True,
    )

    if not leagues.exists():
        return summary

    now = timezone.now()

    for league in leagues:
        memberships = list(
            LeagueMembership.all_objects.filter(league=league)
            .select_related("teacher")
        )
        if not memberships:
            league.closed_at = now
            league.save(update_fields=["closed_at", "updated_at"])
            summary["leagues_closed"] += 1
            continue

        # Rank: weekly_xp desc, total_xp desc (from XPSummary), then created_at asc.
        total_xp_map = {
            s.teacher_id: s.total_xp
            for s in TeacherXPSummary.all_objects.filter(
                tenant=tenant,
                teacher_id__in=[m.teacher_id for m in memberships],
            )
        }
        memberships.sort(
            key=lambda m: (
                -m.weekly_xp,
                -total_xp_map.get(m.teacher_id, 0),
                m.created_at,
            )
        )

        size = len(memberships)
        promote_n = _scale_count(
            config.league_promote_count, config.league_cohort_size, size,
        )
        demote_n = _scale_count(
            config.league_demote_count, config.league_cohort_size, size,
        )
        # Guard against overlap on very small cohorts.
        if promote_n + demote_n > size:
            overlap = promote_n + demote_n - size
            demote_n = max(0, demote_n - overlap)

        promote_set = set(range(promote_n))
        demote_set = set(range(size - demote_n, size))

        for idx, m in enumerate(memberships):
            if idx in promote_set:
                outcome = "promote"
                new_tier_rank = min(LEAGUE_TOP_RANK, league.tier_rank + 1)
            elif idx in demote_set:
                outcome = "demote"
                new_tier_rank = max(LEAGUE_BOTTOM_RANK, league.tier_rank - 1)
            else:
                outcome = "hold"
                new_tier_rank = league.tier_rank

            m.final_rank = idx + 1
            m.outcome = outcome
            m.save(update_fields=["final_rank", "outcome", "updated_at"])

            # Use get_or_create so that a partial crash-then-retry doesn't
            # raise IntegrityError from the unique_league_rank_snapshot_per_teacher_per_week
            # constraint added in migration 0021.
            _snapshot, _snap_created = LeagueRankSnapshot.all_objects.get_or_create(
                teacher=m.teacher,
                week_start_date=week_start_date,
                defaults={
                    "tenant": tenant,
                    "league": league,
                    "tier_code": league.tier_code,
                    "tier_rank": league.tier_rank,
                    "final_rank": idx + 1,
                    "weekly_xp": m.weekly_xp,
                    "outcome": outcome,
                },
            )
            if _snap_created:
                summary["snapshots_written"] += 1
            if outcome == "promote":
                summary["promoted"] += 1
                # TASK-019: Puddle Coins for promotion. Idempotent against
                # re-running close_league_week for the same (teacher, league).
                try:
                    from .coin_engine import earn_coins

                    earn_coins(
                        teacher=m.teacher,
                        reason="league_promote",
                        reference_id=league.id,
                        reference_type="league",
                        description=(
                            f"Promoted from {league.tier_code} "
                            f"(week {week_start_date})"
                        ),
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "earn_coins failed on league promotion teacher=%s league=%s",
                        m.teacher_id, league.id,
                    )
            elif outcome == "demote":
                summary["demoted"] += 1
            else:
                summary["held"] += 1

            # Open next week's membership in the resolved tier.
            next_league = get_or_create_tier_league(
                tenant, new_tier_rank, next_week,
            )
            LeagueMembership.all_objects.get_or_create(
                tenant=tenant,
                league=next_league,
                teacher=m.teacher,
                defaults={"weekly_xp": 0},
            )

        league.closed_at = now
        league.save(update_fields=["closed_at", "updated_at"])
        summary["leagues_closed"] += 1

    logger.info("close_league_week complete: %s", summary)
    return summary
