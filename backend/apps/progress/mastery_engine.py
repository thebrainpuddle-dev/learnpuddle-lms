"""
Mastery Point engine (TASK-018).

Mastery Points (MP) are a second gamification currency that complements XP.
Where XP is awarded for effort (any content completion, quiz attempt, etc.),
MP is awarded only when demonstrated competence clears a configurable
threshold:

* Quiz submissions with `score_percent >= config.mp_quiz_threshold_percent`
  award `round(score_percent * config.mp_quiz_weight)` MP.
* Assignment grades (rubric-backed or otherwise) with
  `score_percent >= config.mp_assignment_threshold_percent` award
  `round(score_percent * config.mp_assignment_weight)` MP.
* A course completion whose average quiz score meets the quiz threshold
  earns a flat `config.mp_course_bonus` bonus.

All functions are import-safe and defensive: missing tenant, opt-out, or
config-inactive conditions simply return ``None`` without raising.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from django.db import IntegrityError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_decimal(value, default: str = '0') -> Decimal:
    """Coerce *value* to Decimal; fall back to *default* on TypeError."""
    if value is None:
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001 — defensive
        return Decimal(default)


def _round_mp(value: Decimal) -> Decimal:
    """Round to 2dp using banker-safe half-up, matching Django decimal fields."""
    return _to_decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _is_teacher_opted_out(teacher) -> bool:
    """Return True if the teacher has opted out of gamification."""
    from .gamification_models import TeacherXPSummary

    try:
        summary = TeacherXPSummary.all_objects.get(teacher=teacher)
    except TeacherXPSummary.DoesNotExist:
        return False
    return bool(summary.opted_out)


# ---------------------------------------------------------------------------
# Core award pathway
# ---------------------------------------------------------------------------


def award_mastery_points(
    teacher,
    reason: str,
    amount,
    description: str = '',
    reference_id=None,
    reference_type: str = '',
    skill_code: str = '',
):
    """
    Award Mastery Points to a teacher. Returns the created
    ``MasteryPointTransaction`` on success, or ``None`` if the award is
    rejected (no tenant, opt-out, inactive, zero/negative amount, or
    duplicate reference).
    """
    from .gamification_engine import get_or_create_config
    from .gamification_models import (
        MasteryPointTransaction,
        TeacherMasterySummary,
    )

    tenant = getattr(teacher, 'tenant', None)
    if tenant is None:
        logger.warning(
            "award_mastery_points: teacher %s has no tenant",
            getattr(teacher, 'id', '?'),
        )
        return None

    config = get_or_create_config(tenant)
    if not config.is_active:
        logger.debug(
            "award_mastery_points: gamification inactive for tenant %s",
            tenant.id,
        )
        return None

    if _is_teacher_opted_out(teacher):
        logger.debug(
            "award_mastery_points: teacher %s opted out — skipping MP",
            teacher.id,
        )
        return None

    amount_dec = _round_mp(amount)
    if amount_dec <= 0 and reason != 'admin_adjust':
        # Zero / negative awards from auto-sources are a no-op. Admin
        # adjustments can still record negative amounts.
        return None

    # Idempotency: the DB unique constraint on
    # (teacher, reason, reference_type, reference_id) catches re-saves.
    try:
        with transaction.atomic():
            txn = MasteryPointTransaction.all_objects.create(
                tenant=tenant,
                teacher=teacher,
                amount=amount_dec,
                reason=reason,
                description=description,
                reference_id=reference_id,
                reference_type=reference_type,
                skill_code=skill_code,
            )
    except IntegrityError:
        logger.info(
            "award_mastery_points: duplicate MP award suppressed "
            "(teacher=%s, reason=%s, ref=%s:%s)",
            teacher.id, reason, reference_type, reference_id,
        )
        return None

    logger.info(
        "Awarded %+sMP to teacher %s (reason=%s, ref=%s:%s)",
        amount_dec, teacher.id, reason, reference_type, reference_id,
    )

    # Refresh the denormalized summary.
    summary, _ = TeacherMasterySummary.all_objects.get_or_create(
        teacher=teacher,
        defaults={'tenant': tenant},
    )
    summary.last_mp_at = timezone.now()
    summary.save(update_fields=['last_mp_at', 'updated_at'])
    summary.refresh_from_transactions()

    return txn


# ---------------------------------------------------------------------------
# Source-specific helpers
# ---------------------------------------------------------------------------


def award_quiz_mastery(submission) -> Optional[object]:
    """
    Evaluate a ``QuizSubmission`` and award MP if the score meets the
    configured quiz threshold. Returns the transaction or ``None``.
    """
    from .gamification_engine import get_or_create_config

    if submission is None or submission.score is None:
        return None
    teacher = submission.teacher
    tenant = submission.tenant or getattr(teacher, 'tenant', None)
    if tenant is None:
        return None

    quiz = submission.quiz
    assignment = getattr(quiz, 'assignment', None)
    max_score = _to_decimal(
        getattr(assignment, 'max_score', None) or 100,
        default='100',
    )
    score = _to_decimal(submission.score)
    if max_score <= 0:
        return None
    score_percent = (score / max_score) * Decimal('100')

    config = get_or_create_config(tenant)
    threshold = _to_decimal(config.mp_quiz_threshold_percent, '80')
    if score_percent < threshold:
        return None

    weight = _to_decimal(config.mp_quiz_weight, '1')
    mp_amount = (score_percent * weight)

    return award_mastery_points(
        teacher=teacher,
        reason='quiz_mastery',
        amount=mp_amount,
        description=(
            f'Quiz mastery: {score_percent.quantize(Decimal("0.01"))}%'
        ),
        reference_id=submission.id,
        reference_type='quiz_submission',
    )


def award_assignment_mastery(submission) -> Optional[object]:
    """
    Evaluate a graded ``AssignmentSubmission`` and award MP if the grade
    meets the configured threshold. Returns the transaction or ``None``.
    """
    from .gamification_engine import get_or_create_config

    if submission is None or submission.score is None:
        return None
    # Only award once the submission is actually graded.
    if submission.status != 'GRADED':
        return None

    teacher = submission.teacher
    tenant = submission.tenant or getattr(teacher, 'tenant', None)
    if tenant is None:
        return None

    assignment = submission.assignment
    max_score = _to_decimal(
        getattr(assignment, 'max_score', None) or 100, default='100',
    )
    score = _to_decimal(submission.score)
    if max_score <= 0:
        return None
    score_percent = (score / max_score) * Decimal('100')

    config = get_or_create_config(tenant)
    threshold = _to_decimal(config.mp_assignment_threshold_percent, '80')
    if score_percent < threshold:
        return None

    weight = _to_decimal(config.mp_assignment_weight, '1')
    # MP scales off the raw rubric/assignment score so higher-weight
    # assignments yield more MP than percentage alone would.
    mp_amount = score * weight

    return award_mastery_points(
        teacher=teacher,
        reason='assignment_mastery',
        amount=mp_amount,
        description=(
            f'Assignment mastery: {score_percent.quantize(Decimal("0.01"))}%'
        ),
        reference_id=submission.id,
        reference_type='assignment_submission',
    )


def award_course_mastery_bonus(teacher, course) -> Optional[object]:
    """
    Award a flat course mastery bonus when the teacher's average quiz
    score in *course* meets the configured threshold. Idempotent on
    (teacher, course).
    """
    from django.db.models import Avg

    from .gamification_engine import get_or_create_config
    from .models import QuizSubmission

    if teacher is None or course is None:
        return None
    tenant = getattr(teacher, 'tenant', None)
    if tenant is None:
        return None

    config = get_or_create_config(tenant)
    threshold = _to_decimal(config.mp_quiz_threshold_percent, '80')

    # Average percentage across all quiz submissions for this course.
    subs = QuizSubmission.all_objects.filter(
        teacher=teacher,
        quiz__assignment__course=course,
        score__isnull=False,
    )
    if not subs.exists():
        return None

    # Compute percentage per submission; guard against max_score=0.
    total_pct = Decimal('0')
    counted = 0
    for sub in subs:
        max_score = _to_decimal(
            getattr(sub.quiz.assignment, 'max_score', None) or 100,
            default='100',
        )
        if max_score <= 0:
            continue
        pct = (_to_decimal(sub.score) / max_score) * Decimal('100')
        total_pct += pct
        counted += 1
    if counted == 0:
        return None

    avg_pct = total_pct / Decimal(counted)
    if avg_pct < threshold:
        return None

    bonus = _to_decimal(config.mp_course_bonus, '0')
    return award_mastery_points(
        teacher=teacher,
        reason='course_mastery_bonus',
        amount=bonus,
        description=(
            f'Course mastery bonus '
            f'(avg {avg_pct.quantize(Decimal("0.01"))}%)'
        ),
        reference_id=course.id,
        reference_type='course',
    )


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


def get_mastery_summary(teacher):
    """Return (creating if absent) the teacher's mastery summary row."""
    from .gamification_models import TeacherMasterySummary

    tenant = getattr(teacher, 'tenant', None)
    summary, created = TeacherMasterySummary.all_objects.get_or_create(
        teacher=teacher,
        defaults={'tenant': tenant} if tenant else {},
    )
    if created:
        summary.refresh_from_transactions()
    return summary
