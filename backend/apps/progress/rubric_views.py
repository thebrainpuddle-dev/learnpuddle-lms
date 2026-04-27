# apps/progress/rubric_views.py
#
# TASK-044 — Rubric CRUD, cloning, assignment attachment, evaluation.

import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.audit import log_audit
from utils.decorators import admin_only, teacher_or_admin, tenant_required
from utils.helpers import make_pagination_class

from .models import Assignment, AssignmentSubmission
from .rubric_models import (
    Rubric,
    RubricCriterion,
    RubricEvaluation,
    RubricLevel,
)
from .rubric_serializers import (
    AttachRubricSerializer,
    RubricEvaluateSerializer,
    RubricEvaluationReadSerializer,
    RubricSerializer,
    RubricWriteSerializer,
)

logger = logging.getLogger(__name__)


# ===========================================================================
# Admin: Rubric CRUD
# ===========================================================================


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def rubric_list_create(request):
    if request.method == "GET":
        qs = (
            Rubric.objects.all()
            .prefetch_related("criteria__levels")
            .order_by("-created_at")
        )
        search = request.GET.get("search")
        if search:
            qs = qs.filter(title__icontains=search)
        active = request.GET.get("is_active")
        if active is not None:
            qs = qs.filter(is_active=active.lower() in ("1", "true", "yes"))

        paginator = make_pagination_class(25, 100)()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            return paginator.get_paginated_response(
                RubricSerializer(page, many=True).data
            )
        return Response(
            {"results": RubricSerializer(qs, many=True).data},
            status=status.HTTP_200_OK,
        )

    # POST
    serializer = RubricWriteSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        rubric = serializer.save()
    log_audit(
        request=request,
        action="CREATE",
        target_type="Rubric",
        target_id=str(rubric.id),
        target_repr=rubric.title,
        changes={"title": rubric.title},
    )
    return Response(RubricSerializer(rubric).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def rubric_detail(request, rubric_id):
    rubric = get_object_or_404(
        Rubric.objects.prefetch_related("criteria__levels"),
        id=rubric_id,
        tenant=request.tenant,
    )

    if request.method == "GET":
        return Response(RubricSerializer(rubric).data, status=status.HTTP_200_OK)

    if request.method == "PATCH":
        serializer = RubricWriteSerializer(
            rubric, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            rubric = serializer.save()
        log_audit(
            request=request,
            action="UPDATE",
            target_type="Rubric",
            target_id=str(rubric.id),
            target_repr=rubric.title,
            changes=request.data,
        )
        return Response(RubricSerializer(rubric).data, status=status.HTTP_200_OK)

    # DELETE
    rubric_id_str = str(rubric.id)
    rubric.delete()
    log_audit(
        request=request,
        action="DELETE",
        target_type="Rubric",
        target_id=rubric_id_str,
    )
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def rubric_clone(request, rubric_id):
    """Deep-copy a rubric including every criterion and level."""
    source = get_object_or_404(
        Rubric.objects.prefetch_related("criteria__levels"),
        id=rubric_id,
        tenant=request.tenant,
    )

    new_title = (request.data.get("title") or f"{source.title} (Copy)").strip()

    with transaction.atomic():
        clone = Rubric.objects.create(
            tenant=request.tenant,
            title=new_title,
            description=source.description,
            is_active=source.is_active,
            created_by=request.user if request.user.is_authenticated else None,
        )
        for criterion in source.criteria.all():
            new_criterion = RubricCriterion.objects.create(
                rubric=clone,
                title=criterion.title,
                description=criterion.description,
                max_points=criterion.max_points,
                order=criterion.order,
            )
            for level in criterion.levels.all():
                RubricLevel.objects.create(
                    criterion=new_criterion,
                    title=level.title,
                    description=level.description,
                    points=level.points,
                    order=level.order,
                )
        clone.recompute_total_points(save=True)

    log_audit(
        request=request,
        action="CREATE",
        target_type="Rubric",
        target_id=str(clone.id),
        target_repr=clone.title,
        changes={"cloned_from": str(source.id)},
    )
    return Response(RubricSerializer(clone).data, status=status.HTTP_201_CREATED)


# ===========================================================================
# Admin: attach rubric to assignment
# ===========================================================================


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def assignment_attach_rubric(request, assignment_id):
    assignment = get_object_or_404(
        Assignment.objects,
        id=assignment_id,
        tenant=request.tenant,
    )

    if request.method == "GET":
        data = {
            "assignment_id": str(assignment.id),
            "rubric": (
                RubricSerializer(assignment.rubric).data if assignment.rubric else None
            ),
        }
        return Response(data, status=status.HTTP_200_OK)

    # POST — attach / detach
    serializer = AttachRubricSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    rubric_id = serializer.validated_data.get("rubric_id")

    if rubric_id is None:
        assignment.rubric = None
    else:
        rubric = get_object_or_404(
            Rubric.objects, id=rubric_id, tenant=request.tenant,
        )
        assignment.rubric = rubric
    assignment.save(update_fields=["rubric", "updated_at"])

    log_audit(
        request=request,
        action="UPDATE",
        target_type="Assignment",
        target_id=str(assignment.id),
        target_repr=assignment.title,
        changes={"rubric_id": str(rubric_id) if rubric_id else None},
    )
    return Response(
        {
            "assignment_id": str(assignment.id),
            "rubric": (
                RubricSerializer(assignment.rubric).data if assignment.rubric else None
            ),
        },
        status=status.HTTP_200_OK,
    )


# ===========================================================================
# Admin / evaluator: evaluate a submission
# ===========================================================================


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def submission_evaluate(request, submission_id):
    submission = get_object_or_404(
        AssignmentSubmission.objects.select_related("assignment__rubric"),
        id=submission_id,
    )
    # Tenant isolation — submissions have a nullable tenant FK for legacy rows.
    if submission.tenant_id not in (None, request.tenant.id):
        return Response(
            {"error": "Submission not found in this tenant."},
            status=status.HTTP_404_NOT_FOUND,
        )
    # Evaluator must be in the same tenant.
    if (
        request.user.role != "SUPER_ADMIN"
        and getattr(request.user, "tenant_id", None) != request.tenant.id
    ):
        return Response(
            {"error": "Evaluator must belong to this tenant."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = RubricEvaluateSerializer(
        data=request.data,
        context={"request": request, "submission": submission},
    )
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    rubric: Rubric = data["_rubric"]
    normalized_scores = data["_normalized_scores"]
    total_score = data["_total_score"]

    with transaction.atomic():
        evaluation, created = RubricEvaluation.all_objects.update_or_create(
            submission=submission,
            evaluator=request.user,
            defaults={
                "tenant": request.tenant,
                "rubric": rubric,
                "scores": normalized_scores,
                "total_score": total_score,
                "feedback": data.get("feedback", "") or "",
            },
        )
        # Mirror into the AssignmentSubmission so the gradebook sees a score.
        submission.score = total_score
        submission.feedback = data.get("feedback", "") or submission.feedback
        submission.graded_by = request.user
        from django.utils import timezone
        submission.graded_at = timezone.now()
        submission.status = "GRADED"
        submission.save(
            update_fields=["score", "feedback", "graded_by", "graded_at", "status", "updated_at"],
        )

    log_audit(
        request=request,
        action="CREATE" if created else "UPDATE",
        target_type="RubricEvaluation",
        target_id=str(evaluation.id),
        target_repr=f"submission={submission.id}",
        changes={"total_score": str(total_score)},
    )
    return Response(
        RubricEvaluationReadSerializer(evaluation).data,
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


# ===========================================================================
# Teacher: view own evaluation
# ===========================================================================


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def submission_evaluation_view(request, submission_id):
    submission = get_object_or_404(
        AssignmentSubmission.objects.select_related("assignment__rubric"),
        id=submission_id,
    )
    if submission.tenant_id not in (None, request.tenant.id):
        return Response(
            {"error": "Submission not found in this tenant."},
            status=status.HTTP_404_NOT_FOUND,
        )
    # Teachers may only see their own submission.
    if (
        request.user.role not in ("SCHOOL_ADMIN", "SUPER_ADMIN", "HOD", "IB_COORDINATOR")
        and submission.teacher_id != request.user.id
    ):
        return Response(
            {"error": "Forbidden."}, status=status.HTTP_403_FORBIDDEN,
        )

    evaluations = RubricEvaluation.objects.filter(submission=submission).order_by(
        "-updated_at"
    )
    return Response(
        {
            "submission_id": str(submission.id),
            "rubric": (
                RubricSerializer(submission.assignment.rubric).data
                if submission.assignment.rubric
                else None
            ),
            "evaluations": RubricEvaluationReadSerializer(evaluations, many=True).data,
        },
        status=status.HTTP_200_OK,
    )
