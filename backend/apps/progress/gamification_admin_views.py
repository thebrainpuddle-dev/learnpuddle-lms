# apps/progress/gamification_admin_views.py

import logging

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.users.models import User
from utils.decorators import admin_only, tenant_required
from utils.helpers import make_pagination_class
from utils.responses import error_response

from .gamification_models import (
    BadgeDefinition,
    GamificationConfig,
    TeacherBadge,
    TeacherStreak,
    TeacherXPSummary,
    XPTransaction,
)
from .gamification_serializers import (
    BadgeDefinitionCreateSerializer,
    BadgeDefinitionSerializer,
    GamificationConfigSerializer,
    LeaderboardEntrySerializer,
    XPAdjustSerializer,
    XPTransactionSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GamificationConfig (admin only)
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def gamification_config_get(request):
    """Get or create the gamification config for the current tenant."""
    config, _ = GamificationConfig.objects.get_or_create(tenant=request.tenant)
    serializer = GamificationConfigSerializer(config)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def gamification_config_update(request):
    """Update the gamification config."""
    config, _ = GamificationConfig.objects.get_or_create(tenant=request.tenant)
    serializer = GamificationConfigSerializer(config, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# BadgeDefinition CRUD (admin only)
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def badge_list(request):
    """List all badge definitions for the tenant."""
    qs = BadgeDefinition.objects.all()

    paginator = make_pagination_class(25, 100)()
    page = paginator.paginate_queryset(qs, request)
    if page is not None:
        serializer = BadgeDefinitionSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    serializer = BadgeDefinitionSerializer(qs, many=True)
    return Response({"results": serializer.data}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def badge_create(request):
    """Create a new badge definition."""
    serializer = BadgeDefinitionCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    badge = BadgeDefinition(tenant=request.tenant, **serializer.validated_data)
    badge.save()
    return Response(
        BadgeDefinitionSerializer(badge).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def badge_update(request, badge_id):
    """Update a badge definition."""
    badge = get_object_or_404(BadgeDefinition, id=badge_id, tenant=request.tenant)
    serializer = BadgeDefinitionCreateSerializer(badge, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    for attr, value in serializer.validated_data.items():
        setattr(badge, attr, value)
    badge.save()
    return Response(
        BadgeDefinitionSerializer(badge).data,
        status=status.HTTP_200_OK,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def badge_delete(request, badge_id):
    """Delete a badge definition."""
    badge = get_object_or_404(BadgeDefinition, id=badge_id, tenant=request.tenant)
    badge.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Leaderboard (admin only)
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def admin_leaderboard(request):
    """
    Get leaderboard data for the current tenant.

    Query params:
      - period: weekly | monthly | all_time (default: all_time)
    """
    period = request.GET.get('period', 'all_time')

    # Determine sort field based on period
    if period == 'weekly':
        sort_field = '-xp_this_week'
    elif period == 'monthly':
        sort_field = '-xp_this_month'
    else:
        sort_field = '-total_xp'

    # Fetch config for anonymization setting
    config, _ = GamificationConfig.objects.get_or_create(tenant=request.tenant)
    anonymize = config.leaderboard_anonymize

    # Query all non-opted-out summaries ordered by the relevant XP field
    summaries = (
        TeacherXPSummary.objects
        .filter(opted_out=False)
        .select_related('teacher')
        .order_by(sort_field)
    )

    entries = []
    for rank, summary in enumerate(summaries, start=1):
        # Badge count
        badge_count = TeacherBadge.all_objects.filter(
            teacher=summary.teacher,
        ).count()

        # Streak
        try:
            streak = TeacherStreak.all_objects.get(teacher=summary.teacher)
            current_streak = streak.current_streak
        except TeacherStreak.DoesNotExist:
            current_streak = 0

        # Teacher display name
        if anonymize:
            full_name = summary.teacher.get_full_name()
            if full_name and full_name.strip():
                parts = full_name.strip().split()
                teacher_name = ''.join(p[0].upper() for p in parts if p)
            else:
                teacher_name = summary.teacher.email[0].upper()
        else:
            teacher_name = summary.teacher.get_full_name() or summary.teacher.email

        # Period XP
        if period == 'weekly':
            xp_period = summary.xp_this_week
        elif period == 'monthly':
            xp_period = summary.xp_this_month
        else:
            xp_period = summary.total_xp

        entries.append({
            'rank': rank,
            'teacher_id': summary.teacher_id,
            'teacher_name': teacher_name,
            'teacher_email': summary.teacher.email if not anonymize else '',
            'total_xp': summary.total_xp,
            'xp_period': xp_period,
            'level': summary.level,
            'level_name': summary.level_name,
            'badge_count': badge_count,
            'current_streak': current_streak,
        })

    serializer = LeaderboardEntrySerializer(entries, many=True)
    return Response(
        {
            "entries": serializer.data,
            "period": period,
            "snapshot_date": timezone.localdate().isoformat(),
        },
        status=status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# XP History & Adjustment (admin only)
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def xp_history(request):
    """
    List XP transactions for the current tenant.

    Query params:
      - teacher_id: filter by teacher UUID
      - reason: filter by XP reason (e.g. content_completion, admin_adjust)
    """
    qs = XPTransaction.objects.select_related('teacher').all()

    teacher_id = request.GET.get('teacher_id')
    if teacher_id:
        qs = qs.filter(teacher_id=teacher_id)

    reason = request.GET.get('reason')
    if reason:
        qs = qs.filter(reason=reason)

    paginator = make_pagination_class(25, 100)()
    page = paginator.paginate_queryset(qs, request)
    if page is not None:
        serializer = XPTransactionSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    serializer = XPTransactionSerializer(qs, many=True)
    return Response({"results": serializer.data}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def xp_adjust(request):
    """
    Manually adjust a teacher's XP (admin only).

    Body:
    {
      "teacher_id": "uuid",
      "xp_amount": 50,
      "reason": "Bonus for workshop participation"
    }
    """
    serializer = XPAdjustSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    teacher = get_object_or_404(
        User, id=data['teacher_id'], tenant=request.tenant, is_active=True,
    )

    from .gamification_engine import award_xp

    tx = award_xp(
        teacher=teacher,
        reason='admin_adjust',
        xp_amount=data['xp_amount'],
        description=data.get('reason', 'Admin adjustment'),
    )

    if tx is None:
        return error_response(
            "Gamification is inactive or teacher has opted out.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    logger.info(
        "Admin XP adjustment: teacher=%s amount=%+d by=%s",
        teacher.email,
        data['xp_amount'],
        request.user.email,
    )

    return Response(
        XPTransactionSerializer(tx).data,
        status=status.HTTP_201_CREATED,
    )
