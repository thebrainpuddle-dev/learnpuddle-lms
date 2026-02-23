import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


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
    if not getattr(settings, "REMINDER_EMAIL_ENABLED", False):
        return {"skipped": True, "reason": "email_disabled"}

    from .models import Notification

    try:
        notification = Notification.objects.select_related("teacher").get(id=notification_id)
    except Notification.DoesNotExist:
        logger.warning("send_notification_email: notification %s not found", notification_id)
        return {"skipped": True, "reason": "not_found"}

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
