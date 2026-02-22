from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date as date_cls
from typing import Iterable

from django.conf import settings
from django.core.mail import send_mail
from django.db import models
from django.utils import timezone

from apps.courses.models import Course
from apps.progress.models import Assignment, AssignmentSubmission
from apps.progress.completion_metrics import get_completed_teacher_ids_for_course
from apps.tenants.models import Tenant
from apps.users.models import User

from .models import ReminderCampaign, ReminderDelivery

logger = logging.getLogger(__name__)

LOCKED_MANUAL_REMINDER_TYPES = {"COURSE_DEADLINE"}
DEFAULT_COURSE_LEAD_DAYS = (7, 3, 1, 0)


@dataclass
class DispatchResult:
    sent: int
    failed: int


def is_manual_reminder_locked(reminder_type: str) -> bool:
    return reminder_type in LOCKED_MANUAL_REMINDER_TYPES


def locked_reminder_message(reminder_type: str) -> str:
    if reminder_type == "COURSE_DEADLINE":
        return (
            "Course-deadline reminders are automated and locked. "
            "Use CUSTOM reminders for manual sends."
        )
    return "This reminder type is locked and handled by automation."


def get_course_reminder_lead_days() -> list[int]:
    raw = getattr(settings, "AUTO_COURSE_REMINDER_LEAD_DAYS", "")
    if not raw:
        return list(DEFAULT_COURSE_LEAD_DAYS)

    parsed: list[int] = []
    for token in str(raw).split(","):
        token = token.strip()
        if not token:
            continue
        try:
            value = int(token)
        except ValueError:
            continue
        if 0 <= value <= 30:
            parsed.append(value)
    return sorted(set(parsed), reverse=True) or list(DEFAULT_COURSE_LEAD_DAYS)


def is_automation_enabled() -> bool:
    return bool(getattr(settings, "AUTO_COURSE_REMINDERS_ENABLED", True))


def tenant_teachers_qs(tenant):
    return User.objects.filter(
        tenant=tenant,
        role__in=["TEACHER", "HOD", "IB_COORDINATOR"],
        is_active=True,
    )


def course_assigned_teachers(course: Course):
    teachers = tenant_teachers_qs(course.tenant)
    if course.assigned_to_all:
        return teachers
    return teachers.filter(
        models.Q(teacher_groups__in=course.assigned_groups.all()) | models.Q(assigned_courses=course)
    ).distinct()


def recipients_for_course_deadline(course: Course):
    assigned = course_assigned_teachers(course)
    assigned_teacher_ids = list(assigned.values_list("id", flat=True))
    completed_teacher_ids = get_completed_teacher_ids_for_course(course.id, assigned_teacher_ids)
    return assigned.exclude(id__in=completed_teacher_ids)


def recipients_for_assignment_due(assignment: Assignment):
    assigned = course_assigned_teachers(assignment.course)
    submitted_teacher_ids = AssignmentSubmission.objects.filter(
        assignment=assignment, status__in=["SUBMITTED", "GRADED"]
    ).values_list("teacher_id", flat=True)
    return assigned.exclude(id__in=submitted_teacher_ids)


def build_subject_and_message(
    reminder_type: str,
    course: Course | None,
    assignment: Assignment | None,
    subject: str,
    message: str,
    deadline_override,
):
    subj = (subject or "").strip()
    msg = (message or "").strip()

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


def _teacher_allows_reminder_email(teacher: User) -> bool:
    prefs = teacher.notification_preferences or {}
    return bool(prefs.get("email_reminders", True))


def _send_campaign_emails(campaign: ReminderCampaign, recipients: Iterable[User]) -> DispatchResult:
    email_sending_enabled = getattr(settings, "REMINDER_EMAIL_ENABLED", False)
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or f"no-reply@{getattr(settings, 'PLATFORM_DOMAIN', 'localhost')}"

    sent = 0
    failed = 0
    for teacher in recipients:
        try:
            delivery = ReminderDelivery.objects.create(campaign=campaign, teacher=teacher, status="PENDING")
            should_send_email = email_sending_enabled and _teacher_allows_reminder_email(teacher)

            if should_send_email:
                try:
                    send_mail(
                        subject=campaign.subject,
                        message=campaign.message,
                        from_email=from_email,
                        recipient_list=[teacher.email],
                        fail_silently=True,
                    )
                except Exception as exc:
                    delivery.status = "FAILED"
                    delivery.error = str(exc)[:500]
                    delivery.sent_at = None
                    delivery.save(update_fields=["status", "error", "sent_at"])
                    failed += 1
                    continue

            delivery.status = "SENT"
            delivery.sent_at = timezone.now()
            delivery.error = ""
            delivery.save(update_fields=["status", "error", "sent_at"])
            sent += 1
        except Exception as exc:
            logger.warning("reminder delivery create failed campaign=%s teacher=%s err=%s", campaign.id, teacher.id, exc)
            failed += 1

    return DispatchResult(sent=sent, failed=failed)


def dispatch_campaign(campaign: ReminderCampaign, recipients: list[User]) -> DispatchResult:
    result = _send_campaign_emails(campaign, recipients)
    if not recipients:
        return result

    try:
        from apps.notifications.services import notify_reminder

        notify_reminder(
            tenant=campaign.tenant,
            teachers=recipients,
            subject=campaign.subject,
            message=campaign.message,
            course=campaign.course,
            assignment=campaign.assignment,
        )
    except Exception as exc:
        logger.warning("in-app reminder notification failed campaign=%s err=%s", campaign.id, exc)

    return result


def run_automated_course_deadline_reminders(run_date: date_cls | None = None) -> dict:
    if not is_automation_enabled():
        return {"enabled": False, "processed_courses": 0, "sent": 0, "failed": 0, "created_campaigns": 0}

    lead_days = get_course_reminder_lead_days()
    if not lead_days:
        return {"enabled": True, "processed_courses": 0, "sent": 0, "failed": 0, "created_campaigns": 0}

    today = run_date or timezone.localdate()
    sent = 0
    failed = 0
    created_campaigns = 0
    processed_courses = 0

    tenants = Tenant.objects.filter(is_active=True, feature_reminders=True)

    for tenant in tenants:
        courses = Course.objects.filter(
            tenant=tenant,
            is_active=True,
            is_published=True,
            deadline__isnull=False,
        )
        for course in courses:
            days_left = (course.deadline - today).days
            if days_left not in lead_days:
                continue

            processed_courses += 1
            automation_key = f"course-deadline:{course.id}:{days_left}:{today.isoformat()}"
            if ReminderCampaign.objects.filter(
                tenant=tenant,
                source="AUTOMATED",
                reminder_type="COURSE_DEADLINE",
                automation_key=automation_key,
            ).exists():
                continue

            recipients = list(recipients_for_course_deadline(course))
            if not recipients:
                continue

            subject, message = build_subject_and_message(
                "COURSE_DEADLINE",
                course,
                None,
                "",
                "",
                None,
            )
            campaign = ReminderCampaign.objects.create(
                tenant=tenant,
                created_by=None,
                reminder_type="COURSE_DEADLINE",
                course=course,
                assignment=None,
                subject=subject,
                message=message,
                deadline_override=None,
                source="AUTOMATED",
                automation_key=automation_key,
            )
            created_campaigns += 1
            result = dispatch_campaign(campaign, recipients)
            sent += result.sent
            failed += result.failed

    return {
        "enabled": True,
        "processed_courses": processed_courses,
        "created_campaigns": created_campaigns,
        "sent": sent,
        "failed": failed,
        "lead_days": lead_days,
        "run_date": str(today),
    }
