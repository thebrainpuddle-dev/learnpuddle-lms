from django.db.models import Count, Q, Subquery, OuterRef, DecimalField, IntegerField, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from utils.decorators import tenant_required, teacher_or_admin
from utils.course_access import is_teacher_assigned_to_course as _teacher_assigned_to_course
from utils.responses import error_response
from apps.progress.models import TeacherProgress
from apps.progress.locking import compute_course_sequence_state
from apps.courses.video_models import VideoAsset, VideoTranscript
from .models import Course, Content
from .teacher_serializers import TeacherCourseListSerializer, TeacherCourseDetailSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_course_list(request):
    """
    List courses assigned to the current teacher (and published).
    Assignment rules:
      - assigned_to_all=True OR
      - assigned_teachers includes user OR
      - assigned_groups intersects user.teacher_groups
    """
    user = request.user

    # Note: Course uses TenantSoftDeleteManager which auto-filters by tenant via get_current_tenant().
    # Do NOT add tenant=request.tenant here - it causes empty results when request.tenant and
    # get_current_tenant() diverge (middleware timing issues).

    # Subquery: count of completed content for this teacher in each course
    completed_subquery = (
        TeacherProgress.objects.filter(
            teacher=user,
            course=OuterRef("pk"),
            content__isnull=False,
            status="COMPLETED",
        )
        .order_by()
        .values("course")
        .annotate(cnt=Count("id"))
        .values("cnt")
    )

    # Subquery: sum of progress_percentage for this teacher in each course
    progress_sum_subquery = (
        TeacherProgress.objects.filter(
            teacher=user,
            course=OuterRef("pk"),
            content__isnull=False,
        )
        .order_by()
        .values("course")
        .annotate(total=Sum("progress_percentage"))
        .values("total")
    )

    qs = (
        Course.objects.filter(is_active=True, is_published=True)
        .filter(
            Q(assigned_to_all=True)
            | Q(assigned_teachers=user)
            | Q(assigned_groups__in=user.teacher_groups.all())
        )
        .distinct()
        .annotate(
            # Precompute counts to eliminate N+1 queries in TeacherCourseListSerializer
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

    serializer = TeacherCourseListSerializer(qs, many=True, context={"request": request})
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_course_detail(request, course_id):
    """
    Retrieve a course (modules + contents) with teacher progress per content.
    """
    user = request.user

    # Note: Course uses TenantSoftDeleteManager - no need for tenant= filter
    course = get_object_or_404(
        Course,
        id=course_id,
        is_active=True,
        is_published=True,
    )

    # Ensure teacher is assigned (admins can view; teachers must be assigned)
    if not _teacher_assigned_to_course(user, course):
        return error_response("Not assigned to this course", status_code=status.HTTP_403_FORBIDDEN)

    progress_qs = TeacherProgress.objects.filter(
        teacher=user,
        course=course,
        content__isnull=False,
    ).select_related("content")
    progress_by_content_id = {str(p.content_id): p for p in progress_qs if p.content_id}

    # Video metadata (HLS/thumbnail/transcript flags) for video contents in this course
    video_assets_qs = VideoAsset.objects.filter(
        content__module__course=course,
        content__is_active=True,
        content__content_type="VIDEO",
    ).select_related("transcript")
    video_assets_by_content_id = {str(a.content_id): a for a in video_assets_qs}
    module_state_by_id, content_state_by_id = compute_course_sequence_state(course, user.id)

    serializer = TeacherCourseDetailSerializer(
        course,
        context={
            "request": request,
            "progress_by_content_id": progress_by_content_id,
            "video_assets_by_content_id": video_assets_by_content_id,
            "module_state_by_id": module_state_by_id,
            "content_state_by_id": content_state_by_id,
        },
    )
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_video_transcript(request, content_id):
    """
    Return transcript (segments + VTT URL) for a video content item.
    """
    content = get_object_or_404(
        Content,
        id=content_id,
        content_type="VIDEO",
        is_active=True,
        module__course__tenant=request.tenant,
        module__course__is_active=True,
        module__course__is_published=True,
    )
    course = content.module.course
    if not _teacher_assigned_to_course(request.user, course):
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

    return Response(
        {
            "content_id": str(content.id),
            "language": transcript.language,
            "full_text": transcript.full_text,
            "segments": transcript.segments,
            "vtt_url": vtt_url,
            "generated_at": transcript.generated_at,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def course_certificate(request, course_id):
    """
    Return certificate data for a completed course.
    Gated by feature_certificates flag.
    """
    from django.http import JsonResponse

    tenant = request.tenant
    if not getattr(tenant, "feature_certificates", False):
        return error_response("Certificates not available on your plan.", status_code=403, upgrade_required=True)

    # Note: Course uses TenantSoftDeleteManager - no need for tenant= filter
    course = get_object_or_404(
        Course,
        id=course_id,
        is_active=True,
        is_published=True,
    )
    user = request.user
    if not _teacher_assigned_to_course(user, course):
        return error_response("Not assigned to this course", status_code=403)

    # Check 100% completion (both queries must use the same is_active scope)
    from apps.courses.models import Content as ContentModel
    total = ContentModel.objects.filter(module__course=course, is_active=True).count()
    completed = TeacherProgress.objects.filter(
        teacher=user, course=course, content__isnull=False, content__is_active=True, status="COMPLETED"
    ).count()

    if total == 0 or completed < total:
        return error_response("Course not completed yet", status_code=400)

    # Find completion date (only from currently-active content)
    last_completion = TeacherProgress.objects.filter(
        teacher=user, course=course, content__isnull=False, content__is_active=True, status="COMPLETED"
    ).order_by("-completed_at").first()

    return Response({
        "teacher_name": user.get_full_name(),
        "course_title": course.title,
        "school_name": tenant.name,
        "completed_at": last_completion.completed_at.isoformat() if last_completion and last_completion.completed_at else None,
        "certificate_id": f"{user.id}-{course.id}",
    })
