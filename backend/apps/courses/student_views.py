# apps/courses/student_views.py
"""
Student-facing API views for courses and AI Studio features.

Core course endpoints:
    GET /api/v1/student/courses/
    GET /api/v1/student/courses/<course_id>/
    GET /api/v1/student/videos/<content_id>/transcript/

AI Studio endpoints:
    GET  /api/v1/student/ai-studio/scenarios/<scenario_id>/
    POST /api/v1/student/ai-studio/scenarios/<scenario_id>/attempt/

Study Notes endpoints (read-only):
    GET /api/v1/student/notes/
    GET /api/v1/student/notes/<notes_id>/
"""

import logging

from django.db.models import Count, Q, Subquery, OuterRef, DecimalField, IntegerField, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.courses.models import Course, Content
from apps.courses.video_models import VideoAsset, VideoTranscript
from apps.progress.models import TeacherProgress
from utils.course_access import is_student_assigned_to_course as _student_assigned_to_course
from utils.decorators import student_only, student_or_admin, tenant_required
from utils.responses import error_response
from .student_serializers import (
    StudentCourseListSerializer,
    StudentCourseDetailSerializer,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Helper: Student Assigned Courses Queryset
# ═══════════════════════════════════════════════════════════════════════════

def _student_assigned_courses_qs(request):
    """Get published, active courses assigned to the current student."""
    user = request.user
    return (
        Course.objects.filter(tenant=request.tenant, is_active=True, is_published=True)
        .filter(
            Q(assigned_to_all_students=True)
            | Q(assigned_students=user)
        )
        .distinct()
    )


# ═══════════════════════════════════════════════════════════════════════════
# Core Course Views
# ═══════════════════════════════════════════════════════════════════════════

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
def student_course_list(request):
    """List courses assigned to the current student with progress."""
    user = request.user

    completed_subquery = (
        TeacherProgress.objects.filter(
            teacher=user, course=OuterRef("pk"),
            content__isnull=False, status="COMPLETED",
        )
        .order_by()
        .values("course")
        .annotate(cnt=Count("id"))
        .values("cnt")
    )

    progress_sum_subquery = (
        TeacherProgress.objects.filter(
            teacher=user, course=OuterRef("pk"),
            content__isnull=False,
        )
        .order_by()
        .values("course")
        .annotate(total=Sum("progress_percentage"))
        .values("total")
    )

    qs = (
        _student_assigned_courses_qs(request)
        .annotate(
            _total_content_count=Count(
                "modules__contents",
                filter=Q(modules__contents__is_active=True),
                distinct=True,
            ),
            _completed_content_count=Coalesce(
                Subquery(completed_subquery, output_field=IntegerField()),
                Value(0, output_field=IntegerField()),
            ),
            _progress_sum=Coalesce(
                Subquery(progress_sum_subquery, output_field=DecimalField()),
                Value(0, output_field=DecimalField()),
            ),
        )
        .order_by("-created_at")
    )

    serializer = StudentCourseListSerializer(qs, many=True, context={"request": request})
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
def student_course_detail(request, course_id):
    """Get course detail with modules, contents, and student progress."""
    user = request.user

    course = get_object_or_404(Course, id=course_id, tenant=request.tenant, is_active=True, is_published=True)

    if not _student_assigned_to_course(user, course):
        return error_response("Not assigned to this course", status_code=status.HTTP_403_FORBIDDEN)

    progress_qs = TeacherProgress.objects.filter(
        teacher=user, course=course, content__isnull=False,
    ).select_related("content")
    progress_by_content_id = {str(p.content_id): p for p in progress_qs if p.content_id}

    video_assets_qs = VideoAsset.objects.filter(
        content__module__course=course,
        content__is_active=True,
        content__content_type="VIDEO",
    ).select_related("transcript")
    video_assets_by_content_id = {str(a.content_id): a for a in video_assets_qs}

    serializer = StudentCourseDetailSerializer(
        course,
        context={
            "request": request,
            "progress_by_content_id": progress_by_content_id,
            "video_assets_by_content_id": video_assets_by_content_id,
        },
    )
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
def student_video_transcript(request, content_id):
    """Return transcript for a video content item."""
    content = get_object_or_404(
        Content, id=content_id, content_type="VIDEO", is_active=True,
        module__course__tenant=request.tenant,
        module__course__is_published=True,
        module__course__is_active=True,
    )
    course = content.module.course
    if not _student_assigned_to_course(request.user, course):
        return error_response("Not assigned to this course", status_code=status.HTTP_403_FORBIDDEN)

    asset = getattr(content, "video_asset", None)
    if not asset:
        return error_response("Video not processed yet", status_code=status.HTTP_404_NOT_FOUND)
    transcript = getattr(asset, "transcript", None)
    if not transcript:
        return error_response("Transcript not available", status_code=status.HTTP_404_NOT_FOUND)

    vtt_url = transcript.vtt_url
    if vtt_url and not (vtt_url.startswith("http://") or vtt_url.startswith("https://")):
        vtt_url = request.build_absolute_uri(vtt_url)

    return Response({
        "content_id": str(content.id),
        "language": transcript.language,
        "full_text": transcript.full_text,
        "segments": transcript.segments,
        "vtt_url": vtt_url,
        "generated_at": transcript.generated_at,
    }, status=status.HTTP_200_OK)


