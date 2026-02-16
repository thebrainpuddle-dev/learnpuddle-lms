from django.db import models
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework import status

from utils.decorators import admin_only, tenant_required

from apps.users.models import User
from apps.courses.models import Course
from apps.progress.models import TeacherProgress, Assignment, AssignmentSubmission


from .models import ReminderCampaign, ReminderDelivery
from .serializers import (
    ReminderPreviewRequestSerializer,
    ReminderSendRequestSerializer,
    ReminderCampaignSerializer,
)


class ReminderSendThrottle(ScopedRateThrottle):
    scope = 'reminder_send'


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


def _recipients_for_course_deadline(course: Course):
    assigned = _course_assigned_teachers(course)
    completed_teacher_ids = TeacherProgress.objects.filter(
        course=course, content__isnull=True, status="COMPLETED"
    ).values_list("teacher_id", flat=True)
    return assigned.exclude(id__in=completed_teacher_ids)


def _recipients_for_assignment_due(assignment: Assignment):
    course = assignment.course
    assigned = _course_assigned_teachers(course)
    submitted_teacher_ids = AssignmentSubmission.objects.filter(
        assignment=assignment, status__in=["SUBMITTED", "GRADED"]
    ).values_list("teacher_id", flat=True)
    return assigned.exclude(id__in=submitted_teacher_ids)


def _build_subject_and_message(reminder_type: str, course: Course | None, assignment: Assignment | None, subject: str, message: str, deadline_override):
    subj = subject.strip()
    msg = message.strip()

    if reminder_type == "COURSE_DEADLINE" and course:
        if not subj:
            subj = f"Reminder: Complete '{course.title}'"
        deadline = deadline_override.date() if deadline_override else course.deadline
        if deadline:
            msg_prefix = f"Please complete the course '{course.title}' by {deadline}."
        else:
            msg_prefix = f"Please complete the course '{course.title}'."
        msg = msg_prefix + ("\n\n" + msg if msg else "")

    if reminder_type == "ASSIGNMENT_DUE" and assignment:
        if not subj:
            subj = f"Reminder: Submit assignment '{assignment.title}'"
        due = deadline_override if deadline_override else assignment.due_date
        if due:
            msg_prefix = f"Please submit the assignment '{assignment.title}' by {due}."
        else:
            msg_prefix = f"Please submit the assignment '{assignment.title}'."
        msg = msg_prefix + ("\n\n" + msg if msg else "")

    if reminder_type == "CUSTOM":
        if not subj:
            subj = "Reminder"
        if not msg:
            msg = "This is a reminder from your school."

    return subj, msg


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def reminder_preview(request):
    serializer = ReminderPreviewRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    reminder_type = data["reminder_type"]
    course = None
    assignment = None

    if reminder_type == "COURSE_DEADLINE":
        course = get_object_or_404(Course, id=data.get("course_id"), tenant=request.tenant)
        recipients = _recipients_for_course_deadline(course)
    elif reminder_type == "ASSIGNMENT_DUE":
        assignment = get_object_or_404(Assignment, id=data.get("assignment_id"), course__tenant=request.tenant)
        recipients = _recipients_for_assignment_due(assignment)
    else:
        recipients = _tenant_teachers_qs(request.tenant)

    teacher_ids = data.get("teacher_ids")
    if teacher_ids:
        recipients = recipients.filter(id__in=teacher_ids)

    recipients = recipients.order_by("last_name", "first_name")
    preview = [
        {"id": t.id, "name": t.get_full_name() or t.email, "email": t.email}
        for t in recipients[:10]
    ]

    subj, msg = _build_subject_and_message(
        reminder_type, course, assignment, data.get("subject", ""), data.get("message", ""), data.get("deadline_override")
    )

    return Response(
        {
            "recipient_count": recipients.count(),
            "recipients_preview": preview,
            "resolved_subject": subj,
            "resolved_message": msg,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([ReminderSendThrottle])
@admin_only
@tenant_required
def reminder_send(request):
    serializer = ReminderSendRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    reminder_type = data["reminder_type"]
    course = None
    assignment = None

    if reminder_type == "COURSE_DEADLINE":
        course = get_object_or_404(Course, id=data.get("course_id"), tenant=request.tenant)
        recipients = _recipients_for_course_deadline(course)
    elif reminder_type == "ASSIGNMENT_DUE":
        assignment = get_object_or_404(Assignment, id=data.get("assignment_id"), course__tenant=request.tenant)
        recipients = _recipients_for_assignment_due(assignment)
    else:
        recipients = _tenant_teachers_qs(request.tenant)

    teacher_ids = data.get("teacher_ids")
    if teacher_ids:
        # Defense-in-depth: explicitly scope to current tenant
        recipients = recipients.filter(id__in=teacher_ids, tenant=request.tenant)

    recipients = recipients.order_by("last_name", "first_name")

    deadline_override = data.get("deadline_override")
    subj, msg = _build_subject_and_message(
        reminder_type, course, assignment, data.get("subject", ""), data.get("message", ""), deadline_override
    )

    campaign = ReminderCampaign.objects.create(
        tenant=request.tenant,
        created_by=request.user,
        reminder_type=reminder_type,
        course=course,
        assignment=assignment,
        subject=subj,
        message=msg,
        deadline_override=deadline_override,
    )

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or f"no-reply@{getattr(settings, 'PLATFORM_DOMAIN', 'localhost')}"

    sent = 0
    failed = 0
    recipient_list = list(recipients)  # Capture for notifications
    
    for teacher in recipient_list:
        delivery = ReminderDelivery.objects.create(campaign=campaign, teacher=teacher, status="PENDING")
        try:
            send_mail(
                subject=subj,
                message=msg,
                from_email=from_email,
                recipient_list=[teacher.email],
                fail_silently=False,
            )
            delivery.status = "SENT"
            delivery.sent_at = timezone.now()
            delivery.save(update_fields=["status", "sent_at"])
            sent += 1
        except Exception as e:
            delivery.status = "FAILED"
            delivery.error = str(e)
            delivery.save(update_fields=["status", "error"])
            failed += 1

    # Create in-app notifications for all recipients
    from apps.notifications.services import notify_reminder
    notify_reminder(
        tenant=request.tenant,
        teachers=recipient_list,
        subject=subj,
        message=msg,
        course=course,
        assignment=assignment,
    )

    return Response(
        {
            "campaign": ReminderCampaignSerializer(campaign).data,
            "sent": sent,
            "failed": failed,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def reminder_history(request):
    qs = ReminderCampaign.objects.filter(tenant=request.tenant).order_by("-created_at")[:50]
    return Response({"results": ReminderCampaignSerializer(qs, many=True).data}, status=status.HTTP_200_OK)

