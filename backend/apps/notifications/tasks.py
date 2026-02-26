import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

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
    platform_domain = getattr(settings, "PLATFORM_DOMAIN", "localhost")
    subdomain = tenant.subdomain if tenant else ""
    login_url = f"https://{subdomain}.{platform_domain}/login" if subdomain else f"https://{platform_domain}/login"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or f"noreply@{platform_domain}"

    subject = f"Welcome to {school_name} on {platform_name}"

    password_line = ""
    if temp_password:
        password_line = f"Your temporary password: {temp_password}\nPlease change your password after your first login.\n\n"

    body = (
        f"Hi {teacher.first_name},\n\n"
        f"You've been added to {school_name} on {platform_name}.\n\n"
        f"Email: {teacher.email}\n"
        f"{password_line}"
        f"Log in here: {login_url}\n\n"
        f"What's next:\n"
        f"  1. Log in with the credentials above\n"
        f"  2. Update your profile\n"
        f"  3. Check your assigned courses\n\n"
        f"If you have questions, please contact your school administrator.\n\n"
        f"— The {platform_name} Team"
    )

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=[teacher.email],
            fail_silently=False,
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
    platform_domain = getattr(settings, "PLATFORM_DOMAIN", "localhost")
    subdomain = tenant.subdomain if tenant else ""
    base_url = f"https://{subdomain}.{platform_domain}" if subdomain else f"https://{platform_domain}"
    accept_url = f"{base_url}/accept-invitation/{invitation.token}"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or f"noreply@{platform_domain}"
    inviter_name = invitation.invited_by.get_full_name() if invitation.invited_by else "your administrator"

    subject = f"You're invited to join {school_name} on {platform_name}"
    body = (
        f"Hi {invitation.first_name},\n\n"
        f"{inviter_name} has invited you to join {school_name} on {platform_name}.\n\n"
        f"Click the link below to set your password and activate your account:\n\n"
        f"  {accept_url}\n\n"
        f"This invitation expires in 7 days.\n\n"
        f"If you didn't expect this invitation, you can safely ignore this email.\n\n"
        f"— The {platform_name} Team"
    )

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=[invitation.email],
            fail_silently=False,
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
    platform_domain = getattr(settings, "PLATFORM_DOMAIN", "localhost")
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or f"noreply@{platform_domain}"

    scheduled_str = booking.scheduled_at.strftime("%B %d, %Y at %I:%M %p") if booking.scheduled_at else "TBD"
    first_name = booking.name.split()[0] if booking.name else "there"

    subject = f"Thanks for booking a {platform_name} demo"
    body = (
        f"Hi {first_name},\n\n"
        f"Thank you for scheduling a demo with {platform_name}!\n\n"
        f"Your demo is scheduled for: {scheduled_str}\n\n"
        f"What to expect:\n"
        f"  - A walkthrough of the platform tailored to your needs\n"
        f"  - Q&A session about features, pricing, and setup\n"
        f"  - No commitment required\n\n"
        f"If you need to reschedule, simply reply to this email.\n\n"
        f"— The {platform_name} Team"
    )

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=[booking.email],
            fail_silently=False,
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
        notification = Notification.objects.select_related("teacher").get(id=notification_id)
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

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or f"noreply@{getattr(settings, 'PLATFORM_DOMAIN', 'localhost')}"
    platform_name = getattr(settings, "PLATFORM_NAME", "LearnPuddle")

    subject = f"[{platform_name}] {notification.title}"
    body = notification.message

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=[teacher.email],
            fail_silently=False,
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
