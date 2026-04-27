# apps/progress/challenge_views.py
#
# TASK-017 — Challenge API (teacher + admin).

import logging
from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.decorators import admin_only, teacher_or_admin, tenant_required

from .challenge_engine import (
    active_challenges,
    serialize_challenge_for_teacher,
)
from .challenge_models import (
    CHALLENGE_GOAL_CHOICES,
    CHALLENGE_TYPE_CHOICES,
    Challenge,
    ChallengeParticipation,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Teacher endpoints
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_active_challenges(request):
    """List the teacher's currently-active challenges with progress."""
    challenges = list(active_challenges(request.tenant))
    data = [
        serialize_challenge_for_teacher(c, request.user) for c in challenges
    ]
    return Response({"results": data})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_completed_challenges(request):
    """List challenges this teacher completed in the last 30 days."""
    since = timezone.now() - timedelta(days=30)
    participations = (
        ChallengeParticipation.all_objects.filter(
            tenant=request.tenant,
            teacher=request.user,
            completed_at__isnull=False,
            completed_at__gte=since,
        )
        .select_related("challenge")
        .order_by("-completed_at")
    )
    data = [
        serialize_challenge_for_teacher(p.challenge, request.user)
        for p in participations
    ]
    return Response({"results": data})


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

def _serialize_admin_challenge(challenge: Challenge) -> dict:
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
        "is_active": challenge.is_active,
        "created_at": challenge.created_at.isoformat(),
        "updated_at": challenge.updated_at.isoformat(),
    }


_REQUIRED_CREATE_FIELDS = {
    "title", "challenge_type", "goal_type", "goal_target",
    "start_at", "end_at",
}


def _parse_dt(value):
    if value is None:
        return None
    from django.utils.dateparse import parse_datetime
    dt = parse_datetime(value) if isinstance(value, str) else value
    if dt and timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _validate_payload(payload, required=True):
    errors = {}
    if required:
        missing = _REQUIRED_CREATE_FIELDS - set(payload.keys())
        if missing:
            errors["missing"] = sorted(missing)

    challenge_type = payload.get("challenge_type")
    if challenge_type is not None and challenge_type not in dict(CHALLENGE_TYPE_CHOICES):
        errors["challenge_type"] = (
            f"Must be one of {list(dict(CHALLENGE_TYPE_CHOICES).keys())}"
        )

    goal_type = payload.get("goal_type")
    if goal_type is not None and goal_type not in dict(CHALLENGE_GOAL_CHOICES):
        errors["goal_type"] = (
            f"Must be one of {list(dict(CHALLENGE_GOAL_CHOICES).keys())}"
        )

    target = payload.get("goal_target")
    if target is not None:
        try:
            if int(target) < 1:
                errors["goal_target"] = "Must be a positive integer."
        except (TypeError, ValueError):
            errors["goal_target"] = "Must be an integer."

    reward_xp = payload.get("reward_xp")
    if reward_xp is not None:
        try:
            if int(reward_xp) < 0:
                errors["reward_xp"] = "Must be >= 0."
        except (TypeError, ValueError):
            errors["reward_xp"] = "Must be an integer."

    start_at = _parse_dt(payload.get("start_at"))
    end_at = _parse_dt(payload.get("end_at"))
    if "start_at" in payload and start_at is None:
        errors["start_at"] = "Invalid datetime."
    if "end_at" in payload and end_at is None:
        errors["end_at"] = "Invalid datetime."
    if start_at and end_at and end_at <= start_at:
        errors["end_at"] = "Must be after start_at."
    return errors


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def admin_list_challenges(request):
    """List all challenges in this tenant (active and inactive)."""
    qs = Challenge.all_objects.filter(tenant=request.tenant).order_by("-start_at")
    data = [_serialize_admin_challenge(c) for c in qs]
    return Response({"results": data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def admin_create_challenge(request):
    """Create a new challenge for this tenant."""
    payload = request.data or {}
    errors = _validate_payload(payload, required=True)
    if errors:
        return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

    challenge = Challenge.all_objects.create(
        tenant=request.tenant,
        title=payload["title"],
        description=payload.get("description", ""),
        challenge_type=payload["challenge_type"],
        goal_type=payload["goal_type"],
        goal_target=int(payload["goal_target"]),
        goal_reference_id=payload.get("goal_reference_id") or None,
        start_at=_parse_dt(payload["start_at"]),
        end_at=_parse_dt(payload["end_at"]),
        reward_xp=int(payload.get("reward_xp") or 0),
        reward_badge_id=payload.get("reward_badge_id") or None,
        is_active=bool(payload.get("is_active", True)),
        created_by=request.user,
    )
    return Response(
        _serialize_admin_challenge(challenge), status=status.HTTP_201_CREATED,
    )


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def admin_update_challenge(request, challenge_id):
    """Update an existing challenge."""
    challenge = get_object_or_404(
        Challenge.all_objects, id=challenge_id, tenant=request.tenant,
    )
    payload = request.data or {}
    errors = _validate_payload(payload, required=False)
    if errors:
        return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

    mutable_fields = [
        "title", "description", "challenge_type", "goal_type",
        "goal_target", "goal_reference_id", "reward_xp", "reward_badge_id",
        "is_active",
    ]
    for field in mutable_fields:
        if field in payload:
            setattr(challenge, field, payload[field])
    if "start_at" in payload:
        challenge.start_at = _parse_dt(payload["start_at"])
    if "end_at" in payload:
        challenge.end_at = _parse_dt(payload["end_at"])

    challenge.save()
    return Response(_serialize_admin_challenge(challenge))


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def admin_delete_challenge(request, challenge_id):
    """Disable a challenge (soft — sets is_active=False)."""
    challenge = get_object_or_404(
        Challenge.all_objects, id=challenge_id, tenant=request.tenant,
    )
    challenge.is_active = False
    challenge.save(update_fields=["is_active", "updated_at"])
    return Response(status=status.HTTP_204_NO_CONTENT)
