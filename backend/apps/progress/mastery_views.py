"""
Mastery Point HTTP views (TASK-018).

Teacher endpoints:
  GET /api/v1/gamification/mastery/         — current teacher's MP summary.
  GET /api/v1/gamification/mastery/history/ — paginated ledger for current
                                              teacher.

Admin endpoints:
  GET /api/v1/gamification/admin/mastery/leaderboard/
      — top-N teachers by total_mastery_points, tenant-scoped.
"""

from __future__ import annotations

import logging

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.decorators import admin_only, teacher_or_admin, tenant_required
from utils.helpers import make_pagination_class

from .gamification_models import (
    MasteryPointTransaction,
    TeacherMasterySummary,
)
from .gamification_serializers import (
    MasteryLeaderboardEntrySerializer,
    MasteryPointTransactionSerializer,
    TeacherMasterySummarySerializer,
)
from .mastery_engine import get_mastery_summary

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Teacher endpoints
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_mastery_summary(request):
    """Return the requesting teacher's mastery summary row."""
    summary = get_mastery_summary(request.user)
    return Response(TeacherMasterySummarySerializer(summary).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_mastery_history(request):
    """Paginated list of the requesting teacher's MP transactions."""
    qs = MasteryPointTransaction.all_objects.filter(
        tenant=request.tenant,
        teacher=request.user,
    ).order_by('-created_at')

    paginator = make_pagination_class(page_size=25)()
    page = paginator.paginate_queryset(qs, request)
    data = MasteryPointTransactionSerializer(page, many=True).data
    return paginator.get_paginated_response(data)


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def admin_mastery_leaderboard(request):
    """
    Return top-N teachers in the tenant, ordered by total mastery points.
    Supports ?limit= (default 25, max 200).
    """
    try:
        limit = int(request.query_params.get('limit', 25))
    except (TypeError, ValueError):
        limit = 25
    limit = max(1, min(limit, 200))

    qs = (
        TeacherMasterySummary.all_objects.filter(tenant=request.tenant)
        .select_related('teacher')
        .order_by('-total_mastery_points')[:limit]
    )

    entries = []
    for rank, summary in enumerate(qs, start=1):
        teacher = summary.teacher
        entries.append({
            'rank': rank,
            'teacher_id': teacher.id,
            'teacher_name': teacher.get_full_name() or teacher.email,
            'teacher_email': teacher.email,
            'total_mastery_points': summary.total_mastery_points,
            'mp_this_week': summary.mp_this_week,
            'mp_this_month': summary.mp_this_month,
        })

    return Response({
        'count': len(entries),
        'results': MasteryLeaderboardEntrySerializer(entries, many=True).data,
    })
