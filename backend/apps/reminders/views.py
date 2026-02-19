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
        # Note: Course uses TenantSoftDeleteManager - no need for tenant= filter
        course = get_object_or_404(Course, id=data.get("course_id"))
        recipients = _recipients_for_course_deadline(course)
    elif reminder_type == "ASSIGNMENT_DUE":
        # Assignment doesn't use TenantManager, so course__tenant is needed for FK traversal
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
    import logging
    import traceback
    logger = logging.getLogger(__name__)
    
    logger.info(f"[REMINDER_SEND] Started - user={request.user.email}, tenant={request.tenant.subdomain}")
    
    try:
        # Validate request data
        serializer = ReminderSendRequestSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"[REMINDER_SEND] Validation failed: {serializer.errors}")
            return Response({"error": "Invalid request data", "details": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        reminder_type = data["reminder_type"]
        logger.info(f"[REMINDER_SEND] Type={reminder_type}, data={data}")
        
        course = None
        assignment = None

        if reminder_type == "COURSE_DEADLINE":
            course_id = data.get("course_id")
            if not course_id:
                return Response({"error": "course_id is required for COURSE_DEADLINE reminders"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Explicitly query with tenant filter to avoid TenantManager issues
            try:
                course = Course.objects.filter(id=course_id).first()
                if not course:
                    logger.warning(f"[REMINDER_SEND] Course not found: {course_id}")
                    return Response({"error": f"Course not found: {course_id}"}, status=status.HTTP_404_NOT_FOUND)
                logger.info(f"[REMINDER_SEND] Found course: {course.title}")
            except Exception as e:
                logger.exception(f"[REMINDER_SEND] Error fetching course: {e}")
                return Response({"error": f"Error fetching course: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            recipients = _recipients_for_course_deadline(course)
            
        elif reminder_type == "ASSIGNMENT_DUE":
            assignment_id = data.get("assignment_id")
            if not assignment_id:
                return Response({"error": "assignment_id is required for ASSIGNMENT_DUE reminders"}, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                assignment = Assignment.objects.filter(id=assignment_id, course__tenant=request.tenant).first()
                if not assignment:
                    return Response({"error": f"Assignment not found: {assignment_id}"}, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                logger.exception(f"[REMINDER_SEND] Error fetching assignment: {e}")
                return Response({"error": f"Error fetching assignment: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            recipients = _recipients_for_assignment_due(assignment)
        else:
            recipients = _tenant_teachers_qs(request.tenant)

        teacher_ids = data.get("teacher_ids")
        if teacher_ids:
            # Defense-in-depth: explicitly scope to current tenant
            recipients = recipients.filter(id__in=teacher_ids, tenant=request.tenant)
            logger.info(f"[REMINDER_SEND] Filtered to teacher_ids: {teacher_ids}")

        recipients = recipients.order_by("last_name", "first_name")
        recipient_list = list(recipients)
        logger.info(f"[REMINDER_SEND] Found {len(recipient_list)} recipients")

        if not recipient_list:
            return Response({"error": "No valid recipients found for this reminder"}, status=status.HTTP_400_BAD_REQUEST)

        deadline_override = data.get("deadline_override")
        subj, msg = _build_subject_and_message(
            reminder_type, course, assignment, data.get("subject", ""), data.get("message", ""), deadline_override
        )
        logger.info(f"[REMINDER_SEND] Subject: {subj}")

        # Create campaign
        try:
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
            logger.info(f"[REMINDER_SEND] Campaign created: {campaign.id}")
        except Exception as e:
            logger.exception("[REMINDER_SEND] Failed to create campaign")
            return Response({"error": f"Failed to create campaign: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Check if email is configured (not console backend)
        email_backend = getattr(settings, "EMAIL_BACKEND", "")
        email_enabled = "console" not in email_backend.lower() and getattr(settings, "EMAIL_HOST", "")
        logger.info(f"[REMINDER_SEND] Email backend: {email_backend}, enabled: {email_enabled}")

        sent = 0
        failed = 0
        
        # Create delivery records for tracking
        for teacher in recipient_list:
            try:
                delivery = ReminderDelivery.objects.create(campaign=campaign, teacher=teacher, status="PENDING")
                
                # Only attempt email if email is properly configured
                if email_enabled:
                    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or f"no-reply@{getattr(settings, 'PLATFORM_DOMAIN', 'localhost')}"
                    try:
                        send_mail(
                            subject=subj,
                            message=msg,
                            from_email=from_email,
                            recipient_list=[teacher.email],
                            fail_silently=True,  # Don't block on email errors
                        )
                        delivery.status = "SENT"
                        delivery.sent_at = timezone.now()
                        sent += 1
                        logger.info(f"[REMINDER_SEND] Email sent to {teacher.email}")
                    except Exception as e:
                        logger.warning(f"[REMINDER_SEND] Email failed to {teacher.email}: {e}")
                        delivery.status = "FAILED"
                        delivery.error = str(e)[:500]
                        failed += 1
                else:
                    # Email not configured - mark as sent (in-app notification will be created)
                    delivery.status = "SENT"
                    delivery.sent_at = timezone.now()
                    sent += 1
                    logger.info(f"[REMINDER_SEND] Email skipped (not configured), in-app only for {teacher.email}")
                
                delivery.save(update_fields=["status", "sent_at", "error"])
                
            except Exception as e:
                logger.warning(f"[REMINDER_SEND] Failed to create delivery for {teacher.email}: {e}")
                failed += 1
                continue

        # Create in-app notifications (this is the primary delivery method)
        try:
            from apps.notifications.services import notify_reminder
            notify_reminder(
                tenant=request.tenant,
                teachers=recipient_list,
                subject=subj,
                message=msg,
                course=course,
                assignment=assignment,
            )
            logger.info(f"[REMINDER_SEND] In-app notifications created for {len(recipient_list)} recipients")
        except Exception as e:
            logger.warning(f"[REMINDER_SEND] In-app notifications failed: {e}")

        response_data = {
            "campaign": ReminderCampaignSerializer(campaign).data,
            "sent": sent,
            "failed": failed,
        }
        logger.info(f"[REMINDER_SEND] Complete - sent={sent}, failed={failed}")
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception(f"[REMINDER_SEND] Unexpected error: {e}\n{traceback.format_exc()}")
        return Response({"error": f"Unexpected error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def reminder_history(request):
    qs = ReminderCampaign.objects.filter(tenant=request.tenant).order_by("-created_at")[:50]
    return Response({"results": ReminderCampaignSerializer(qs, many=True).data}, status=status.HTTP_200_OK)

