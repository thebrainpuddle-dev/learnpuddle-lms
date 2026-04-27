"""
Core XP engine for the LearnPuddle gamification system.

All functions are importable and testable independently.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


def get_or_create_config(tenant):
    """Get or create the gamification config for a tenant."""
    from .gamification_models import GamificationConfig

    config, created = GamificationConfig.objects.get_or_create(tenant=tenant)
    if created:
        logger.info("Created default GamificationConfig for tenant %s", tenant.id)
    return config


def get_xp_for_reason(config, reason: str) -> Optional[int]:
    """Map a reason string to the configured XP amount. Returns None for unknown reasons."""
    mapping = {
        'content_completion': config.xp_per_content_completion,
        'course_completion': config.xp_per_course_completion,
        'assignment_submission': config.xp_per_assignment_submission,
        'quiz_submission': config.xp_per_quiz_submission,
        'lesson_reflection': config.xp_per_lesson_reflection,
        'streak_bonus': config.xp_per_streak_day,
    }
    return mapping.get(reason)


def award_xp(
    teacher,
    reason: str,
    xp_amount: int = None,
    description: str = '',
    reference_id=None,
    reference_type: str = '',
):
    """
    Award XP to a teacher. Creates an XPTransaction and updates TeacherXPSummary.

    If xp_amount is None, looks up the default from GamificationConfig based on reason.
    Returns None if teacher has opted out or gamification is inactive for the tenant.

    reason must be one of: content_completion, course_completion, assignment_submission,
    quiz_submission, streak_bonus, badge_award, admin_adjust, quest_reward
    """
    from .gamification_models import GamificationConfig, TeacherXPSummary, XPTransaction

    tenant = getattr(teacher, 'tenant', None)
    if not tenant:
        logger.warning("award_xp called for teacher %s with no tenant", teacher.id)
        return None

    # 1. Get config, check is_active
    config = get_or_create_config(tenant)
    if not config.is_active:
        logger.debug("Gamification inactive for tenant %s — skipping XP award", tenant.id)
        return None

    # 2. Check if teacher has opted out
    summary, _ = TeacherXPSummary.all_objects.get_or_create(
        teacher=teacher,
        defaults={'tenant': tenant},
    )
    if summary.opted_out:
        logger.debug("Teacher %s opted out of gamification — skipping XP award", teacher.id)
        return None

    # 3. Resolve xp_amount from config when not explicitly provided
    if xp_amount is None:
        xp_amount = get_xp_for_reason(config, reason)
        if xp_amount is None:
            logger.error(
                "award_xp: no xp_amount provided and reason '%s' has no default mapping",
                reason,
            )
            return None

    # 4. Create XPTransaction
    txn = XPTransaction.all_objects.create(
        tenant=tenant,
        teacher=teacher,
        xp_amount=xp_amount,
        reason=reason,
        description=description,
        reference_id=reference_id,
        reference_type=reference_type,
    )
    logger.info(
        "Awarded %+d XP to teacher %s (reason=%s, ref=%s:%s)",
        xp_amount,
        teacher.id,
        reason,
        reference_type,
        reference_id,
    )

    # 5. Update TeacherXPSummary
    level_before = summary.level
    summary.last_xp_at = timezone.now()
    summary.save(update_fields=['last_xp_at', 'updated_at'])
    summary.refresh_from_transactions()

    # 5b. TASK-019: detect level-up and grant Puddle Coins.
    # Each (teacher, level) pair earns coins at most once, enforced via a
    # deterministic UUIDv5 reference_id so the unique partial constraint on
    # CoinTransaction suppresses duplicates even if award_xp runs twice.
    try:
        if summary.level > level_before:
            import uuid as _uuid

            from .coin_engine import earn_coins

            for new_level in range(level_before + 1, summary.level + 1):
                level_ref = _uuid.uuid5(
                    _uuid.NAMESPACE_OID,
                    f"coin-levelup:{teacher.id}:{new_level}",
                )
                earn_coins(
                    teacher=teacher,
                    reason='level_up',
                    reference_id=level_ref,
                    reference_type='level',
                    description=f'Reached level {new_level}',
                )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to grant level-up coins for teacher %s", teacher.id)

    # 6. Check and award badges
    check_and_award_badges(teacher, tenant)

    # 7. League: lazy-assign + bump weekly XP for current cohort
    try:
        _bump_league_weekly_xp(teacher, xp_amount)
    except Exception:  # noqa: BLE001 — never break XP award on league errors
        logger.exception("Failed to bump league weekly XP for teacher %s", teacher.id)

    # 8. Challenges: advance any active earn_xp challenges.
    # Guard on reason so awarding a challenge_reward doesn't recurse.
    if reason != "challenge_reward" and xp_amount > 0:
        try:
            from .challenge_engine import record_event

            record_event(
                teacher=teacher,
                event_type="earn_xp",
                reference_id=txn.id,
                reference_type="xp_transaction",
                amount=int(xp_amount),
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to record earn_xp challenge event")

    # 9. Return the transaction
    return txn


def _bump_league_weekly_xp(teacher, xp_amount: int):
    """
    Assign the teacher to the current week's league if not already assigned,
    and atomically increment ``LeagueMembership.weekly_xp``. Safe to call for
    opted-out teachers (they won't be assigned, so nothing happens).
    """
    from django.db.models import F

    from .league_engine import assign_teacher_to_league
    from .league_models import LeagueMembership

    membership = assign_teacher_to_league(teacher)
    if membership is None:
        return
    # Clamp additions to >=0 for PositiveIntegerField safety.
    delta = max(0, xp_amount)
    if delta == 0:
        return
    LeagueMembership.all_objects.filter(pk=membership.pk).update(
        weekly_xp=F("weekly_xp") + delta,
    )


def check_and_award_badges(teacher, tenant) -> list:
    """
    Check all active badge definitions for the tenant and award any the teacher
    qualifies for but hasn't earned yet.

    Returns list of newly awarded TeacherBadge instances.
    """
    from .gamification_models import (
        BadgeDefinition,
        TeacherBadge,
        TeacherStreak,
        TeacherXPSummary,
    )
    from .models import TeacherProgress

    awarded = []

    # Get or create the teacher's XP summary
    try:
        summary = TeacherXPSummary.all_objects.get(teacher=teacher)
    except TeacherXPSummary.DoesNotExist:
        logger.debug("No XP summary for teacher %s — skipping badge check", teacher.id)
        return awarded

    # Get all active badge definitions for the tenant
    badge_defs = BadgeDefinition.all_objects.filter(tenant=tenant, is_active=True)
    if not badge_defs.exists():
        return awarded

    # Get IDs of badges the teacher already owns
    existing_badge_ids = set(
        TeacherBadge.all_objects.filter(teacher=teacher)
        .values_list('badge_id', flat=True)
    )

    for badge_def in badge_defs:
        if badge_def.id in existing_badge_ids:
            continue

        qualified = False
        criteria_type = badge_def.criteria_type
        criteria_value = badge_def.criteria_value

        if criteria_type == 'xp_threshold':
            qualified = summary.total_xp >= criteria_value

        elif criteria_type == 'courses_completed':
            completed_count = (
                TeacherProgress.all_objects.filter(
                    teacher=teacher,
                    content__isnull=True,
                    status='COMPLETED',
                ).count()
            )
            # Also count courses where all content is done (progress_percentage >= 100)
            if completed_count < criteria_value:
                completed_count += (
                    TeacherProgress.all_objects.filter(
                        teacher=teacher,
                        content__isnull=False,
                        status='COMPLETED',
                    )
                    .values('course_id')
                    .distinct()
                    .count()
                )
                # Use the distinct course count as a rough proxy;
                # the actual per-course check is done elsewhere.
            qualified = completed_count >= criteria_value

        elif criteria_type == 'streak_days':
            try:
                streak = TeacherStreak.all_objects.get(teacher=teacher)
                qualified = (
                    streak.current_streak >= criteria_value
                    or streak.longest_streak >= criteria_value
                )
            except TeacherStreak.DoesNotExist:
                qualified = False

        elif criteria_type == 'content_completed':
            content_count = TeacherProgress.all_objects.filter(
                teacher=teacher,
                content__isnull=False,
                status='COMPLETED',
            ).count()
            qualified = content_count >= criteria_value

        elif criteria_type == 'manual':
            # Manual badges are awarded by admins, not automatically
            continue

        else:
            logger.warning("Unknown badge criteria_type '%s' for badge %s", criteria_type, badge_def.id)
            continue

        if qualified:
            tb = TeacherBadge.all_objects.create(
                tenant=tenant,
                teacher=teacher,
                badge=badge_def,
                awarded_reason=f'Auto-awarded: {criteria_type} >= {criteria_value}',
            )
            awarded.append(tb)
            logger.info(
                "Awarded badge '%s' to teacher %s (criteria: %s >= %s)",
                badge_def.name,
                teacher.id,
                criteria_type,
                criteria_value,
            )

    return awarded


def update_streak(teacher, tenant):
    """
    Record activity for today. Gets or creates TeacherStreak and calls record_activity().
    Returns the updated TeacherStreak instance.
    """
    from .gamification_models import TeacherStreak

    streak, created = TeacherStreak.all_objects.get_or_create(
        teacher=teacher,
        defaults={'tenant': tenant},
    )
    if created:
        logger.debug("Created new streak tracker for teacher %s", teacher.id)
    streak.record_activity()

    # Challenges: evaluate any active maintain_streak challenges.
    try:
        from .challenge_engine import evaluate_streak_challenge

        evaluate_streak_challenge(teacher, streak.current_streak)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to evaluate streak challenges for teacher %s", teacher.id)
    return streak


# ---------------------------------------------------------------------------
# Streak freeze tokens
# ---------------------------------------------------------------------------

def _count_available_tokens(teacher, now=None):
    """Return the count of unconsumed, unexpired tokens for a teacher."""
    from .gamification_models import StreakFreezeToken

    now = now or timezone.now()
    return (
        StreakFreezeToken.all_objects.filter(
            teacher=teacher,
            consumed_at__isnull=True,
        )
        .filter(
            models_q_unexpired(now),
        )
        .count()
    )


def models_q_unexpired(now):
    """Build a Q filter for 'expires_at is null OR expires_at > now'."""
    from django.db.models import Q
    return Q(expires_at__isnull=True) | Q(expires_at__gt=now)


def earn_streak_freeze_token(
    teacher,
    source: str = 'streak_milestone',
    description: str = '',
    reference_id=None,
    reference_type: str = '',
):
    """
    Grant a single streak-freeze token to a teacher.

    Respects ``GamificationConfig.freeze_token_max_inventory`` — if the teacher
    already has >= cap unconsumed tokens, the earn is rejected and ``None`` is
    returned.

    On success, writes a ledger row (``event_type='earned'``) and returns the
    new ``StreakFreezeToken``.
    """
    from .gamification_models import StreakFreezeLedger, StreakFreezeToken

    tenant = getattr(teacher, 'tenant', None)
    if not tenant:
        logger.warning("earn_streak_freeze_token: teacher %s has no tenant", teacher.id)
        return None

    config = get_or_create_config(tenant)
    if not config.is_active:
        return None

    now = timezone.now()
    available = _count_available_tokens(teacher, now=now)
    if available >= config.freeze_token_max_inventory:
        logger.info(
            "Teacher %s already at freeze-token cap (%d); skipping earn",
            teacher.id, available,
        )
        return None

    expires_at = None
    if config.freeze_token_expires_days and config.freeze_token_expires_days > 0:
        expires_at = now + timedelta(days=config.freeze_token_expires_days)

    token = StreakFreezeToken.all_objects.create(
        tenant=tenant,
        teacher=teacher,
        source=source,
        expires_at=expires_at,
        reference_id=reference_id,
        reference_type=reference_type,
    )

    StreakFreezeLedger.all_objects.create(
        tenant=tenant,
        teacher=teacher,
        event_type='earned' if source != 'admin_grant' else 'granted',
        token=token,
        description=description or f'Earned via {source}',
        balance_after=available + 1,
    )

    logger.info(
        "Granted freeze token to teacher %s (source=%s, inventory=%d)",
        teacher.id, source, available + 1,
    )
    return token


def spend_streak_freeze_token(teacher, description: str = ''):
    """
    Consume the oldest unexpired unconsumed token for a teacher.

    Returns the consumed ``StreakFreezeToken``, or ``None`` if no tokens are
    available. Writes a ledger row (``event_type='spent'``).
    """
    from .gamification_models import StreakFreezeLedger, StreakFreezeToken

    tenant = getattr(teacher, 'tenant', None)
    if not tenant:
        return None

    now = timezone.now()
    candidate = (
        StreakFreezeToken.all_objects.filter(
            teacher=teacher, consumed_at__isnull=True,
        )
        .filter(models_q_unexpired(now))
        .order_by('earned_at')
        .first()
    )
    if not candidate:
        return None

    candidate.consumed_at = now
    candidate.save(update_fields=['consumed_at'])

    balance_after = _count_available_tokens(teacher, now=now)

    StreakFreezeLedger.all_objects.create(
        tenant=tenant,
        teacher=teacher,
        event_type='spent',
        token=candidate,
        description=description or 'Token spent to protect streak',
        balance_after=balance_after,
    )

    logger.info(
        "Teacher %s spent freeze token %s (remaining=%d)",
        teacher.id, candidate.id, balance_after,
    )
    return candidate


