import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

from .email_utils import send_templated_email, build_login_url

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
    subdomain = tenant.subdomain if tenant else ""
    login_url = build_login_url(subdomain)

    subject = f"Welcome to {school_name} on {platform_name}"

    context = {
        "first_name": teacher.first_name or "there",
        "email": teacher.email,
        "temp_password": temp_password,
        "school_name": school_name,
        "login_url": login_url,
    }

    try:
        send_templated_email(
            to_email=teacher.email,
            subject=subject,
            template_name="teacher_welcome.html",
            context=context,
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
    subdomain = tenant.subdomain if tenant else ""
    accept_url = build_login_url(subdomain, f"/accept-invitation/{invitation.token}")
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
    }

    try:
        send_templated_email(
            to_email=invitation.email,
            subject=subject,
            template_name="teacher_invitation.html",
            context=context,
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
    elif not getattr(settings, "REMINDER_EMAIL_ENABLED", False):
        return {"skipped": True, "reason": "email_disabled"}

    teacher = notification.teacher
    if not teacher.email:
        return {"skipped": True, "reason": "no_email"}

    prefs = teacher.notification_preferences or {}
    if not prefs.get("email_reminders", True):
        return {"skipped": True, "reason": "user_preference"}

    platform_name = getattr(settings, "PLATFORM_NAME", "LearnPuddle")
    tenant = teacher.tenant
    school_name = tenant.name if tenant else "your organization"
    subdomain = tenant.subdomain if tenant else ""
    dashboard_url = build_login_url(subdomain, "/dashboard")

    subject = f"[{platform_name}] {notification.title}"

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
            template_name="notification.html",
            context=context,
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
