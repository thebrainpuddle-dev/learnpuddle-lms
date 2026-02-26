import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

from .email_utils import (
    send_templated_email,
    build_tenant_url,
    build_school_sender_email,
    build_tenant_reply_to,
    build_bucket_headers,
)

logger = logging.getLogger(__name__)


@shared_task(
    name="notifications.send_teacher_welcome_email",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def send_teacher_welcome_email(self, user_id: str, temp_password: str | None = None):
    """
    Send a welcome email to a newly created teacher with login instructions.
    Called after bulk import or single teacher creation.
    """
    if not getattr(settings, "SEND_ONBOARDING_EMAIL", True):
        return {"skipped": True, "reason": "onboarding_email_disabled"}

    from apps.users.models import User

    try:
        teacher = User.objects.select_related("tenant").get(id=user_id)
    except User.DoesNotExist:
        logger.warning("send_teacher_welcome_email: user %s not found", user_id)
        return {"skipped": True, "reason": "not_found"}

    if not teacher.email:
        return {"skipped": True, "reason": "no_email"}

    tenant = teacher.tenant
    school_name = tenant.name if tenant else "your organization"
    platform_name = getattr(settings, "PLATFORM_NAME", "LearnPuddle")
    login_url = build_tenant_url(tenant=tenant, path="/login")
    forgot_password_url = build_tenant_url(tenant=tenant, path="/forgot-password")

    subject = f"Welcome to {school_name} on {platform_name}"

    context = {
        "first_name": teacher.first_name or "there",
        "email": teacher.email,
        "temp_password": temp_password,
        "school_name": school_name,
        "login_url": login_url,
        "forgot_password_url": forgot_password_url,
    }

    try:
        send_templated_email(
            to_email=teacher.email,
            subject=subject,
            template_name="teacher_welcome.html",
            context=context,
            headers=build_bucket_headers(
                tenant=tenant,
                bucket="onboarding",
                template_name="teacher_welcome.html",
                event="teacher_welcome",
            ),
        )
        logger.info("teacher welcome email sent to=%s user_id=%s", teacher.email, user_id)
        return {"sent": True, "to": teacher.email}
    except Exception as exc:
        logger.error("teacher welcome email failed to=%s user_id=%s err=%s", teacher.email, user_id, exc)
        raise self.retry(exc=exc)


@shared_task(
    name="notifications.send_teacher_invitation_email",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def send_teacher_invitation_email(self, invitation_id: str):
    """
    Send an invitation email to a teacher with a unique token-based link
    so they can set their own password and join the platform.
    """
    from apps.users.models import TeacherInvitation

    try:
        invitation = TeacherInvitation.objects.select_related("tenant", "invited_by").get(id=invitation_id)
    except TeacherInvitation.DoesNotExist:
        logger.warning("send_teacher_invitation_email: invitation %s not found", invitation_id)
        return {"skipped": True, "reason": "not_found"}

    tenant = invitation.tenant
    school_name = tenant.name if tenant else "your organization"
    platform_name = getattr(settings, "PLATFORM_NAME", "LearnPuddle")
    accept_url = build_tenant_url(tenant=tenant, path=f"/accept-invitation/{invitation.token}")
    forgot_password_url = build_tenant_url(tenant=tenant, path="/forgot-password")
    inviter_name = invitation.invited_by.get_full_name() if invitation.invited_by else "your administrator"
    expires_at = invitation.expires_at.strftime("%B %d, %Y") if invitation.expires_at else "7 days from now"

    subject = f"You're invited to join {school_name} on {platform_name}"

    context = {
        "first_name": invitation.first_name or "there",
        "email": invitation.email,
        "school_name": school_name,
        "inviter_name": inviter_name,
        "accept_url": accept_url,
        "expires_at": expires_at,
        "forgot_password_url": forgot_password_url,
    }

    try:
        send_templated_email(
            to_email=invitation.email,
            subject=subject,
            template_name="teacher_invitation.html",
            context=context,
            headers=build_bucket_headers(
                tenant=tenant,
                bucket="onboarding",
                template_name="teacher_invitation.html",
                event="teacher_invitation",
            ),
        )
        logger.info("teacher invitation email sent to=%s invitation_id=%s", invitation.email, invitation_id)
        return {"sent": True, "to": invitation.email}
    except Exception as exc:
        logger.error("teacher invitation email failed to=%s invitation_id=%s err=%s", invitation.email, invitation_id, exc)
        raise self.retry(exc=exc)


@shared_task(
    name="notifications.send_demo_followup_email",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def send_demo_followup_email(self, booking_id: str):
    """
    Send a follow-up/confirmation email after a demo booking is created.
    """
    from apps.tenants.models import DemoBooking

    try:
        booking = DemoBooking.objects.get(id=booking_id)
    except DemoBooking.DoesNotExist:
        logger.warning("send_demo_followup_email: booking %s not found", booking_id)
        return {"skipped": True, "reason": "not_found"}

    platform_name = getattr(settings, "PLATFORM_NAME", "LearnPuddle")
    scheduled_str = booking.scheduled_at.strftime("%B %d, %Y at %I:%M %p") if booking.scheduled_at else "To be confirmed"
    first_name = booking.name.split()[0] if booking.name else "there"

    subject = f"Thanks for booking a {platform_name} demo"

    context = {
        "first_name": first_name,
        "scheduled_at": scheduled_str,
        "company": booking.company or "",
    }

    try:
        send_templated_email(
            to_email=booking.email,
            subject=subject,
            template_name="demo_confirmation.html",
            context=context,
            headers=build_bucket_headers(
                tenant=None,
                bucket="onboarding",
                template_name="demo_confirmation.html",
                event="demo_confirmation",
            ),
        )
        from django.utils import timezone
        booking.followup_sent_at = timezone.now()
        booking.save(update_fields=["followup_sent_at"])
        logger.info("demo followup email sent to=%s booking_id=%s", booking.email, booking_id)
        return {"sent": True, "to": booking.email}
    except Exception as exc:
        logger.error("demo followup email failed to=%s booking_id=%s err=%s", booking.email, booking_id, exc)
        raise self.retry(exc=exc)


@shared_task(
    name="notifications.send_arbitrary_email",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def send_arbitrary_email(self, to_email: str, subject: str, body: str, tenant_id: str = ""):
    """
    Send a plain-text email via the configured SMTP backend.
    Used by the Super Admin custom-email feature so the HTTP request
    returns immediately instead of blocking on SMTP.
    """
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or f"noreply@{getattr(settings, 'PLATFORM_DOMAIN', 'localhost')}"
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=[to_email],
            fail_silently=False,
        )
        logger.info("arbitrary email sent to=%s subject=%s tenant=%s", to_email, subject, tenant_id)
        return {"sent": True, "to": to_email}
    except Exception as exc:
        logger.error("arbitrary email failed to=%s subject=%s tenant=%s err=%s", to_email, subject, tenant_id, exc)
        raise self.retry(exc=exc)


@shared_task(
    name="notifications.send_notification_email",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def send_notification_email(self, notification_id: str):
    """
    Send an email for a single Notification record.
    Checks global email toggle and per-user preference before sending.
    """
    from .models import Notification

    try:
        notification = Notification.objects.select_related("teacher", "teacher__tenant").get(id=notification_id)
    except Notification.DoesNotExist:
        logger.warning("send_notification_email: notification %s not found", notification_id)
        return {"skipped": True, "reason": "not_found"}

    if notification.notification_type == "COURSE_ASSIGNED":
        if not getattr(settings, "COURSE_ASSIGNMENT_EMAIL_ENABLED", True):
            return {"skipped": True, "reason": "course_assignment_email_disabled"}
    elif notification.notification_type == "REMINDER":
        if not getattr(settings, "REMINDER_EMAIL_ENABLED", False):
            return {"skipped": True, "reason": "email_disabled"}

    teacher = notification.teacher
    if not teacher.email:
        return {"skipped": True, "reason": "no_email"}

    prefs = teacher.notification_preferences or {}
    pref_key_map = {
        "COURSE_ASSIGNED": "email_courses",
        "ASSIGNMENT_DUE": "email_assignments",
        "REMINDER": "email_reminders",
        "ANNOUNCEMENT": "email_announcements",
    }
    pref_key = pref_key_map.get(notification.notification_type, "email_reminders")
    if not prefs.get(pref_key, True):
        return {"skipped": True, "reason": "user_preference"}

    platform_name = getattr(settings, "PLATFORM_NAME", "LearnPuddle")
    tenant = teacher.tenant
    school_name = tenant.name if tenant else "your organization"
    dashboard_url = build_tenant_url(tenant=tenant, path="/dashboard")

    subject = f"[{platform_name}] {notification.title}"
    template_name = "notification.html"
    bucket = "security"
    event = notification.notification_type.lower()

    if notification.notification_type == "COURSE_ASSIGNED":
        template_name = "course_assigned.html"
        bucket = "course_assignment"
        course = notification.course
        course_url = dashboard_url
        if course:
            course_url = build_tenant_url(tenant=tenant, path=f"/teacher/courses/{course.id}")
        context = {
            "first_name": teacher.first_name or "there",
            "school_name": school_name,
            "course_title": getattr(course, "title", notification.title),
            "course_description": getattr(course, "description", ""),
            "deadline": course.deadline.strftime("%B %d, %Y") if course and getattr(course, "deadline", None) else "",
            "content_count": course.modules.count() if course else 0,
            "course_url": course_url,
        }
    else:
        if notification.notification_type == "ASSIGNMENT_DUE":
            bucket = "assignment_due"
        elif notification.notification_type == "REMINDER":
            bucket = "reminder_manual"
        elif notification.notification_type == "ANNOUNCEMENT":
            bucket = "security"
        context = {
            "first_name": teacher.first_name or "there",
            "notification_title": notification.title,
            "notification_message": notification.message,
            "school_name": school_name,
            "action_url": dashboard_url,
            "action_text": "Go to Dashboard",
        }

    try:
        send_templated_email(
            to_email=teacher.email,
            subject=subject,
            template_name=template_name,
            context=context,
            from_email=build_school_sender_email(tenant),
            reply_to=build_tenant_reply_to(tenant),
            headers=build_bucket_headers(
                tenant=tenant,
                bucket=bucket,
                template_name=template_name,
                event=event,
            ),
        )
        logger.info(
            "notification email sent id=%s to=%s type=%s",
            notification_id, teacher.email, notification.notification_type,
        )
        return {"sent": True, "to": teacher.email}
    except Exception as exc:
        logger.error(
            "notification email failed id=%s to=%s err=%s",
            notification_id, teacher.email, exc,
        )
        raise self.retry(exc=exc)
