# apps/progress/challenge_engine.py
#
# TASK-017 — Daily / Weekly Challenges engine.
#
# Single entry-point ``record_event`` is called by signals to increment
# progress on all active challenges matching an event type. Fully
# idempotent: each increment is keyed by ``reference_type:reference_id``
# so re-saves of the same underlying row do not double-count.

from __future__ import annotations

import logging
from typing import Iterable, Optional

from django.db import transaction
from django.utils import timezone

from .challenge_models import (
    Challenge,
    ChallengeParticipation,
)

logger = logging.getLogger(__name__)


# Map signal event names → the goal_type(s) they advance.
EVENT_TO_GOAL = {
    "content_completion": ["complete_lessons"],
    "course_completion": ["finish_course"],
    "assignment_submission": ["submit_assignments"],
    "earn_xp": ["earn_xp"],
    "streak_update": ["maintain_streak"],
}


INCREMENT_LOG_MAX = 50


def _now():
    return timezone.now()


def active_challenges(
    tenant,
    now=None,
    challenge_type: Optional[str] = None,
    goal_types: Optional[Iterable[str]] = None,
):
    """Return the challenges currently in-window for a tenant."""
    now = now or _now()
    qs = Challenge.all_objects.filter(
        tenant=tenant,
        is_active=True,
        start_at__lte=now,
        end_at__gte=now,
    )
    if challenge_type:
        qs = qs.filter(challenge_type=challenge_type)
    if goal_types:
        qs = qs.filter(goal_type__in=list(goal_types))
    return qs


def get_or_create_participation(teacher, challenge: Challenge) -> ChallengeParticipation:
    """Fetch (or create) the ChallengeParticipation for teacher × challenge."""
    participation, _ = ChallengeParticipation.all_objects.get_or_create(
        challenge=challenge,
        teacher=teacher,
        defaults={"tenant": challenge.tenant},
    )
    return participation


def _ref_key(reference_type: str, reference_id) -> str:
    if reference_id is None:
        return ""
    return f"{reference_type or ''}:{reference_id}"


def _already_applied(participation: ChallengeParticipation, ref_key: str) -> bool:
    """Has this exact (ref_type, ref_id) pair already been counted?"""
    if not ref_key:
        return False
    log = participation.increments_log or []
    for entry in log:
        if entry.get("ref_key") == ref_key:
            return True
    return False


def _append_log(participation: ChallengeParticipation, ref_key: str, amount: int):
    log = list(participation.increments_log or [])
    log.append({
        "ref_key": ref_key,
        "value": int(amount),
        "ts": _now().isoformat(),
    })
    # Keep bounded so JSON field doesn't grow unbounded over long challenges.
    if len(log) > INCREMENT_LOG_MAX:
        log = log[-INCREMENT_LOG_MAX:]
    participation.increments_log = log


def record_event(
    teacher,
    event_type: str,
    reference_id=None,
    reference_type: str = "",
    amount: int = 1,
):
    """
    Advance all active challenges of the mapped goal_type(s) for the teacher.

    Idempotent: each (reference_type, reference_id) pair is applied at most
    once per participation. Safe to call on every signal firing.
    """
    tenant = getattr(teacher, "tenant", None)
    if not tenant:
        return

    goal_types = EVENT_TO_GOAL.get(event_type)
    if not goal_types:
        return

    # Respect opt-out: if teacher is opted out of gamification, no progress.
    from .gamification_models import TeacherXPSummary

    summary = TeacherXPSummary.all_objects.filter(teacher=teacher).first()
    if summary and summary.opted_out:
        return

    challenges = list(active_challenges(tenant, goal_types=goal_types))
    if not challenges:
        return

    ref_key = _ref_key(reference_type, reference_id)

    for challenge in challenges:
        # goal_reference_id narrowing (e.g. finish_course targets one course).
        if (
            challenge.goal_reference_id is not None
            and challenge.goal_type == "finish_course"
            and reference_id != challenge.goal_reference_id
        ):
            continue

        _apply_increment(teacher, challenge, ref_key=ref_key, amount=amount)


@transaction.atomic
def _apply_increment(teacher, challenge: Challenge, ref_key: str, amount: int):
    """Increment one participation, guarding dedup and reward issuance."""
    participation = get_or_create_participation(teacher, challenge)

    if participation.completed_at is not None:
        return  # already done — nothing more to do

    if _already_applied(participation, ref_key):
        return

    target = challenge.goal_target
    delta = max(0, int(amount))
    if delta == 0:
        return

    new_value = min(target, participation.progress_value + delta)
    participation.progress_value = new_value
    participation.last_reference_key = ref_key
    _append_log(participation, ref_key, delta)

    newly_complete = new_value >= target and participation.completed_at is None
    if newly_complete:
        participation.completed_at = _now()

    participation.save(update_fields=[
        "progress_value",
        "last_reference_key",
        "increments_log",
        "completed_at",
        "updated_at",
    ])

    if newly_complete:
        issue_challenge_rewards(participation)


def evaluate_streak_challenge(teacher, current_streak: int):
    """
    Called when a teacher's streak changes. Sets progress on any active
    ``maintain_streak`` challenge to min(current_streak, target). If the
    streak reaches the target, marks complete + issues rewards.
    """
    tenant = getattr(teacher, "tenant", None)
    if not tenant:
        return
    challenges = list(active_challenges(tenant, goal_types=["maintain_streak"]))
    for challenge in challenges:
        participation = get_or_create_participation(teacher, challenge)
        if participation.completed_at is not None:
            continue
        new_value = min(challenge.goal_target, max(participation.progress_value, current_streak))
        if new_value == participation.progress_value:
            continue
        participation.progress_value = new_value
        if new_value >= challenge.goal_target:
            participation.completed_at = _now()
        participation.save(update_fields=[
            "progress_value", "completed_at", "updated_at",
        ])
        if participation.completed_at and not participation.reward_issued:
            issue_challenge_rewards(participation)


def issue_challenge_rewards(participation: ChallengeParticipation):
    """Issue XP + optional badge for a completed participation. Idempotent."""
    if participation.reward_issued:
        return
    challenge = participation.challenge
    teacher = participation.teacher

    # Local import — avoid circular: gamification_engine imports nothing from here.
    from .gamification_engine import award_xp
    from .gamification_models import TeacherBadge

    if challenge.reward_xp and challenge.reward_xp > 0:
        award_xp(
            teacher=teacher,
            reason="challenge_reward",
            xp_amount=challenge.reward_xp,
            description=f"Challenge completed: {challenge.title}",
            reference_id=challenge.id,
            reference_type="challenge",
        )

    if challenge.reward_badge_id:
        # De-duplicate via the unique (teacher, badge) constraint.
        TeacherBadge.all_objects.get_or_create(
            teacher=teacher,
            badge=challenge.reward_badge,
            defaults={
                "tenant": challenge.tenant,
                "awarded_reason": f"Challenge reward: {challenge.title}",
            },
        )

    # TASK-019: Puddle Coins on challenge completion. Idempotent via the
    # unique (teacher, reason, reference_type, reference_id) earn constraint.
    try:
        from .coin_engine import earn_coins

        earn_coins(
            teacher=teacher,
            reason="challenge_reward",
            reference_id=challenge.id,
            reference_type="challenge",
            description=f"Challenge completed: {challenge.title}",
        )
    except Exception:  # noqa: BLE001 — never break reward issuance on coin error
        logger.exception(
            "earn_coins failed on challenge completion teacher=%s challenge=%s",
            teacher.id, challenge.id,
        )

    participation.reward_issued = True
    participation.save(update_fields=["reward_issued", "updated_at"])
    logger.info(
        "Issued challenge rewards: teacher=%s challenge=%s xp=%s badge=%s",
        teacher.id, challenge.id, challenge.reward_xp, challenge.reward_badge_id,
    )


def serialize_challenge_for_teacher(challenge: Challenge, teacher) -> dict:
    """Shape a Challenge + participation for the teacher-facing list response."""
    participation = ChallengeParticipation.all_objects.filter(
        challenge=challenge, teacher=teacher,
    ).first()
    progress_value = participation.progress_value if participation else 0
    completed_at = participation.completed_at if participation else None
    target = max(1, challenge.goal_target)
    percent = min(100, int(round(100 * progress_value / target)))
    return {
        "id": str(challenge.id),
        "title": challenge.title,
        "description": challenge.description,
        "challenge_type": challenge.challenge_type,
        "goal_type": challenge.goal_type,
        "goal_target": challenge.goal_target,
        "goal_reference_id": (
            str(challenge.goal_reference_id) if challenge.goal_reference_id else None
        ),
        "start_at": challenge.start_at.isoformat(),
        "end_at": challenge.end_at.isoformat(),
        "reward_xp": challenge.reward_xp,
        "reward_badge_id": (
            str(challenge.reward_badge_id) if challenge.reward_badge_id else None
        ),
        "progress_value": progress_value,
        "progress_percent": percent,
        "completed_at": completed_at.isoformat() if completed_at else None,
    }
