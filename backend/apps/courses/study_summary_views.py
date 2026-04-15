"""
Student-facing API views for AI Study Summaries.

Endpoints:
    POST   /api/v1/student/study-summaries/generate/           — Generate (SSE stream or cached)
    GET    /api/v1/student/study-summaries/                     — List student's summaries
    GET    /api/v1/student/study-summaries/<summary_id>/        — Get full summary detail
    DELETE /api/v1/student/study-summaries/<summary_id>/delete/ — Delete a summary
"""

import json
import logging

from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.courses.maic_models import TenantAIConfig
from apps.courses.models import Content
from apps.courses.study_summary_models import StudySummary
from apps.courses.study_summary_service import (
    extract_content_text,
    compute_text_hash,
    generate_study_summary_sse,
)
from utils.course_access import is_student_assigned_to_course
from utils.decorators import student_or_admin, tenant_required, check_feature

logger = logging.getLogger(__name__)


def _check_generation_throttle(request):
    """Throttle removed — always allow generation."""
    return None


# ─── Generate Study Summary ─────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_study_summary_generate(request):
    """
    Generate an AI study summary for a content item.

    If a cached summary exists with a matching source_text_hash, returns it
    immediately as JSON. Otherwise, streams SSE events as the summary is
    generated, then persists the result.

    Request body: {"content_id": "<uuid>"}
    """
    content_id = request.data.get("content_id")
    if not content_id:
        return Response(
            {"error": "content_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Fetch content and validate course access
    try:
        content = Content.objects.get(
            pk=content_id,
            is_active=True,
            module__course__tenant=request.tenant,
            module__course__is_published=True,
            module__course__is_active=True,
        )
    except Content.DoesNotExist:
        return Response(
            {"error": "Content not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    course = content.module.course
    if not is_student_assigned_to_course(request.user, course):
        return Response(
            {"error": "You are not assigned to this course"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Check for shared teacher summary — return it if available
    shared = StudySummary.all_objects.filter(
        content=content,
        is_shared=True,
        status='READY',
        generated_by__isnull=False,
        content__module__course__tenant=request.tenant,
    ).select_related('generated_by').first()

    if shared:
        return Response({
            "id": str(shared.id),
            "cached": True,
            "is_shared": True,
            "shared_by": (
                shared.generated_by.get_full_name()
                if shared.generated_by else None
            ),
            "status": shared.status,
            "summary_data": shared.summary_data,
            "created_at": shared.created_at.isoformat(),
            "updated_at": shared.updated_at.isoformat(),
        })

    # Check AI config
    try:
        ai_config = TenantAIConfig.objects.get(tenant=request.tenant)
    except TenantAIConfig.DoesNotExist:
        return Response(
            {"error": "AI provider not configured for this institution"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # Extract source text and compute hash for cache check
    source_text = extract_content_text(content)
    current_hash = compute_text_hash(source_text) if source_text else ''

    # Check for cached summary
    try:
        existing = StudySummary.all_objects.filter(
            student=request.user,
            content=content,
        ).first()
        if not existing:
            raise StudySummary.DoesNotExist
        if existing.status == 'READY' and existing.source_text_hash == current_hash and current_hash:
            return Response({
                "id": str(existing.id),
                "cached": True,
                "status": existing.status,
                "summary_data": existing.summary_data,
                "created_at": existing.created_at.isoformat(),
                "updated_at": existing.updated_at.isoformat(),
            })
        # Content changed or previous attempt failed — regenerate
        summary_obj = existing
    except StudySummary.DoesNotExist:
        summary_obj = None

    # ── Throttle only actual generation (not cache hits) ──
    throttle_response = _check_generation_throttle(request)
    if throttle_response:
        return throttle_response

    # Create or update the summary record
    if summary_obj:
        summary_obj.status = 'GENERATING'
        summary_obj.summary_data = {}
        summary_obj.source_text_hash = current_hash
        summary_obj.save(update_fields=['status', 'summary_data', 'source_text_hash', 'updated_at'])
    else:
        summary_obj = StudySummary.all_objects.create(
            tenant=request.tenant,
            student=request.user,
            content=content,
            status='GENERATING',
            source_text_hash=current_hash,
        )

    summary_pk = str(summary_obj.pk)

    # SSE streaming response
    def sse_stream():
        result_data = None
        try:
            gen = generate_study_summary_sse(content, ai_config)
            for event in gen:
                yield event
                # Capture the parsed data from section events
                try:
                    payload = json.loads(event.replace("data: ", "").strip())
                    event_type = payload.get("type")
                    if event_type == "summary":
                        if result_data is None:
                            result_data = {}
                        result_data["summary"] = payload.get("content", "")
                    elif event_type == "flashcards":
                        if result_data is None:
                            result_data = {}
                        result_data["flashcards"] = payload.get("cards", [])
                    elif event_type == "key_terms":
                        if result_data is None:
                            result_data = {}
                        result_data["key_terms"] = payload.get("terms", [])
                    elif event_type == "quiz_prep":
                        if result_data is None:
                            result_data = {}
                        result_data["quiz_prep"] = payload.get("questions", [])
                    elif event_type == "mind_map":
                        if result_data is None:
                            result_data = {}
                        result_data["mind_map"] = {
                            "nodes": payload.get("nodes", []),
                            "edges": payload.get("edges", []),
                        }
                    elif event_type == "error":
                        # Mark as failed
                        StudySummary.all_objects.filter(pk=summary_pk).update(
                            status='FAILED',
                        )
                        return
                except (json.JSONDecodeError, ValueError):
                    pass
        except GeneratorExit:
            pass
        except Exception:
            logger.exception("Study summary stream error for content %s", content.id)
            yield f"data: {json.dumps({'type': 'error', 'error': 'An unexpected error occurred.'})}\n\n"
            StudySummary.all_objects.filter(pk=summary_pk).update(status='FAILED')
            return

        # Persist the generated result
        if result_data:
            try:
                StudySummary.all_objects.filter(pk=summary_pk).update(
                    status='READY',
                    summary_data=result_data,
                )
            except Exception:
                logger.exception("Failed to save study summary %s", summary_pk)
        else:
            StudySummary.all_objects.filter(pk=summary_pk).update(status='FAILED')

    response = StreamingHttpResponse(
        sse_stream(),
        content_type='text/event-stream',
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


# ─── List Summaries ──────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_study_summary_list(request):
    """
    List the current student's study summaries.

    Optional query param: ?course_id=<uuid> to filter by course.
    Returns summary metadata ordered by most recent.
    """
    qs = StudySummary.objects.filter(
        student=request.user,
    ).select_related(
        'content', 'content__module', 'content__module__course', 'generated_by',
    ).order_by('-created_at')

    course_id = request.query_params.get('course_id')
    if course_id:
        qs = qs.filter(content__module__course__id=course_id)

    results = []
    for summary in qs:
        content = summary.content
        course = content.module.course
        shared_by = None
        if summary.generated_by:
            shared_by = summary.generated_by.get_full_name()
        results.append({
            "id": str(summary.id),
            "content_id": str(content.id),
            "content_title": content.title,
            "content_type": content.content_type,
            "course_id": str(course.id),
            "course_title": course.title,
            "status": summary.status,
            "is_shared": summary.is_shared,
            "shared_by": shared_by,
            "created_at": summary.created_at.isoformat(),
            "updated_at": summary.updated_at.isoformat(),
        })

    return Response(results)


# ─── Summary Detail ──────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_study_summary_detail(request, summary_id):
    """
    Get the full study summary data for a specific summary.

    Only the owning student (or an admin) can access their summaries.
    """
    try:
        summary = StudySummary.objects.select_related(
            'content', 'content__module', 'content__module__course',
        ).get(pk=summary_id, student=request.user)
    except StudySummary.DoesNotExist:
        return Response(
            {"error": "Summary not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    content = summary.content
    course = content.module.course

    return Response({
        "id": str(summary.id),
        "content_id": str(content.id),
        "content_title": content.title,
        "content_type": content.content_type,
        "course_id": str(course.id),
        "course_title": course.title,
        "status": summary.status,
        "summary_data": summary.summary_data,
        "created_at": summary.created_at.isoformat(),
        "updated_at": summary.updated_at.isoformat(),
    })


# ─── Delete Summary ─────────────────────────────────────────────────────────

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_study_summary_delete(request, summary_id):
    """
    Delete a study summary. Only the owning student can delete their summaries.
    """
    try:
        summary = StudySummary.objects.get(pk=summary_id, student=request.user)
    except StudySummary.DoesNotExist:
        return Response(
            {"error": "Summary not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    summary.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
