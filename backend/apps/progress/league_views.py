# apps/progress/league_views.py
#
# API endpoints for the 10-tier League Leaderboard system (TASK-016).

import logging

from django.db.models import Count
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.decorators import admin_only, teacher_or_admin, tenant_required

from .gamification_engine import get_or_create_config
from .gamification_models import TeacherXPSummary
from .league_engine import (
    _iso_week_start,
    assign_teacher_to_league,
    get_current_league_for_teacher,
)
from .league_models import (
    LEAGUE_TIER_BY_CODE,
    League,
    LeagueMembership,
    LeagueRankSnapshot,
)

logger = logging.getLogger(__name__)


def _serialize_member(membership, anonymize: bool) -> dict:
    teacher = membership.teacher
    name = teacher.get_full_name() or teacher.email
    if anonymize:
        parts = name.split()
        name = "".join(p[0].upper() for p in parts if p)
    return {
        "teacher_id": str(teacher.id),
        "teacher_name": name,
        "teacher_email": "" if anonymize else teacher.email,
        "weekly_xp": membership.weekly_xp,
        "final_rank": membership.final_rank,
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_current_league(request):
    """
    Return the current teacher's active league cohort for this ISO week.

    Response shape:
      {
        "tier_code": "silver_2" | None,
        "tier_name": "Silver II",
        "tier_rank": 5,
        "week_start_date": "2026-04-20",
        "members": [ { teacher_id, teacher_name, weekly_xp, final_rank }, ... ],
        "promote_count": 7,
        "demote_count": 7,
        "cohort_size": 30
      }
    """
    config = get_or_create_config(request.tenant)
    if not config.leagues_enabled:
        return Response(
            {"detail": "Leagues are disabled for this tenant."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    week_start = _iso_week_start()

    # Lazy-assign on read so teachers always see a cohort.
    assign_teacher_to_league(request.user, week_start_date=week_start)

    league = get_current_league_for_teacher(request.user, week_start)
    if not league:
        return Response({
            "tier_code": None,
            "tier_name": None,
            "tier_rank": None,
            "week_start_date": week_start.isoformat(),
            "members": [],
            "promote_count": config.league_promote_count,
            "demote_count": config.league_demote_count,
            "cohort_size": config.league_cohort_size,
        })

    members = (
        LeagueMembership.all_objects.filter(league=league)
        .select_related("teacher")
        .order_by("-weekly_xp", "created_at")
    )
    tier = LEAGUE_TIER_BY_CODE.get(league.tier_code, {})
    return Response({
        "tier_code": league.tier_code,
        "tier_name": tier.get("name"),
        "tier_rank": league.tier_rank,
        "week_start_date": league.week_start_date.isoformat(),
        "members": [
            _serialize_member(m, config.leaderboard_anonymize) for m in members
        ],
        "promote_count": config.league_promote_count,
        "demote_count": config.league_demote_count,
        "cohort_size": config.league_cohort_size,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_league_history(request):
    """
    Return the teacher's league rank snapshots, newest first.
    """
    snapshots = LeagueRankSnapshot.all_objects.filter(
        tenant=request.tenant, teacher=request.user,
    ).order_by("-week_start_date")[:52]  # up to a year

    data = [
        {
            "week_start_date": s.week_start_date.isoformat(),
            "tier_code": s.tier_code,
            "tier_name": LEAGUE_TIER_BY_CODE.get(s.tier_code, {}).get("name"),
            "tier_rank": s.tier_rank,
            "final_rank": s.final_rank,
            "weekly_xp": s.weekly_xp,
            "outcome": s.outcome,
        }
        for s in snapshots
    ]
    return Response({"history": data})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def admin_leagues_overview(request):
    """
    Admin view: one row per current (not-closed) league in the tenant with
    member count.
    """
    week_start = _iso_week_start()

    leagues = (
        League.all_objects.filter(
            tenant=request.tenant,
            week_start_date=week_start,
            closed_at__isnull=True,
        )
        .annotate(member_count=Count("memberships"))
        .order_by("tier_rank", "created_at")
    )

    data = [
        {
            "league_id": str(lg.id),
            "tier_code": lg.tier_code,
            "tier_name": LEAGUE_TIER_BY_CODE.get(lg.tier_code, {}).get("name"),
            "tier_rank": lg.tier_rank,
            "week_start_date": lg.week_start_date.isoformat(),
            "member_count": lg.member_count,
        }
        for lg in leagues
    ]
    return Response({"week_start_date": week_start.isoformat(), "leagues": data})
