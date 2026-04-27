"""
Puddle Coin HTTP views (TASK-019).

Teacher endpoints:
  GET  /api/v1/gamification/coins/          — current balance + lifetime totals.
  GET  /api/v1/gamification/coins/history/  — paginated ledger.
  POST /api/v1/gamification/coins/purchase/streak-freeze/
      — spend coins, mint a freeze token.
"""

from __future__ import annotations

import logging

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.decorators import teacher_or_admin, tenant_required
from utils.helpers import make_pagination_class
from utils.responses import error_response

from .coin_engine import (
    InsufficientCoinsError,
    get_balance,
    spend_coins,
)
from .gamification_engine import (
    earn_streak_freeze_token,
    get_or_create_config,
    _count_available_tokens,
)
from .gamification_models import CoinTransaction
from .gamification_serializers import (
    CoinTransactionSerializer,
    TeacherCoinBalanceSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Teacher read endpoints
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_coin_balance(request):
    """Return the requesting teacher's coin balance row."""
    balance = get_balance(request.user)
    return Response(TeacherCoinBalanceSerializer(balance).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_coin_history(request):
    """Paginated list of the requesting teacher's coin transactions."""
    qs = CoinTransaction.all_objects.filter(
        tenant=request.tenant,
        teacher=request.user,
    ).order_by('-created_at')

    paginator = make_pagination_class(page_size=25)()
    page = paginator.paginate_queryset(qs, request)
    data = CoinTransactionSerializer(page, many=True).data
    return paginator.get_paginated_response(data)


# ---------------------------------------------------------------------------
# Spend — purchase streak freeze
# ---------------------------------------------------------------------------


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_purchase_streak_freeze(request):
    """
    Spend coins to buy exactly one streak-freeze token.

    Respects:
      - GamificationConfig.coin_price_streak_freeze (price)
      - GamificationConfig.freeze_token_max_inventory (cap)

    Returns 400 when the teacher has insufficient coins or is at the
    inventory cap; 200 + new balance + minted token on success.
    """
    teacher = request.user
    config = get_or_create_config(request.tenant)
    price = int(config.coin_price_streak_freeze)

    # Check inventory cap first — refusing after we've debited would be a
    # worse UX (we'd have to refund). Count unexpired unconsumed tokens.
    available = _count_available_tokens(teacher)
    if available >= config.freeze_token_max_inventory:
        return error_response(
            "Streak-freeze inventory is at the cap.",
            status_code=400,
            cap=config.freeze_token_max_inventory,
        )

    try:
        spend_txn = spend_coins(
            teacher=teacher,
            amount=price,
            reason='purchase_streak_freeze',
            description='Purchased streak-freeze token',
            reference_type='streak_freeze_purchase',
        )
    except InsufficientCoinsError as exc:
        return error_response(
            "Insufficient Puddle Coins.",
            status_code=400,
            balance=exc.balance,
            price=price,
        )

    token = earn_streak_freeze_token(
        teacher=teacher,
        source='purchase',
        description='Purchased with Puddle Coins',
    )

    balance = get_balance(teacher)
    return Response({
        'balance': TeacherCoinBalanceSerializer(balance).data,
        'transaction': CoinTransactionSerializer(spend_txn).data,
        'token': {
            'id': str(token.id) if token else None,
            'source': token.source if token else None,
            'expires_at': token.expires_at.isoformat() if token and token.expires_at else None,
        },
    })
