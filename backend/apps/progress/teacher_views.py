from datetime import datetime, timezone

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.courses.models import Course, Content
from apps.progress.models import TeacherProgress, Assignment, AssignmentSubmission
from utils.decorators import tenant_required, teacher_or_admin

from .teacher_serializers import (
    TeacherProgressSerializer,
    TeacherAssignmentListSerializer,
    TeacherAssignmentSubmissionSerializer,
)


def _utcnow():
    return datetime.now(timezone.utc)


def _teacher_assigned_to_course(user, course: Course) -> bool:
    if user.role in ["SCHOOL_ADMIN", "SUPER_ADMIN"]:
        return True
    if course.assigned_to_all:
        return True
    if course.assigned_teachers.filter(id=user.id).exists():
        return True
    if course.assigned_groups.filter(id__in=user.teacher_groups.values_list("id", flat=True)).exists():
        return True
    return False


def _teacher_assigned_courses_qs(request):
    user = request.user
    return (
        Course.objects.filter(tenant=request.tenant, is_active=True, is_published=True)
        .filter(
            Q(assigned_to_all=True)
            | Q(assigned_teachers=user)
            | Q(assigned_groups__in=user.teacher_groups.all())
        )
        .distinct()
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_dashboard(request):
    """
    Teacher dashboard data: stats, continue-learning, deadlines.
    """
    user = request.user
    courses = _teacher_assigned_courses_qs(request)
    total_courses = courses.count()

    # Overall progress: completed contents across assigned courses
    total_contents = Content.objects.filter(
        module__course__in=courses, is_active=True
    ).count()
    completed_contents = TeacherProgress.objects.filter(
        teacher=user,
        course__in=courses,
        content__isnull=False,
        status="COMPLETED",
    ).count()
    overall_progress = round((completed_contents / total_contents) * 100.0, 2) if total_contents else 0.0

    # Completed courses: course where completed contents == total contents (and total>0)
    completed_course_count = 0
    if total_courses:
        for course in courses:
            c_total = Content.objects.filter(module__course=course, is_active=True).count()
            if c_total == 0:
                continue
            c_completed = TeacherProgress.objects.filter(
                teacher=user,
                course=course,
                content__isnull=False,
                status="COMPLETED",
            ).count()
            if c_completed >= c_total:
                completed_course_count += 1

    # Assignments for assigned courses
    assignments = Assignment.objects.filter(course__in=courses, is_active=True)
    submissions = AssignmentSubmission.objects.filter(teacher=user, assignment__in=assignments)
    submitted_or_graded_ids = submissions.filter(status__in=["SUBMITTED", "GRADED"]).values_list("assignment_id", flat=True)
    pending_assignments = assignments.exclude(id__in=submitted_or_graded_ids).count()

    # Continue learning: most recently accessed in-progress content
    last_progress = (
        TeacherProgress.objects.filter(
            teacher=user,
            course__in=courses,
            content__isnull=False,
            status__in=["IN_PROGRESS", "NOT_STARTED"],
        )
        .select_related("course", "content")
        .order_by("-last_accessed")
        .first()
    )
    continue_learning = None
    if last_progress and last_progress.course and last_progress.content:
        continue_learning = {
            "course_id": str(last_progress.course_id),
            "course_title": last_progress.course.title,
            "content_id": str(last_progress.content_id),
            "content_title": last_progress.content.title,
            "progress_percentage": float(last_progress.progress_percentage),
        }

    # Upcoming deadlines: course deadline (date) + assignment due_date (datetime)
    now = _utcnow()
    deadline_items = []
    for course in courses.exclude(deadline__isnull=True).order_by("deadline")[:10]:
        days_left = (datetime.combine(course.deadline, datetime.min.time(), tzinfo=timezone.utc) - now).days
        deadline_items.append(
            {
                "type": "course",
                "id": str(course.id),
                "title": course.title,
                "days_left": days_left,
            }
        )
    for a in assignments.exclude(due_date__isnull=True).order_by("due_date")[:10]:
        days_left = (a.due_date - now).days
        deadline_items.append(
            {"type": "assignment", "id": str(a.id), "title": a.title, "days_left": days_left}
        )
    deadline_items = sorted(deadline_items, key=lambda x: x["days_left"])[:10]

    return Response(
        {
            "stats": {
                "overall_progress": overall_progress,
                "total_courses": total_courses,
                "completed_courses": completed_course_count,
                "pending_assignments": pending_assignments,
            },
            "continue_learning": continue_learning,
            "deadlines": deadline_items,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def progress_start(request, content_id):
    content = get_object_or_404(
        Content,
        id=content_id,
        is_active=True,
        module__course__tenant=request.tenant,
        module__course__is_published=True,
        module__course__is_active=True,
    )
    course = content.module.course
    if not _teacher_assigned_to_course(request.user, course):
        return Response({"error": "Not assigned to this course"}, status=status.HTTP_403_FORBIDDEN)

    obj, _created = TeacherProgress.objects.get_or_create(
        teacher=request.user,
        course=course,
        content=content,
        defaults={"status": "IN_PROGRESS", "started_at": _utcnow()},
    )
    if obj.status == "NOT_STARTED":
        obj.status = "IN_PROGRESS"
    if not obj.started_at:
        obj.started_at = _utcnow()
    obj.save()
    return Response(TeacherProgressSerializer(obj).data, status=status.HTTP_200_OK)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def progress_update(request, content_id):
    content = get_object_or_404(
        Content,
        id=content_id,
        is_active=True,
        module__course__tenant=request.tenant,
        module__course__is_published=True,
        module__course__is_active=True,
    )
    course = content.module.course
    if not _teacher_assigned_to_course(request.user, course):
        return Response({"error": "Not assigned to this course"}, status=status.HTTP_403_FORBIDDEN)

    obj, _created = TeacherProgress.objects.get_or_create(
        teacher=request.user,
        course=course,
        content=content,
        defaults={"status": "IN_PROGRESS", "started_at": _utcnow()},
    )

    video_seconds = request.data.get("video_progress_seconds")
    progress_pct = request.data.get("progress_percentage")

    if video_seconds is not None:
        obj.video_progress_seconds = int(video_seconds)
    if progress_pct is not None:
        obj.progress_percentage = float(progress_pct)

    if obj.status == "NOT_STARTED":
        obj.status = "IN_PROGRESS"
    if not obj.started_at:
        obj.started_at = _utcnow()

    obj.save()
    return Response(TeacherProgressSerializer(obj).data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def progress_complete(request, content_id):
    content = get_object_or_404(
        Content,
        id=content_id,
        is_active=True,
        module__course__tenant=request.tenant,
        module__course__is_published=True,
        module__course__is_active=True,
    )
    course = content.module.course
    if not _teacher_assigned_to_course(request.user, course):
        return Response({"error": "Not assigned to this course"}, status=status.HTTP_403_FORBIDDEN)

    obj, _created = TeacherProgress.objects.get_or_create(
        teacher=request.user,
        course=course,
        content=content,
        defaults={"status": "COMPLETED", "started_at": _utcnow(), "completed_at": _utcnow(), "progress_percentage": 100},
    )
    obj.status = "COMPLETED"
    obj.progress_percentage = 100
    if not obj.started_at:
        obj.started_at = _utcnow()
    obj.completed_at = _utcnow()
    obj.save()
    return Response(TeacherProgressSerializer(obj).data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def assignment_list(request):
    """
    List assignments for the teacher's assigned courses.
    Supports ?status=PENDING|SUBMITTED|GRADED.
    """
    status_filter = request.GET.get("status")
    courses = _teacher_assigned_courses_qs(request)
    qs = Assignment.objects.filter(course__in=courses, is_active=True).select_related("course")

    # Prefetch teacher submissions
    submissions = AssignmentSubmission.objects.filter(teacher=request.user, assignment__in=qs).select_related("assignment")
    submissions_map = {s.assignment_id: s for s in submissions}

    # Apply filter by derived status
    if status_filter in {"PENDING", "SUBMITTED", "GRADED"}:
        filtered = []
        for a in qs:
            sub = submissions_map.get(a.id)
            derived = sub.status if sub else "PENDING"
            if derived == status_filter:
                setattr(a, "_submission_for_teacher", sub)
                filtered.append(a)
        serializer = TeacherAssignmentListSerializer(filtered, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    # Attach submission for serializer
    items = []
    for a in qs:
        setattr(a, "_submission_for_teacher", submissions_map.get(a.id))
        items.append(a)
    serializer = TeacherAssignmentListSerializer(items, many=True, context={"request": request})
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def assignment_submit(request, assignment_id):
    """
    Submit/update teacher assignment submission.
    """
    assignment = get_object_or_404(
        Assignment,
        id=assignment_id,
        is_active=True,
        course__tenant=request.tenant,
        course__is_published=True,
        course__is_active=True,
    )
    if not _teacher_assigned_to_course(request.user, assignment.course):
        return Response({"error": "Not assigned to this course"}, status=status.HTTP_403_FORBIDDEN)

    submission_text = request.data.get("submission_text", "")
    file_url = request.data.get("file_url", "")

    obj, _created = AssignmentSubmission.objects.get_or_create(
        assignment=assignment,
        teacher=request.user,
        defaults={"submission_text": submission_text, "file_url": file_url, "status": "SUBMITTED"},
    )
    obj.submission_text = submission_text
    obj.file_url = file_url
    obj.status = "SUBMITTED"
    obj.save()

    return Response(TeacherAssignmentSubmissionSerializer(obj).data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def assignment_submission_detail(request, assignment_id):
    assignment = get_object_or_404(
        Assignment,
        id=assignment_id,
        is_active=True,
        course__tenant=request.tenant,
    )
    if not _teacher_assigned_to_course(request.user, assignment.course):
        return Response({"error": "Not assigned to this course"}, status=status.HTTP_403_FORBIDDEN)

    submission = get_object_or_404(AssignmentSubmission, assignment=assignment, teacher=request.user)
    return Response(TeacherAssignmentSubmissionSerializer(submission).data, status=status.HTTP_200_OK)

