# apps/progress/gamification_teacher_views.py

import logging

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.decorators import teacher_or_admin, tenant_required
from utils.helpers import make_pagination_class
from utils.responses import error_response

from .gamification_engine import (
    get_or_create_config,
    spend_streak_freeze_token,
)
from .gamification_models import (
    BadgeDefinition,
    LeaderboardSnapshot,
    StreakFreezeLedger,
    StreakFreezeToken,
    TeacherBadge,
    TeacherStreak,
    TeacherXPSummary,
    XPTransaction,
)
from .gamification_serializers import (
    BadgeDefinitionSerializer,
    StreakFreezeLedgerSerializer,
    StreakFreezeTokenSerializer,
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


def _available_tokens_qs(teacher, now=None):
    """Unconsumed, unexpired tokens for ``teacher``."""
    from django.db.models import Q

    now = now or timezone.now()
    return StreakFreezeToken.all_objects.filter(
        teacher=teacher,
        consumed_at__isnull=True,
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_streak_freeze(request):
    """
    Use a streak freeze to protect the current streak.

    Prefers consuming a StreakFreezeToken from the teacher's inventory. Falls
    back to the legacy monthly-counter mechanism for backward compatibility.
    """
    config = get_or_create_config(request.tenant)

    streak, _ = TeacherStreak.all_objects.get_or_create(
        teacher=request.user,
        defaults={'tenant': request.tenant}
    )

    from datetime import timedelta
    today = timezone.localdate()

    # Preferred path: consume an inventory token.
    spent = spend_streak_freeze_token(
        request.user, description='Freeze applied to protect streak',
    )
    if spent is not None:
        streak.freeze_used_today = True
        streak.streak_frozen_until = today + timedelta(days=1)
        streak.save(update_fields=[
            'freeze_used_today', 'streak_frozen_until', 'updated_at',
        ])
        tokens_remaining = _available_tokens_qs(request.user).count()
        return Response({
            "success": True,
            "tokens_remaining": tokens_remaining,
            "freezes_remaining": tokens_remaining,  # legacy alias
        })

    # Legacy fallback: monthly counter (only if no tokens available).
    if streak.freeze_count_this_month >= config.streak_freeze_max:
        return error_response(
            f"No freezes remaining this month (max {config.streak_freeze_max}).",
            status_code=400,
        )

    if streak.freeze_used_today:
        return error_response("Freeze already used today.", status_code=400)

    streak.freeze_used_today = True
    streak.freeze_count_this_month += 1
    streak.streak_frozen_until = today + timedelta(days=1)
    streak.save(update_fields=[
        'freeze_used_today', 'freeze_count_this_month',
        'streak_frozen_until', 'updated_at',
    ])

    freezes_remaining = config.streak_freeze_max - streak.freeze_count_this_month
    return Response({
        "success": True,
        "freezes_remaining": freezes_remaining,
        "tokens_remaining": 0,
    })


# ---------------------------------------------------------------------------
# Streak Freeze — Inventory / Use / Weekend Mode / Ledger
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_streak_freeze_inventory(request):
    """
    Return the teacher's current streak-freeze token inventory and mode state.
    """
    config = get_or_create_config(request.tenant)
    streak, _ = TeacherStreak.all_objects.get_or_create(
        teacher=request.user,
        defaults={'tenant': request.tenant},
    )

    available_qs = _available_tokens_qs(request.user)
    tokens = StreakFreezeTokenSerializer(
        available_qs.order_by('earned_at'),
        many=True,
    ).data

    in_grace_period = bool(
        streak.grace_period_ends_at
        and streak.grace_period_ends_at > timezone.now()
    )

    return Response({
        "token_count": available_qs.count(),
        "max_inventory": config.freeze_token_max_inventory,
        "earn_every_n_days": config.freeze_token_earn_every_n_days,
        "expires_days": config.freeze_token_expires_days,
        "tokens": tokens,
        "weekend_mode_enabled": streak.weekend_mode_enabled,
        "weekend_mode_available": config.weekend_mode_available,
        "grace_period_hours": config.grace_period_hours,
        "in_grace_period": in_grace_period,
        "grace_period_ends_at": streak.grace_period_ends_at,
        "current_streak": streak.current_streak,
        "longest_streak": streak.longest_streak,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_streak_freeze_use(request):
    """
    Consume one streak-freeze token from the teacher's inventory to protect
    the current streak.
    """
    streak, _ = TeacherStreak.all_objects.get_or_create(
        teacher=request.user,
        defaults={'tenant': request.tenant},
    )

    spent = spend_streak_freeze_token(
        request.user, description='Token consumed via /streak-freeze/use/',
    )
    if spent is None:
        return error_response(
            "No streak freeze tokens available.",
            status_code=400,
        )

    from datetime import timedelta
    today = timezone.localdate()
    streak.freeze_used_today = True
    streak.streak_frozen_until = today + timedelta(days=1)
    streak.save(update_fields=[
        'freeze_used_today', 'streak_frozen_until', 'updated_at',
    ])

    tokens_remaining = _available_tokens_qs(request.user).count()
    return Response({
        "success": True,
        "tokens_remaining": tokens_remaining,
        "token_id": str(spent.id),
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_streak_freeze_weekend_mode(request):
    """
    Enable or disable weekend mode for the teacher's streak.

    Body: ``{"enabled": true|false}``.
    """
    config = get_or_create_config(request.tenant)
    enabled = bool(request.data.get('enabled', False))
    if enabled and not config.weekend_mode_available:
        return error_response(
            "Weekend mode is disabled for this tenant.",
            status_code=400,
        )

    streak, _ = TeacherStreak.all_objects.get_or_create(
        teacher=request.user,
        defaults={'tenant': request.tenant},
    )
    streak.weekend_mode_enabled = enabled
    streak.save(update_fields=['weekend_mode_enabled', 'updated_at'])

    return Response({
        "success": True,
        "weekend_mode_enabled": streak.weekend_mode_enabled,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_streak_freeze_ledger(request):
    """Paginated history of the teacher's streak-freeze events."""
    entries = StreakFreezeLedger.all_objects.filter(
        tenant=request.tenant,
        teacher=request.user,
    ).order_by('-created_at')

    PaginationCls = make_pagination_class(page_size=25, max_page_size=100)
    paginator = PaginationCls()
    page = paginator.paginate_queryset(entries, request)
    data = StreakFreezeLedgerSerializer(page, many=True).data
    return paginator.get_paginated_response(data)
