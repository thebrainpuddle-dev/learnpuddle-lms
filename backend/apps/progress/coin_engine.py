"""
Puddle Coin engine (TASK-019).

Puddle Coins are the third gamification currency — earnable from gameplay
milestones and spendable on cosmetic / utility items (MVP: streak-freeze
tokens). XP tracks effort, Mastery Points track competence, and Coins track
engagement-driven virtual wealth.

All public callables are import-safe (no circular imports on load) and
defensive: missing tenant, opt-out, or inactive gamification conditions
simply return ``None`` without raising. The only error a caller must handle
is ``InsufficientCoinsError`` raised by ``spend_coins``.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.db import IntegrityError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class InsufficientCoinsError(Exception):
    """Raised when a spend would drive the teacher's balance below zero."""

    def __init__(self, balance: int, amount: int):
        self.balance = balance
        self.amount = amount
        super().__init__(
            f"Insufficient Puddle Coins: balance={balance}, required={amount}",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_teacher_opted_out(teacher) -> bool:
    from .gamification_models import TeacherXPSummary

    try:
        summary = TeacherXPSummary.all_objects.get(teacher=teacher)
    except TeacherXPSummary.DoesNotExist:
        return False
    return bool(summary.opted_out)


def _get_amount_for_reason(config, reason: str) -> Optional[int]:
    mapping = {
        'level_up': config.coins_per_level_up,
        'challenge_reward': config.coins_per_challenge,
        'league_promote': config.coins_per_league_promote,
        'streak_milestone': config.coins_per_streak_milestone,
    }
    return mapping.get(reason)


# ---------------------------------------------------------------------------
# Read path
# ---------------------------------------------------------------------------


def get_balance(teacher):
    """Return (creating if absent) the teacher's cached coin balance row."""
    from .gamification_models import TeacherCoinBalance

    tenant = getattr(teacher, 'tenant', None)
    balance, created = TeacherCoinBalance.all_objects.get_or_create(
        teacher=teacher,
        defaults={'tenant': tenant} if tenant else {},
    )
    if created:
        balance.recompute_from_transactions()
    return balance


def recompute_balance(teacher):
    """Rebuild the cached balance row from the ledger (safe, idempotent)."""
    balance = get_balance(teacher)
    balance.recompute_from_transactions()
    return balance


# ---------------------------------------------------------------------------
# Earn path
# ---------------------------------------------------------------------------


def earn_coins(
    teacher,
    reason: str,
    amount: Optional[int] = None,
    description: str = '',
    reference_id=None,
    reference_type: str = '',
):
    """
    Grant Puddle Coins. Returns the ``CoinTransaction`` on success, ``None``
    on rejection (no tenant, inactive config, teacher opted-out, zero amount,
    or duplicate earn suppressed by the unique constraint).

    If ``amount`` is None, looks up the default for ``reason`` from the
    tenant's ``GamificationConfig``.
    """
    from .gamification_engine import get_or_create_config
    from .gamification_models import CoinTransaction, TeacherCoinBalance

    tenant = getattr(teacher, 'tenant', None)
    if tenant is None:
        logger.warning("earn_coins: teacher %s has no tenant", getattr(teacher, 'id', '?'))
        return None

    config = get_or_create_config(tenant)
    if not config.is_active:
        return None

    if _is_teacher_opted_out(teacher):
        logger.debug("earn_coins: teacher %s opted out — skipping", teacher.id)
        return None

    if amount is None:
        amount = _get_amount_for_reason(config, reason)
    if amount is None or amount <= 0:
        return None

    amount = int(amount)

    try:
        with transaction.atomic():
            txn = CoinTransaction.all_objects.create(
                tenant=tenant,
                teacher=teacher,
                amount=amount,
                reason=reason,
                description=description,
                reference_id=reference_id,
                reference_type=reference_type,
            )
            # Update cached balance in the same transaction.
            bal, _ = TeacherCoinBalance.all_objects.select_for_update().get_or_create(
                teacher=teacher,
                defaults={'tenant': tenant},
            )
            bal.balance = bal.balance + amount
            bal.lifetime_earned = bal.lifetime_earned + amount
            bal.last_txn_at = timezone.now()
            bal.save(update_fields=[
                'balance', 'lifetime_earned', 'last_txn_at', 'updated_at',
            ])
    except IntegrityError:
        logger.info(
            "earn_coins: duplicate suppressed (teacher=%s reason=%s ref=%s:%s)",
            teacher.id, reason, reference_type, reference_id,
        )
        return None

    logger.info(
        "Granted %d coins to teacher %s (reason=%s, ref=%s:%s)",
        amount, teacher.id, reason, reference_type, reference_id,
    )
    return txn


# ---------------------------------------------------------------------------
# Spend path
# ---------------------------------------------------------------------------


def spend_coins(
    teacher,
    amount: int,
    reason: str,
    description: str = '',
    reference_id=None,
    reference_type: str = '',
):
    """
    Debit ``amount`` coins from the teacher's balance. Raises
    ``InsufficientCoinsError`` if the teacher has fewer than ``amount``
    coins available.

    Runs inside ``transaction.atomic()`` with ``select_for_update()`` on the
    balance row so concurrent spend calls serialize safely and never
    double-debit.
    """
    from .gamification_models import CoinTransaction, TeacherCoinBalance

    if amount is None or int(amount) <= 0:
        raise ValueError("spend_coins amount must be a positive integer")
    amount = int(amount)

    tenant = getattr(teacher, 'tenant', None)
    if tenant is None:
        raise ValueError("spend_coins: teacher has no tenant")

    with transaction.atomic():
        bal, _ = TeacherCoinBalance.all_objects.select_for_update().get_or_create(
            teacher=teacher,
            defaults={'tenant': tenant},
        )
        if bal.balance < amount:
            raise InsufficientCoinsError(bal.balance, amount)

        txn = CoinTransaction.all_objects.create(
            tenant=tenant,
            teacher=teacher,
            amount=-amount,
            reason=reason,
            description=description,
            reference_id=reference_id,
            reference_type=reference_type,
        )

        bal.balance = bal.balance - amount
        bal.lifetime_spent = bal.lifetime_spent + amount
        bal.last_txn_at = timezone.now()
        bal.save(update_fields=[
            'balance', 'lifetime_spent', 'last_txn_at', 'updated_at',
        ])

    logger.info(
        "Teacher %s spent %d coins (reason=%s, new_balance=%d)",
        teacher.id, amount, reason, bal.balance,
    )
    return txn
