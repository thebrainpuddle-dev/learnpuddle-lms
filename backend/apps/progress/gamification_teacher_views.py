# apps/progress/gamification_teacher_views.py

import logging

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.decorators import teacher_or_admin, tenant_required
from utils.helpers import make_pagination_class
from utils.responses import error_response

from .gamification_engine import get_or_create_config
from .gamification_models import (
    BadgeDefinition,
    LeaderboardSnapshot,
    TeacherBadge,
    TeacherStreak,
    TeacherXPSummary,
    XPTransaction,
)
from .gamification_serializers import (
    BadgeDefinitionSerializer,
    TeacherBadgeSerializer,
    TeacherXPSummarySerializer,
    XPTransactionSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# XP Summary
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_xp_summary(request):
    """
    Get the current teacher's XP summary including level, streaks, badges.
    Returns the TeacherXPSummary with computed fields.
    """
    summary, created = TeacherXPSummary.all_objects.get_or_create(
        teacher=request.user,
        defaults={'tenant': request.tenant}
    )
    if created:
        summary.refresh_from_transactions()
    serializer = TeacherXPSummarySerializer(summary)
    return Response(serializer.data)


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_leaderboard(request):
    """
    Get the leaderboard visible to teachers.
    Supports ?period= (weekly, monthly, all_time). Defaults to weekly.

    Uses LeaderboardSnapshot for data. If config.leaderboard_anonymize is True,
    show initials instead of full names.
    """
    config = get_or_create_config(request.tenant)
    if not config.leaderboard_enabled:
        return error_response("Leaderboard is disabled.", status_code=400)

    period = request.GET.get('period', 'weekly')
    if period not in ('weekly', 'monthly', 'all_time'):
        period = 'weekly'

    # Get latest snapshot date for this period
    latest = LeaderboardSnapshot.objects.filter(
        tenant=request.tenant, period=period
    ).order_by('-snapshot_date').values_list('snapshot_date', flat=True).first()

    if not latest:
        return Response({"period": period, "entries": [], "snapshot_date": None})

    snapshots = LeaderboardSnapshot.objects.filter(
        tenant=request.tenant, period=period, snapshot_date=latest
    ).select_related('teacher').order_by('rank')[:100]

    entries = []
    for snap in snapshots:
        name = snap.teacher.get_full_name() or snap.teacher.email
        if config.leaderboard_anonymize:
            parts = name.split()
            name = ''.join(p[0].upper() for p in parts if p)

        # Get summary and streak
        try:
            summary = snap.teacher.xp_summary
            level = summary.level
            level_name = summary.level_name
        except TeacherXPSummary.DoesNotExist:
            level = 1
            level_name = 'Associate Educator'

        badge_count = TeacherBadge.all_objects.filter(teacher=snap.teacher).count()
        try:
            streak = snap.teacher.streak.current_streak
        except TeacherStreak.DoesNotExist:
            streak = 0

        entries.append({
            "rank": snap.rank,
            "teacher_id": str(snap.teacher_id),
            "teacher_name": name,
            "teacher_email": snap.teacher.email if not config.leaderboard_anonymize else "",
            "total_xp": snap.xp_total,
            "xp_period": snap.xp_period,
            "level": level,
            "level_name": level_name,
            "badge_count": badge_count,
            "current_streak": streak,
        })

    return Response({
        "period": period,
        "entries": entries,
        "snapshot_date": latest.isoformat(),
    })


# ---------------------------------------------------------------------------
# Badge Definitions (teacher-accessible, read-only)
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_badge_definitions(request):
    """List all active badge definitions for the tenant (read-only for teachers)."""
    qs = BadgeDefinition.objects.filter(is_active=True).order_by('sort_order', 'name')
    serializer = BadgeDefinitionSerializer(qs, many=True)
    return Response({"results": serializer.data})


# ---------------------------------------------------------------------------
# Badges
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_badges(request):
    """Get all badges earned by the current teacher."""
    teacher_badges_qs = TeacherBadge.all_objects.filter(
        teacher=request.user
    ).select_related('badge').order_by('-awarded_at')

    serializer = TeacherBadgeSerializer(teacher_badges_qs, many=True)
    return Response({"results": serializer.data})


# ---------------------------------------------------------------------------
# XP History
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_xp_history(request):
    """Get XP transaction history for the current teacher."""
    qs = XPTransaction.all_objects.filter(
        teacher=request.user
    ).order_by('-created_at')

    paginator = make_pagination_class(25, 100)()
    page = paginator.paginate_queryset(qs, request)
    if page is not None:
        serializer = XPTransactionSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    serializer = XPTransactionSerializer(qs, many=True)
    return Response({"results": serializer.data})


# ---------------------------------------------------------------------------
# Opt-out / Opt-in
# ---------------------------------------------------------------------------


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_opt_out(request):
    """Opt out of gamification. Hides XP, badges, and leaderboard."""
    config = get_or_create_config(request.tenant)
    if not config.opt_out_allowed:
        return error_response("Opt-out is not allowed by your school.", status_code=403)

    summary, _ = TeacherXPSummary.all_objects.get_or_create(
        teacher=request.user,
        defaults={'tenant': request.tenant}
    )
    summary.opted_out = True
    summary.save(update_fields=['opted_out', 'updated_at'])
    return Response({"opted_out": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_opt_in(request):
    """Opt back into gamification."""
    summary, _ = TeacherXPSummary.all_objects.get_or_create(
        teacher=request.user,
        defaults={'tenant': request.tenant}
    )
    summary.opted_out = False
    summary.save(update_fields=['opted_out', 'updated_at'])
    return Response({"opted_out": False})


# ---------------------------------------------------------------------------
# Streak Freeze
# ---------------------------------------------------------------------------


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_streak_freeze(request):
    """Use a streak freeze to protect the current streak."""
    config = get_or_create_config(request.tenant)

    streak, _ = TeacherStreak.all_objects.get_or_create(
        teacher=request.user,
        defaults={'tenant': request.tenant}
    )

    if streak.freeze_count_this_month >= config.streak_freeze_max:
        return error_response(
            f"No freezes remaining this month (max {config.streak_freeze_max}).",
            status_code=400,
        )

    if streak.freeze_used_today:
        return error_response("Freeze already used today.", status_code=400)

    from datetime import timedelta
    today = timezone.localdate()
    streak.freeze_used_today = True
    streak.freeze_count_this_month += 1
    streak.streak_frozen_until = today + timedelta(days=1)
    streak.save(update_fields=['freeze_used_today', 'freeze_count_this_month', 'streak_frozen_until', 'updated_at'])

    freezes_remaining = config.streak_freeze_max - streak.freeze_count_this_month
    return Response({
        "success": True,
        "freezes_remaining": freezes_remaining,
    })
