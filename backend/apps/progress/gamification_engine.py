"""
Core XP engine for the LearnPuddle gamification system.

All functions are importable and testable independently.
"""

from __future__ import annotations

import logging
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
    summary.last_xp_at = timezone.now()
    summary.save(update_fields=['last_xp_at', 'updated_at'])
    summary.refresh_from_transactions()

    # 6. Check and award badges
    check_and_award_badges(teacher, tenant)

    # 7. Return the transaction
    return txn


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
    return streak
