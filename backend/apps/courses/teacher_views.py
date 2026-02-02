from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from utils.decorators import tenant_required, teacher_or_admin
from apps.progress.models import TeacherProgress
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

    qs = (
        Course.objects.filter(tenant=request.tenant, is_active=True, is_published=True)
        .filter(
            Q(assigned_to_all=True)
            | Q(assigned_teachers=user)
            | Q(assigned_groups__in=user.teacher_groups.all())
        )
        .distinct()
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

    course = get_object_or_404(
        Course,
        id=course_id,
        tenant=request.tenant,
        is_active=True,
        is_published=True,
    )

    # Ensure teacher is assigned (admins can view; teachers must be assigned)
    if user.role not in ["SCHOOL_ADMIN", "SUPER_ADMIN"]:
        assigned = (
            course.assigned_to_all
            or course.assigned_teachers.filter(id=user.id).exists()
            or course.assigned_groups.filter(id__in=user.teacher_groups.values_list("id", flat=True)).exists()
        )
        if not assigned:
            return Response({"error": "Not assigned to this course"}, status=status.HTTP_403_FORBIDDEN)

    progress_qs = TeacherProgress.objects.filter(
        teacher=user,
        course=course,
        content__isnull=False,
    ).select_related("content")
    progress_by_content_id = {str(p.content_id): p for p in progress_qs if p.content_id}

    serializer = TeacherCourseDetailSerializer(
        course,
        context={"request": request, "progress_by_content_id": progress_by_content_id},
    )
    return Response(serializer.data, status=status.HTTP_200_OK)

