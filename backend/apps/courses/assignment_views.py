from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.courses.models import Content, Course, Module
from apps.courses.tasks import compile_assignment_source_text, _generate_quiz_questions_with_meta
from apps.courses.video_models import VideoTranscript
from apps.progress.models import Assignment, Quiz, QuizQuestion
from utils.decorators import admin_only, tenant_required


_ALLOWED_QUESTION_TYPES = {"MCQ", "SHORT_ANSWER", "TRUE_FALSE"}
_ALLOWED_SELECTION_MODES = {"SINGLE", "MULTIPLE"}


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _as_decimal(value: Any, default: Decimal) -> Decimal:
    if value in (None, ""):
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Invalid decimal value") from exc


def _parse_due_date(value: Any):
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("due_date must be an ISO date/time string")

    dt = parse_datetime(value)
    if dt is not None:
        if timezone.is_naive(dt):
            return timezone.make_aware(dt, timezone.get_current_timezone())
        return dt

    d = parse_date(value)
    if d is not None:
        dt = datetime.combine(d, time.min)
        if timezone.is_naive(dt):
            return timezone.make_aware(dt, timezone.get_current_timezone())
        return dt

    raise ValueError("Invalid due_date format")


def _resolve_scope(course: Course, scope_type_raw: Any, module_id: Any) -> tuple[str, Module | None]:
    scope_type = str(scope_type_raw or "COURSE").upper().strip()
    if scope_type not in {"COURSE", "MODULE"}:
        raise ValueError("scope_type must be COURSE or MODULE")

    module = None
    if scope_type == "MODULE":
        if not module_id:
            raise ValueError("module_id is required for MODULE scope")
        module = get_object_or_404(Module, id=module_id, course=course, is_active=True)

    return scope_type, module


def _normalize_questions(raw_questions: Any) -> list[dict[str, Any]]:
    if raw_questions is None:
        return []
    if not isinstance(raw_questions, list):
        raise ValueError("questions must be an array")

    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_questions, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Question #{idx} must be an object")

        question_type = str(item.get("question_type") or "").upper().strip()
        if question_type not in _ALLOWED_QUESTION_TYPES:
            raise ValueError(f"Question #{idx}: unsupported question_type '{question_type}'")

        prompt = str(item.get("prompt") or "").strip()
        if not prompt:
            raise ValueError(f"Question #{idx}: prompt is required")

        try:
            points = int(item.get("points") or (1 if question_type in {"MCQ", "TRUE_FALSE"} else 2))
        except (TypeError, ValueError):
            raise ValueError(f"Question #{idx}: points must be an integer")
        if points <= 0:
            raise ValueError(f"Question #{idx}: points must be greater than 0")

        explanation = str(item.get("explanation") or "")
        options = item.get("options") or []
        correct_answer = item.get("correct_answer") or {}
        selection_mode = str(item.get("selection_mode") or "SINGLE").upper().strip()

        if question_type == "MCQ":
            if selection_mode not in _ALLOWED_SELECTION_MODES:
                raise ValueError(f"Question #{idx}: selection_mode must be SINGLE or MULTIPLE")

            if not isinstance(options, list):
                raise ValueError(f"Question #{idx}: options must be an array")
            cleaned_options = [str(opt).strip() for opt in options if str(opt).strip()]
            if len(cleaned_options) < 2:
                raise ValueError(f"Question #{idx}: MCQ requires at least 2 options")

            if not isinstance(correct_answer, dict):
                raise ValueError(f"Question #{idx}: correct_answer must be an object")

            if selection_mode == "SINGLE":
                try:
                    option_index = int(correct_answer.get("option_index"))
                except (TypeError, ValueError):
                    raise ValueError(f"Question #{idx}: option_index must be an integer")
                if option_index < 0 or option_index >= len(cleaned_options):
                    raise ValueError(f"Question #{idx}: option_index is out of range")
                normalized_correct = {"option_index": option_index}
            else:
                raw_indices = correct_answer.get("option_indices")
                if not isinstance(raw_indices, list):
                    raise ValueError(f"Question #{idx}: option_indices must be an array")
                indices: list[int] = []
                for raw_index in raw_indices:
                    try:
                        option_index = int(raw_index)
                    except (TypeError, ValueError):
                        raise ValueError(f"Question #{idx}: option_indices must contain integers")
                    if option_index < 0 or option_index >= len(cleaned_options):
                        raise ValueError(f"Question #{idx}: option_indices contain out-of-range index")
                    if option_index not in indices:
                        indices.append(option_index)
                if len(indices) < 2:
                    raise ValueError(f"Question #{idx}: MULTIPLE MCQ requires at least 2 correct answers")
                normalized_correct = {"option_indices": indices}

            normalized.append(
                {
                    "order": idx,
                    "question_type": question_type,
                    "selection_mode": selection_mode,
                    "prompt": prompt,
                    "options": cleaned_options,
                    "correct_answer": normalized_correct,
                    "explanation": explanation,
                    "points": points,
                }
            )
            continue

        if question_type == "TRUE_FALSE":
            if not isinstance(correct_answer, dict):
                raise ValueError(f"Question #{idx}: correct_answer must be an object")
            value = correct_answer.get("value")
            if not isinstance(value, bool):
                raise ValueError(f"Question #{idx}: TRUE_FALSE requires correct_answer.value as boolean")
            normalized.append(
                {
                    "order": idx,
                    "question_type": question_type,
                    "selection_mode": "SINGLE",
                    "prompt": prompt,
                    "options": ["True", "False"],
                    "correct_answer": {"value": value},
                    "explanation": explanation,
                    "points": points,
                }
            )
            continue

        normalized.append(
            {
                "order": idx,
                "question_type": "SHORT_ANSWER",
                "selection_mode": "SINGLE",
                "prompt": prompt,
                "options": [],
                "correct_answer": {},
                "explanation": explanation,
                "points": points,
            }
        )

    return normalized


def _source_material_summary(course: Course, module: Module | None) -> dict[str, int]:
    contents = Content.objects.filter(module__course=course, is_active=True)
    if module is not None:
        contents = contents.filter(module=module)

    text_blocks = contents.filter(content_type="TEXT").exclude(text_content__isnull=True).exclude(text_content__exact="")
    documents = contents.filter(content_type="DOCUMENT").exclude(file_url__isnull=True).exclude(file_url__exact="")
    video_ids = list(contents.filter(content_type="VIDEO").values_list("id", flat=True))
    transcript_count = 0
    if video_ids:
        transcript_count = (
            VideoTranscript.objects.filter(video_asset__content_id__in=video_ids)
            .exclude(full_text__isnull=True)
            .exclude(full_text__exact="")
            .count()
        )

    return {
        "text_blocks": text_blocks.count(),
        "documents": documents.count(),
        "video_transcripts": transcript_count,
    }


def _serialize_assignment(assignment: Assignment, include_questions: bool = True) -> dict[str, Any]:
    quiz = getattr(assignment, "quiz", None)
    questions = []
    if include_questions and quiz:
        for q in quiz.questions.all().order_by("order"):
            questions.append(
                {
                    "id": str(q.id),
                    "order": q.order,
                    "question_type": q.question_type,
                    "selection_mode": q.selection_mode,
                    "prompt": q.prompt,
                    "options": q.options or [],
                    "correct_answer": q.correct_answer or {},
                    "explanation": q.explanation,
                    "points": q.points,
                }
            )

    return {
        "id": str(assignment.id),
        "title": assignment.title,
        "description": assignment.description,
        "instructions": assignment.instructions,
        "due_date": assignment.due_date,
        "max_score": assignment.max_score,
        "passing_score": assignment.passing_score,
        "is_mandatory": assignment.is_mandatory,
        "is_active": assignment.is_active,
        "scope_type": "MODULE" if assignment.module_id else "COURSE",
        "module_id": str(assignment.module_id) if assignment.module_id else None,
        "module_title": assignment.module.title if assignment.module_id else None,
        "assignment_type": "QUIZ" if quiz else "WRITTEN",
        "generation_source": assignment.generation_source,
        "generation_metadata": assignment.generation_metadata or {},
        "questions": questions,
        "created_at": assignment.created_at,
        "updated_at": assignment.updated_at,
    }


def _replace_quiz_questions(assignment: Assignment, questions: list[dict[str, Any]], is_auto_generated: bool = False):
    quiz, _created = Quiz.objects.get_or_create(
        assignment=assignment,
        defaults={
            "schema_version": 1,
            "is_auto_generated": is_auto_generated,
        },
    )
    if is_auto_generated:
        quiz.is_auto_generated = True
        quiz.save(update_fields=["is_auto_generated", "updated_at"])

    quiz.questions.all().delete()
    for payload in questions:
        QuizQuestion.objects.create(
            quiz=quiz,
            order=payload["order"],
            question_type=payload["question_type"],
            selection_mode=payload["selection_mode"],
            prompt=payload["prompt"],
            options=payload["options"],
            correct_answer=payload["correct_answer"],
            explanation=payload["explanation"],
            points=payload["points"],
        )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def assignment_list_create(request, course_id):
    course = get_object_or_404(Course, id=course_id, tenant=request.tenant, is_active=True)

    if request.method == "GET":
        scope = (request.GET.get("scope") or "ALL").upper()
        module_id = request.GET.get("module_id")

        qs = Assignment.objects.filter(course=course, is_active=True).select_related("module").select_related("quiz")
        if scope == "COURSE":
            qs = qs.filter(module__isnull=True)
        elif scope == "MODULE":
            qs = qs.filter(module__isnull=False)
        if module_id:
            qs = qs.filter(module_id=module_id)
        qs = qs.order_by("-created_at")

        return Response([_serialize_assignment(a, include_questions=False) for a in qs], status=status.HTTP_200_OK)

    try:
        scope_type, module = _resolve_scope(course, request.data.get("scope_type"), request.data.get("module_id"))
        assignment_type = str(request.data.get("assignment_type") or "").upper().strip()
        questions_raw = request.data.get("questions")
        if not assignment_type:
            assignment_type = "QUIZ" if questions_raw else "WRITTEN"
        if assignment_type not in {"QUIZ", "WRITTEN"}:
            raise ValueError("assignment_type must be QUIZ or WRITTEN")

        questions = _normalize_questions(questions_raw if assignment_type == "QUIZ" else [])
        if assignment_type == "QUIZ" and not questions:
            raise ValueError("Quiz assignments require at least one question")

        title = str(request.data.get("title") or "").strip()
        if not title:
            raise ValueError("title is required")

        due_date = _parse_due_date(request.data.get("due_date"))
        max_score = _as_decimal(request.data.get("max_score"), Decimal("100"))
        passing_score = _as_decimal(request.data.get("passing_score"), Decimal("70"))

        with transaction.atomic():
            assignment = Assignment.objects.create(
                course=course,
                module=module if scope_type == "MODULE" else None,
                content=None,
                title=title,
                description=str(request.data.get("description") or ""),
                instructions=str(request.data.get("instructions") or ""),
                due_date=due_date,
                max_score=max_score,
                passing_score=passing_score,
                is_mandatory=_as_bool(request.data.get("is_mandatory"), True),
                is_active=_as_bool(request.data.get("is_active"), True),
                generation_source="MANUAL",
                generation_metadata=dict(request.data.get("generation_metadata") or {}),
            )
            if assignment_type == "QUIZ":
                _replace_quiz_questions(assignment, questions, is_auto_generated=False)

        assignment = Assignment.objects.select_related("module").select_related("quiz").get(id=assignment.id)
        return Response(_serialize_assignment(assignment), status=status.HTTP_201_CREATED)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def assignment_detail(request, course_id, assignment_id):
    course = get_object_or_404(Course, id=course_id, tenant=request.tenant, is_active=True)
    assignment = get_object_or_404(
        Assignment.objects.select_related("module").select_related("quiz"),
        id=assignment_id,
        course=course,
        is_active=True,
    )

    if request.method == "GET":
        return Response(_serialize_assignment(assignment), status=status.HTTP_200_OK)

    if request.method == "DELETE":
        assignment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    try:
        scope_type = request.data.get("scope_type")
        module_id = request.data.get("module_id")
        if scope_type is not None or module_id is not None:
            resolved_scope, module = _resolve_scope(
                course,
                scope_type if scope_type is not None else ("MODULE" if assignment.module_id else "COURSE"),
                module_id if module_id is not None else assignment.module_id,
            )
            assignment.module = module if resolved_scope == "MODULE" else None

        assignment_type = request.data.get("assignment_type")
        has_quiz = bool(getattr(assignment, "quiz", None))
        normalized_type = str(assignment_type or ("QUIZ" if has_quiz else "WRITTEN")).upper().strip()
        if normalized_type not in {"QUIZ", "WRITTEN"}:
            raise ValueError("assignment_type must be QUIZ or WRITTEN")

        if "title" in request.data:
            title = str(request.data.get("title") or "").strip()
            if not title:
                raise ValueError("title cannot be empty")
            assignment.title = title
        if "description" in request.data:
            assignment.description = str(request.data.get("description") or "")
        if "instructions" in request.data:
            assignment.instructions = str(request.data.get("instructions") or "")
        if "due_date" in request.data:
            assignment.due_date = _parse_due_date(request.data.get("due_date"))
        if "max_score" in request.data:
            assignment.max_score = _as_decimal(request.data.get("max_score"), assignment.max_score)
        if "passing_score" in request.data:
            assignment.passing_score = _as_decimal(request.data.get("passing_score"), assignment.passing_score)
        if "is_mandatory" in request.data:
            assignment.is_mandatory = _as_bool(request.data.get("is_mandatory"), assignment.is_mandatory)
        if "is_active" in request.data:
            assignment.is_active = _as_bool(request.data.get("is_active"), assignment.is_active)

        questions = None
        if "questions" in request.data:
            questions = _normalize_questions(request.data.get("questions"))
            if normalized_type == "QUIZ" and not questions:
                raise ValueError("Quiz assignments require at least one question")

        with transaction.atomic():
            assignment.save()
            if normalized_type == "WRITTEN":
                quiz = getattr(assignment, "quiz", None)
                if quiz:
                    quiz.delete()
            else:
                if questions is not None:
                    _replace_quiz_questions(assignment, questions, is_auto_generated=False)
                elif not getattr(assignment, "quiz", None):
                    raise ValueError("Quiz assignments require questions when creating a quiz")

        assignment = Assignment.objects.select_related("module").select_related("quiz").get(id=assignment.id)
        return Response(_serialize_assignment(assignment), status=status.HTTP_200_OK)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def assignment_ai_generate(request, course_id):
    course = get_object_or_404(Course, id=course_id, tenant=request.tenant, is_active=True)

    try:
        scope_type, module = _resolve_scope(course, request.data.get("scope_type"), request.data.get("module_id"))
        question_count = int(request.data.get("question_count") or 6)
        if question_count < 2 or question_count > 20:
            raise ValueError("question_count must be between 2 and 20")
        include_short_answer = _as_bool(request.data.get("include_short_answer"), True)
        title_hint = str(request.data.get("title_hint") or "").strip()

        source_summary = _source_material_summary(course, module)
        if (
            source_summary["video_transcripts"] == 0
            and source_summary["documents"] == 0
            and source_summary["text_blocks"] == 0
        ):
            raise ValueError(
                "Upload source content first. AI generation requires a video transcript, document, or text content."
            )

        source_text = compile_assignment_source_text(course=course, module=module, include_fallback=False)
        generated, generation_meta = _generate_quiz_questions_with_meta(
            source_text or course.title, question_count=question_count
        )

        question_payloads: list[dict[str, Any]] = []
        for idx, item in enumerate(generated, start=1):
            q_type = str(item.get("question_type") or "MCQ").upper()
            if q_type == "SHORT_ANSWER" and not include_short_answer:
                continue
            if q_type not in _ALLOWED_QUESTION_TYPES:
                q_type = "MCQ"
            selection_mode = "SINGLE"
            options = list(item.get("options") or [])
            correct_answer = dict(item.get("correct_answer") or {})

            if q_type == "MCQ":
                maybe_mode = str(item.get("selection_mode") or "SINGLE").upper()
                if maybe_mode == "MULTIPLE":
                    raw_indices = correct_answer.get("option_indices")
                    if isinstance(raw_indices, list):
                        normalized_indices = []
                        for raw_index in raw_indices:
                            try:
                                option_index = int(raw_index)
                            except (TypeError, ValueError):
                                continue
                            if option_index not in normalized_indices:
                                normalized_indices.append(option_index)
                        if len(normalized_indices) >= 2:
                            selection_mode = "MULTIPLE"
                            correct_answer = {"option_indices": normalized_indices}
                        else:
                            selection_mode = "SINGLE"
                            correct_answer = {"option_index": int(correct_answer.get("option_index") or 0)}
                    else:
                        correct_answer = {"option_index": int(correct_answer.get("option_index") or 0)}
                else:
                    correct_answer = {"option_index": int(correct_answer.get("option_index") or 0)}
            elif q_type == "TRUE_FALSE":
                selection_mode = "SINGLE"
                correct_answer = {"value": bool(correct_answer.get("value", True))}
                options = ["True", "False"]
            else:
                selection_mode = "SINGLE"
                correct_answer = {}
                options = []

            question_payloads.append(
                {
                    "order": len(question_payloads) + 1,
                    "question_type": q_type,
                    "selection_mode": selection_mode,
                    "prompt": str(item.get("prompt") or f"Question {idx}"),
                    "options": options,
                    "correct_answer": correct_answer,
                    "explanation": str(item.get("explanation") or ""),
                    "points": int(item.get("points") or (1 if q_type in {"MCQ", "TRUE_FALSE"} else 2)),
                }
            )

        if not question_payloads:
            raise ValueError("Could not generate questions for this scope")

        # Keep only requested question count after optional filtering.
        question_payloads = question_payloads[:question_count]
        # Revalidate generated payloads with the same manual rules.
        question_payloads = _normalize_questions(question_payloads)

        base_title = title_hint or (module.title if module is not None else course.title)
        assignment_title = f"AI Quiz: {base_title}"
        assignment_description = "AI-generated quiz based on the selected course material."
        assignment_instructions = (
            "Answer each question carefully. Objective questions are auto-graded; "
            "short answers may require manual review."
        )

        with transaction.atomic():
            assignment = Assignment.objects.create(
                course=course,
                module=module if scope_type == "MODULE" else None,
                content=None,
                title=assignment_title,
                description=assignment_description,
                instructions=assignment_instructions,
                max_score=Decimal("100"),
                passing_score=Decimal("70"),
                is_mandatory=True,
                is_active=True,
                generation_source="MANUAL",
                generation_metadata={
                    "origin": "AI_ON_DEMAND",
                    "scope_type": scope_type,
                    "module_id": str(module.id) if module else None,
                    "question_count": len(question_payloads),
                    "source_material": source_summary,
                    "generator_provider": generation_meta.get("provider", ""),
                    "generator_model": generation_meta.get("model", ""),
                },
            )
            _replace_quiz_questions(assignment, question_payloads, is_auto_generated=True)

        assignment = Assignment.objects.select_related("module").select_related("quiz").get(id=assignment.id)
        return Response(_serialize_assignment(assignment), status=status.HTTP_201_CREATED)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
