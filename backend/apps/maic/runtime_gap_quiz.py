"""Small MAIC v2 quiz-grading runtime surface.

Phase 13 names quiz grading as one of the OpenMAIC runtime gaps.  The
full phase eventually persists attempts, but the smooth-demo gap is
smaller: v2 needs a tenant-gated HTTP route that can score a short
answer using the same production grading logic already used by the
legacy MAIC route.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from rest_framework import status
from rest_framework.response import Response

from apps.courses.maic_generation_service import (
    _fallback_quiz_grade_deterministic,
    fallback_quiz_grade,
)
from apps.courses.maic_views import _get_ai_config


@dataclass(frozen=True)
class QuizGradePayload:
    question: str
    user_answer: str
    expected_answer: str
    rubric: str | None
    points: float
    points_was_provided: bool


def normalize_quiz_grade_payload(data: Any) -> tuple[QuizGradePayload | None, Response | None]:
    """Validate the two payload shapes we need to support.

    OpenMAIC sends ``question``, ``userAnswer`` and ``points``.  Existing
    LearnPuddle callers send ``question``, ``answer`` and sometimes
    ``commentPrompt``.  Both are normalized into one service-level shape.
    """
    if not isinstance(data, dict):
        return None, Response(
            {"error": "JSON object body is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    question = _clean_str(data.get("question") or data.get("prompt"))
    user_answer = _clean_str(
        data.get("userAnswer")
        or data.get("studentAnswer")
        or data.get("answer")
    )
    expected_answer = _clean_str(
        data.get("expectedAnswer")
        or data.get("correctAnswer")
        or data.get("answerKey")
        or question
    )
    rubric = _clean_str(data.get("rubric") or data.get("commentPrompt")) or None

    if not question:
        return None, Response(
            {"error": "question is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not user_answer:
        return None, Response(
            {"error": "userAnswer is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    points_was_provided = "points" in data
    points = _coerce_points(data.get("points", 100))
    if points is None:
        return None, Response(
            {"error": "points must be a positive finite number."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return (
        QuizGradePayload(
            question=question,
            user_answer=user_answer,
            expected_answer=expected_answer,
            rubric=rubric,
            points=points,
            points_was_provided=points_was_provided,
        ),
        None,
    )


def grade_quiz_payload(payload: QuizGradePayload, tenant) -> tuple[dict[str, Any] | None, Response | None]:
    """Grade a normalized quiz payload for ``tenant``.

    Reuses the existing ``TenantAIConfig`` lookup and grading service.  If
    the tenant has no LLM key configured, short-circuit to the same
    deterministic production fallback instead of making a doomed network
    call with an empty bearer token.
    """
    config, err = _get_ai_config(tenant)
    if err:
        return None, err

    if getattr(config, "llm_api_key_encrypted", ""):
        result = fallback_quiz_grade(
            student_answer=payload.user_answer,
            expected_answer=payload.expected_answer,
            rubric=payload.rubric,
            config=config,
        )
    else:
        result = _fallback_quiz_grade_deterministic(
            payload.user_answer,
            payload.expected_answer,
        )

    score_percent = _bounded_percent(result.get("score"))
    if payload.points_was_provided:
        score = round((score_percent / 100) * payload.points)
    else:
        score = score_percent

    feedback = str(result.get("feedback") or result.get("comment") or "")
    is_correct = bool(result.get("isCorrect", score_percent >= 70))

    return (
        {
            "score": score,
            "feedback": feedback,
            "isCorrect": is_correct,
            # OpenMAIC's response shape uses `comment`; keeping both lets
            # the v2 route satisfy either renderer without frontend glue.
            "comment": feedback,
            "points": _clean_number(payload.points),
            "scorePercent": score_percent,
        },
        None,
    )


def _clean_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _coerce_points(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        points = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(points) or points <= 0:
        return None
    return points


def _bounded_percent(value: Any) -> int:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        score = 0
    return max(0, min(100, score))


def _clean_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value
