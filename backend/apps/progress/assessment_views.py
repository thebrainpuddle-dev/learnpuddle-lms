# apps/progress/assessment_views.py
#
# Views for TASK-043: Question Bank + Advanced Quizzing.

import csv
import io
import logging
import random

from django.db import IntegrityError, transaction
from django.db.models import (
    Avg,
    Count,
    ExpressionWrapper,
    F,
    FloatField,
    Max,
    Q,
)
from django.db.models.functions import Cast, NullIf
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.courses.models import Content, Course
from utils.decorators import admin_only, teacher_or_admin, tenant_required
from utils.helpers import make_pagination_class, tenant_teachers_qs
from utils.responses import error_response

from .assessment_models import (
    Question,
    QuestionBank,
    QuestionChoice,
    QuizAttempt,
    QuizConfig,
)
from .assessment_serializers import (
    GradebookRowSerializer,
    QuestionBankSerializer,
    QuestionSerializer,
    QuizAttemptSerializer,
    QuizAttemptStartSerializer,
    QuizAttemptSubmitSerializer,
    QuizConfigSerializer,
)
from .models import AssignmentSubmission, TeacherProgress

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper: scoring a single answer
# ---------------------------------------------------------------------------

def _score_answer(question: dict, answer, *, multi_partial_credit: bool = False) -> float:
    """Return the fraction of `question`'s points that `answer` should earn.

    Values:
      * 1.0 — fully correct
      * 0.0 — wrong / unanswered / un-auto-gradable
      * 0.0..1.0 — partial credit (MULTI only, when `multi_partial_credit=True`)

    `question` is a dict from `questions_snapshot` with keys:
      - type: the Question.question_type
      - choices: list of {id, text, is_correct, order}  (for choice-based)
    `answer` depends on type:
      - MCQ / TRUE_FALSE     : choice_id (string)
      - MULTI                : list of choice_ids
      - SHORT / ESSAY        : text — never auto-graded (reviewer workflow)
    """
    qtype = question.get("type")
    choices = question.get("choices") or []

    if qtype in ("MCQ", "TRUE_FALSE"):
        correct_ids = [c["id"] for c in choices if c.get("is_correct")]
        if correct_ids and str(answer) in correct_ids:
            return 1.0
        return 0.0

    if qtype == "MULTI":
        if not isinstance(answer, (list, tuple)):
            return 0.0
        correct_ids = {c["id"] for c in choices if c.get("is_correct")}
        all_ids = {c["id"] for c in choices}
        answer_ids = {str(a) for a in answer if str(a) in all_ids}
        if not correct_ids:
            return 0.0
        if multi_partial_credit:
            # Negative-marking style: +1 per correct selection, -1 per wrong
            # selection, normalized to total_correct. Clamped to [0, 1].
            correct_selected = len(answer_ids & correct_ids)
            wrong_selected = len(answer_ids - correct_ids)
            raw = (correct_selected - wrong_selected) / float(len(correct_ids))
            return max(0.0, min(1.0, raw))
        # All-or-nothing (default)
        return 1.0 if answer_ids == correct_ids else 0.0

    # SHORT / ESSAY — free text, not auto-graded by default
    return 0.0


def _is_answer_correct(question: dict, answer) -> bool:
    """Backwards-compat wrapper. Returns True iff fully correct (no partial)."""
    return _score_answer(question, answer, multi_partial_credit=False) >= 1.0


def _snapshot_question(q: Question) -> dict:
    """Serialize a Question + its choices for storage in an attempt."""
    return {
        "id": str(q.id),
        "type": q.question_type,
        "prompt": q.prompt,
        "points": q.points,
        "difficulty": q.difficulty,
        "explanation": q.explanation,
        "choices": [
            {
                "id": str(c.id),
                "text": c.text,
                "is_correct": c.is_correct,
                "order": c.order,
            }
            for c in q.choices.all()
        ],
    }


# ===========================================================================
# Admin: Question Bank CRUD
# ===========================================================================

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def question_bank_list_create(request):
    if request.method == "GET":
        qs = QuestionBank.objects.all().annotate(
            question_count=Count("questions"),
        ).order_by("title")

        search = request.GET.get("search")
        if search:
            qs = qs.filter(
                Q(title__icontains=search) | Q(description__icontains=search),
            )

        paginator = make_pagination_class(25, 100)()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            ser = QuestionBankSerializer(page, many=True)
            return paginator.get_paginated_response(ser.data)
        ser = QuestionBankSerializer(qs, many=True)
        return Response({"results": ser.data}, status=status.HTTP_200_OK)

    # POST
    ser = QuestionBankSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    bank = QuestionBank.objects.create(
        tenant=request.tenant,
        created_by=request.user,
        **ser.validated_data,
    )
    return Response(
        QuestionBankSerializer(bank).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def question_bank_detail(request, bank_id):
    bank = get_object_or_404(QuestionBank, id=bank_id, tenant=request.tenant)

    if request.method == "GET":
        return Response(QuestionBankSerializer(bank).data)

    if request.method == "PATCH":
        ser = QuestionBankSerializer(bank, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(QuestionBankSerializer(bank).data)

    # DELETE
    bank.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def question_bank_questions(request, bank_id):
    bank = get_object_or_404(QuestionBank, id=bank_id, tenant=request.tenant)

    if request.method == "GET":
        qs = bank.questions.prefetch_related("choices").order_by("order", "created_at")

        qtype = request.GET.get("type")
        if qtype:
            qs = qs.filter(question_type=qtype)

        paginator = make_pagination_class(50, 200)()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            ser = QuestionSerializer(page, many=True)
            return paginator.get_paginated_response(ser.data)
        ser = QuestionSerializer(qs, many=True)
        return Response({"results": ser.data}, status=status.HTTP_200_OK)

    # POST — create question (+ choices)
    data = dict(request.data)
    data["bank"] = str(bank.id)
    ser = QuestionSerializer(data=data, context={"request": request})
    ser.is_valid(raise_exception=True)
    question = ser.save()
    return Response(
        QuestionSerializer(question).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def question_detail(request, question_id):
    question = get_object_or_404(
        Question.objects.prefetch_related("choices"),
        id=question_id,
        tenant=request.tenant,
    )

    if request.method == "GET":
        return Response(QuestionSerializer(question).data)

    if request.method == "PATCH":
        ser = QuestionSerializer(
            question, data=request.data, partial=True,
            context={"request": request},
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(QuestionSerializer(question).data)

    # DELETE
    question.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ===========================================================================
# Admin: Quiz Config per Content
# ===========================================================================

@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def quiz_config_for_content(request, content_id):
    content = get_object_or_404(
        Content.objects.select_related("module__course__tenant"),
        id=content_id,
        module__course__tenant=request.tenant,
    )

    config, _ = QuizConfig.objects.get_or_create(
        content=content,
        defaults={"tenant": request.tenant},
    )

    if request.method == "GET":
        return Response(QuizConfigSerializer(config).data)

    # PATCH
    ser = QuizConfigSerializer(config, data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    # M2M needs explicit handling — enforce tenant isolation LOUDLY: return 400
    # rather than silently drop cross-tenant bank IDs (M2).
    banks = ser.validated_data.pop("source_question_banks", None)
    if banks is not None:
        cross_tenant = [
            str(b.id) for b in banks if b.tenant_id != request.tenant.id
        ]
        if cross_tenant:
            return Response(
                {
                    "error": {
                        "message": "One or more question banks do not belong to this tenant.",
                        "code": "CROSS_TENANT_BANK",
                    },
                    "code": "CROSS_TENANT_BANK",
                    "invalid_bank_ids": cross_tenant,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    for attr, value in ser.validated_data.items():
        setattr(config, attr, value)
    config.save()
    if banks is not None:
        config.source_question_banks.set([b.id for b in banks])
    return Response(QuizConfigSerializer(config).data)


# ===========================================================================
# Teacher: Start / Submit / List Attempts
# ===========================================================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def quiz_attempt_start(request, content_id):
    return _quiz_attempt_start_core(request, content_id)


def _quiz_attempt_start_core(request, content_id):
    """Start a new attempt; enforces max_attempts + assembles questions."""
    content = get_object_or_404(
        Content.objects.select_related("module__course"),
        id=content_id,
        module__course__tenant=request.tenant,
    )

    try:
        config = QuizConfig.objects.select_related("tenant").prefetch_related(
            "source_question_banks",
        ).get(content=content)
    except QuizConfig.DoesNotExist:
        return error_response(
            "No quiz configuration found for this content.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # Collect candidate questions from linked banks
    banks = list(config.source_question_banks.all())
    question_qs = (
        Question.objects.filter(bank__in=banks)
        .prefetch_related("choices")
    )
    all_questions = list(question_qs)

    if not all_questions:
        return error_response(
            "Quiz has no questions configured.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Random selection
    if config.random_selection_count and config.random_selection_count > 0:
        count = min(config.random_selection_count, len(all_questions))
        chosen = random.sample(all_questions, count)
    else:
        chosen = list(all_questions)

    # Shuffle questions
    if config.shuffle_questions:
        random.shuffle(chosen)

    # Build snapshot
    snapshot = []
    max_score = 0
    for q in chosen:
        snap = _snapshot_question(q)
        if config.shuffle_choices and snap["choices"]:
            random.shuffle(snap["choices"])
        snapshot.append(snap)
        max_score += q.points

    # H2 — Attempt creation must be race-free. Lock the QuizConfig row for
    # this content so two parallel start calls serialize, then re-count
    # existing attempts inside the transaction. The unique_together on
    # (teacher, content, attempt_number) is the final backstop; if we still
    # hit IntegrityError we translate it to 409 instead of 500.
    try:
        with transaction.atomic():
            QuizConfig.objects.select_for_update().filter(pk=config.pk).first()
            existing_count = (
                QuizAttempt.objects.select_for_update()
                .filter(teacher=request.user, content=content)
                .count()
            )
            if config.max_attempts and existing_count >= config.max_attempts:
                return error_response(
                    "Maximum attempts reached for this quiz.",
                    status_code=status.HTTP_403_FORBIDDEN,
                    code="MAX_ATTEMPTS_REACHED",
                )
            attempt = QuizAttempt.objects.create(
                tenant=request.tenant,
                teacher=request.user,
                content=content,
                attempt_number=existing_count + 1,
                status="IN_PROGRESS",
                questions_snapshot=snapshot,
                max_score=max_score,
            )
    except IntegrityError:
        # Two concurrent starts collided on unique_together; one of them won.
        # The loser gets 409 so the client can retry / refresh.
        logger.info(
            "QuizAttempt concurrent-create collision for teacher=%s content=%s",
            request.user.id, content.id,
        )
        return error_response(
            "Another attempt was just started; please refresh and try again.",
            status_code=status.HTTP_409_CONFLICT,
            code="ATTEMPT_RACE",
        )

    # Don't leak `is_correct` back to the teacher
    sanitized = []
    for q in snapshot:
        s = dict(q)
        s["choices"] = [
            {"id": c["id"], "text": c["text"], "order": c["order"]}
            for c in q["choices"]
        ]
        s.pop("explanation", None)
        sanitized.append(s)

    return Response(
        {
            "id": str(attempt.id),
            "attempt_number": attempt.attempt_number,
            "status": attempt.status,
            "started_at": attempt.started_at,
            "time_limit_seconds": config.time_limit_seconds,
            "max_score": float(attempt.max_score),
            "questions": sanitized,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def quiz_attempt_submit(request, attempt_id):
    """Submit an attempt; grades auto-gradable questions & stores answers."""
    attempt = get_object_or_404(
        QuizAttempt.objects.select_related("content"),
        id=attempt_id,
        tenant=request.tenant,
        teacher=request.user,
    )

    if attempt.status != "IN_PROGRESS":
        return error_response(
            "This attempt is already submitted.",
            status_code=status.HTTP_400_BAD_REQUEST,
            code="ATTEMPT_ALREADY_SUBMITTED",
        )

    ser = QuizAttemptSubmitSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    answers = ser.validated_data["answers"]
    client_time_spent = ser.validated_data.get("time_spent_seconds")

    # Load config to validate time-limit
    try:
        config = QuizConfig.objects.get(content=attempt.content)
    except QuizConfig.DoesNotExist:
        config = None

    now = timezone.now()
    elapsed = int((now - attempt.started_at).total_seconds())
    if client_time_spent is not None:
        # Trust min(server elapsed, client-reported)
        attempt.time_spent_seconds = min(elapsed, client_time_spent)
    else:
        attempt.time_spent_seconds = elapsed

    expired = False
    if config and config.time_limit_seconds:
        # 5 second grace
        if elapsed > config.time_limit_seconds + 5:
            expired = True

    # M3 — If the submission arrived past the deadline, we keep the attempt
    # but discard the (untrustworthy) client-supplied answers and score 0.
    # This prevents a teacher from holding the window open indefinitely and
    # then submitting answers well after time_limit_seconds.
    if expired:
        answers = {}

    # Score (supports partial credit for MULTI when configured — M1).
    multi_partial = bool(config and config.multi_partial_credit)
    score = 0.0
    for q in attempt.questions_snapshot:
        qid = q.get("id")
        if qid is None:
            continue
        pts = float(q.get("points") or 0)
        ans = answers.get(qid)
        if ans is None:
            continue
        fraction = _score_answer(q, ans, multi_partial_credit=multi_partial)
        score += pts * fraction

    attempt.answers = answers
    attempt.score = score
    attempt.passed = False
    if attempt.max_score:
        percent = float(score) / float(attempt.max_score) * 100.0
        if config and percent >= float(config.pass_threshold_percent):
            attempt.passed = True

    attempt.submitted_at = now
    attempt.status = "EXPIRED" if expired else "SUBMITTED"
    attempt.save()

    show_answers = bool(config and config.show_correct_answers_after)
    response_snapshot = attempt.questions_snapshot
    if not show_answers:
        # Strip correct-answer flags + explanations
        response_snapshot = []
        for q in attempt.questions_snapshot:
            s = dict(q)
            s["choices"] = [
                {"id": c["id"], "text": c["text"], "order": c["order"]}
                for c in q["choices"]
            ]
            s.pop("explanation", None)
            response_snapshot.append(s)

    return Response(
        {
            "id": str(attempt.id),
            "status": attempt.status,
            "score": float(attempt.score),
            "max_score": float(attempt.max_score),
            "score_percent": attempt.score_percent,
            "passed": attempt.passed,
            "time_spent_seconds": attempt.time_spent_seconds,
            "submitted_at": attempt.submitted_at,
            "questions": response_snapshot,
            "answers": attempt.answers,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def my_quiz_attempts(request):
    qs = (
        QuizAttempt.objects.filter(teacher=request.user)
        .select_related("content", "content__module__course")
        .order_by("-started_at")
    )
    content_id = request.GET.get("content_id")
    if content_id:
        qs = qs.filter(content_id=content_id)

    # H1 — preload QuizConfig rows for all attempts on this page so the
    # sanitized serializer can decide whether to reveal the answer key
    # without issuing one query per row.
    def _config_map(rows):
        content_ids = {a.content_id for a in rows}
        configs = QuizConfig.objects.filter(content_id__in=content_ids)
        return {c.content_id: c for c in configs}

    rows = list(qs)
    ctx = {"request": request, "_quiz_configs_by_content": _config_map(rows)}
    ser = QuizAttemptSerializer(rows, many=True, context=ctx)
    if not rows:
        return Response({}, status=status.HTTP_200_OK)
    return Response({"results": ser.data}, status=status.HTTP_200_OK)


# ===========================================================================
# Admin: Centralized Gradebook
# ===========================================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def course_gradebook(request, course_id):
    """
    Return per-teacher aggregated gradebook for a course:
      - # of quiz attempts, best %, pass count
      - # of assignment submissions, # graded, avg score
      - progress_percent
    """
    course = get_object_or_404(
        Course.objects.filter(tenant=request.tenant),
        id=course_id,
    )

    teachers = list(tenant_teachers_qs(request.tenant).order_by("first_name", "last_name"))

    # Pre-compute aggregates in as few queries as possible to avoid N+1.
    # H3 — per-attempt percent first, THEN take max across attempts.
    # Aggregating Max(score) and Max(max_score) independently is wrong
    # because random-selection attempts have different max_scores.
    per_attempt_percent = ExpressionWrapper(
        Cast(F("score"), FloatField())
        * 100.0
        / NullIf(Cast(F("max_score"), FloatField()), 0),
        output_field=FloatField(),
    )
    quiz_agg = (
        QuizAttempt.objects.filter(
            tenant=request.tenant,
            content__module__course=course,
        )
        .annotate(percent=per_attempt_percent)
        .values("teacher_id")
        .annotate(
            attempts=Count("id"),
            best_percent=Max("percent"),
            pass_count=Count("id", filter=Q(passed=True)),
        )
    )
    quiz_by_teacher = {
        str(row["teacher_id"]): row for row in quiz_agg
    }

    assign_agg = (
        AssignmentSubmission.objects.filter(
            tenant=request.tenant,
            assignment__course=course,
        )
        .values("teacher_id")
        .annotate(
            submitted=Count("id"),
            graded=Count("id", filter=Q(status="GRADED")),
            avg_score=Avg("score"),
        )
    )
    assign_by_teacher = {str(row["teacher_id"]): row for row in assign_agg}

    # Progress %: take the course-level TeacherProgress (content=NULL) or
    # average over content-level rows as fallback.
    progress_agg = (
        TeacherProgress.objects.filter(
            tenant=request.tenant, course=course,
        )
        .values("teacher_id")
        .annotate(avg_pct=Avg("progress_percentage"))
    )
    progress_by_teacher = {str(row["teacher_id"]): row for row in progress_agg}

    rows = []
    for teacher in teachers:
        tid = str(teacher.id)
        qa = quiz_by_teacher.get(tid, {})
        aa = assign_by_teacher.get(tid, {})
        pa = progress_by_teacher.get(tid, {})

        # H3 — best_percent is already per-attempt max; guard against None
        # when the teacher has no attempts.
        best_percent = qa.get("best_percent")
        best_percent = float(best_percent) if best_percent is not None else 0.0

        rows.append({
            "teacher_id": teacher.id,
            "teacher_name": teacher.get_full_name() or teacher.email,
            "teacher_email": teacher.email,
            "course_id": course.id,
            "course_title": course.title,
            "quiz_attempts": qa.get("attempts", 0),
            "quiz_best_score_percent": round(best_percent, 2),
            "quiz_passed": qa.get("pass_count", 0),
            "assignments_submitted": aa.get("submitted", 0),
            "assignments_graded": aa.get("graded", 0),
            "assignments_avg_score": float(aa.get("avg_score") or 0),
            "progress_percent": float(pa.get("avg_pct") or 0),
        })

    ser = GradebookRowSerializer(rows, many=True)
    return Response({"results": ser.data}, status=status.HTTP_200_OK)
