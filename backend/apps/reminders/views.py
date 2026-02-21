from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework import status

from utils.decorators import admin_only, tenant_required

from apps.courses.models import Course
from apps.progress.models import Assignment


from .models import ReminderCampaign
from .serializers import (
    ReminderPreviewRequestSerializer,
    ReminderSendRequestSerializer,
    ReminderCampaignSerializer,
)
from .services import (
    build_subject_and_message,
    dispatch_campaign,
    is_manual_reminder_locked,
    locked_reminder_message,
    recipients_for_assignment_due,
    recipients_for_course_deadline,
    tenant_teachers_qs,
    get_course_reminder_lead_days,
    is_automation_enabled,
)


class ReminderSendThrottle(ScopedRateThrottle):
    scope = 'reminder_send'


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def reminder_preview(request):
    serializer = ReminderPreviewRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    reminder_type = data["reminder_type"]
    if is_manual_reminder_locked(reminder_type):
        return Response(
            {
                "error": locked_reminder_message(reminder_type),
                "locked": True,
                "automation_enabled": is_automation_enabled(),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    course = None
    assignment = None

    if reminder_type == "COURSE_DEADLINE":
        # Note: Course uses TenantSoftDeleteManager - no need for tenant= filter
        course = get_object_or_404(Course, id=data.get("course_id"))
        recipients = recipients_for_course_deadline(course)
    elif reminder_type == "ASSIGNMENT_DUE":
        # Assignment doesn't use TenantManager, so course__tenant is needed for FK traversal
        assignment = get_object_or_404(Assignment, id=data.get("assignment_id"), course__tenant=request.tenant)
        recipients = recipients_for_assignment_due(assignment)
    else:
        recipients = tenant_teachers_qs(request.tenant)

    teacher_ids = data.get("teacher_ids")
    if teacher_ids:
        recipients = recipients.filter(id__in=teacher_ids)

    recipients = recipients.order_by("last_name", "first_name")
    preview = [
        {"id": t.id, "name": t.get_full_name() or t.email, "email": t.email}
        for t in recipients[:10]
    ]

    subj, msg = build_subject_and_message(
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
        if is_manual_reminder_locked(reminder_type):
            return Response(
                {
                    "error": locked_reminder_message(reminder_type),
                    "locked": True,
                    "automation_enabled": is_automation_enabled(),
                },
                status=status.HTTP_403_FORBIDDEN,
            )
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
            
            recipients = recipients_for_course_deadline(course)
            
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
            
            recipients = recipients_for_assignment_due(assignment)
        else:
            recipients = tenant_teachers_qs(request.tenant)

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
        subj, msg = build_subject_and_message(
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
                source="MANUAL",
                automation_key="",
            )
            logger.info(f"[REMINDER_SEND] Campaign created: {campaign.id}")
        except Exception as e:
            logger.exception("[REMINDER_SEND] Failed to create campaign")
            return Response({"error": f"Failed to create campaign: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        dispatch = dispatch_campaign(campaign, recipient_list)
        sent = dispatch.sent
        failed = dispatch.failed

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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def reminder_automation_status(request):
    today = timezone.localdate()
    lead_days = get_course_reminder_lead_days()
    horizon = max(lead_days) if lead_days else 0

    upcoming_courses_count = Course.objects.filter(
        tenant=request.tenant,
        is_active=True,
        is_published=True,
        deadline__isnull=False,
        deadline__gte=today,
        deadline__lte=today + timedelta(days=horizon),
    ).count()

    last_auto_campaign = (
        ReminderCampaign.objects.filter(
            tenant=request.tenant,
            source="AUTOMATED",
            reminder_type="COURSE_DEADLINE",
        )
        .order_by("-created_at")
        .first()
    )

    return Response(
        {
            "enabled": is_automation_enabled(),
            "locked_manual_types": sorted(["COURSE_DEADLINE"]),
            "lead_days": lead_days,
            "upcoming_courses_count": upcoming_courses_count,
            "last_run_at": last_auto_campaign.created_at if last_auto_campaign else None,
            "next_run_note": "Runs daily via scheduler.",
        },
        status=status.HTTP_200_OK,
    )
