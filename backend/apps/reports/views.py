from django.db import models
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from utils.decorators import admin_only, tenant_required

from apps.users.models import User
from apps.courses.models import Course
from apps.progress.models import TeacherProgress, Assignment, AssignmentSubmission


def _tenant_teachers_qs(tenant):
    return User.objects.filter(
        tenant=tenant,
        role__in=["TEACHER", "HOD", "IB_COORDINATOR"],
        is_active=True,
    )


def _course_assigned_teachers(course: Course):
    teachers = _tenant_teachers_qs(course.tenant)
    if course.assigned_to_all:
        return teachers
    return teachers.filter(
        models.Q(teacher_groups__in=course.assigned_groups.all()) | models.Q(assigned_courses=course)
    ).distinct()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def course_progress_report(request):
    """
    Course completion report.
    Query params:
      - course_id (required)
      - status: COMPLETED|IN_PROGRESS|NOT_STARTED (optional)
      - search: name/email (optional)
    """
    course_id = request.GET.get("course_id")
    if not course_id:
        return Response({"error": "course_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    course = get_object_or_404(Course, id=course_id, tenant=request.tenant)
    teachers = _course_assigned_teachers(course)

    search = request.GET.get("search")
    if search:
        teachers = teachers.filter(
            models.Q(email__icontains=search)
            | models.Q(first_name__icontains=search)
            | models.Q(last_name__icontains=search)
            | models.Q(employee_id__icontains=search)
            | models.Q(department__icontains=search)
        )

    # Use course-level progress marker (content is NULL) when present
    progress_map = {
        p.teacher_id: p
        for p in TeacherProgress.objects.filter(course=course, content__isnull=True, teacher__in=teachers)
    }

    rows = []
    for t in teachers.order_by("last_name", "first_name"):
        p = progress_map.get(t.id)
        status_val = p.status if p else "NOT_STARTED"
        completed_at = p.completed_at if p else None
        rows.append(
            {
                "teacher_id": t.id,
                "teacher_name": t.get_full_name() or t.email,
                "teacher_email": t.email,
                "course_id": course.id,
                "course_title": course.title,
                "deadline": course.deadline,
                "status": status_val,
                "completed_at": completed_at,
            }
        )

    status_filter = request.GET.get("status")
    if status_filter:
        rows = [r for r in rows if r["status"] == status_filter]

    return Response({"results": rows}, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def assignment_status_report(request):
    """
    Assignment submission report.
    Query params:
      - assignment_id (required)
      - status: PENDING|SUBMITTED|GRADED (optional)
      - search: name/email (optional)
    """
    assignment_id = request.GET.get("assignment_id")
    if not assignment_id:
        return Response({"error": "assignment_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    assignment = get_object_or_404(Assignment, id=assignment_id, course__tenant=request.tenant)
    course = assignment.course
    teachers = _course_assigned_teachers(course)

    search = request.GET.get("search")
    if search:
        teachers = teachers.filter(
            models.Q(email__icontains=search)
            | models.Q(first_name__icontains=search)
            | models.Q(last_name__icontains=search)
            | models.Q(employee_id__icontains=search)
            | models.Q(department__icontains=search)
        )

    submissions = AssignmentSubmission.objects.filter(assignment=assignment, teacher__in=teachers)
    submission_map = {s.teacher_id: s for s in submissions}

    rows = []
    for t in teachers.order_by("last_name", "first_name"):
        s = submission_map.get(t.id)
        status_val = s.status if s else "PENDING"
        submitted_at = s.submitted_at if s else None
        rows.append(
            {
                "teacher_id": t.id,
                "teacher_name": t.get_full_name() or t.email,
                "teacher_email": t.email,
                "assignment_id": assignment.id,
                "assignment_title": assignment.title,
                "due_date": assignment.due_date,
                "status": status_val,
                "submitted_at": submitted_at,
            }
        )

    status_filter = request.GET.get("status")
    if status_filter:
        rows = [r for r in rows if r["status"] == status_filter]

    return Response({"results": rows}, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def list_courses_for_reports(request):
    qs = Course.objects.filter(tenant=request.tenant, is_active=True).order_by("-created_at")
    return Response(
        [{"id": c.id, "title": c.title, "deadline": c.deadline} for c in qs[:200]],
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def list_assignments_for_reports(request):
    course_id = request.GET.get("course_id")
    qs = Assignment.objects.filter(course__tenant=request.tenant, is_active=True)
    if course_id:
        qs = qs.filter(course_id=course_id)
    qs = qs.order_by("-created_at")
    return Response(
        [{"id": a.id, "title": a.title, "course_id": a.course_id, "due_date": a.due_date} for a in qs[:200]],
        status=status.HTTP_200_OK,
    )

