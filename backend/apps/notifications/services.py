"""
Service functions to create notifications from various parts of the app.

Notifications are:
1. Persisted to the database
2. Sent in real-time via WebSocket (if user is connected)
3. Optionally sent via email (if send_email=True and email is enabled)
"""

import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import Notification
from .consumers import get_user_group_name

logger = logging.getLogger(__name__)

ACTIONABLE_TYPES = {'COURSE_ASSIGNED', 'ASSIGNMENT_DUE', 'REMINDER'}


def send_realtime_notification(user_id: str, notification_data: dict):
    """
    Send a notification to a user's WebSocket connection.

    Args:
        user_id: UUID of the user
        notification_data: Serialized notification data
    """
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            logger.debug("Channel layer not available, skipping real-time notification")
            return
        
        group_name = get_user_group_name(user_id)
        
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "notification.message",
                "notification": notification_data,
            }
        )
        logger.debug(f"Real-time notification sent to user {user_id}")
    except Exception as e:
        # Don't fail if WebSocket delivery fails - notification is already in DB
        logger.warning(f"Failed to send real-time notification: {e}")


def serialize_notification(notification: Notification) -> dict:
    """Serialize a notification for WebSocket delivery."""
    return {
        "id": str(notification.id),
        "type": notification.notification_type,
        "title": notification.title,
        "message": notification.message,
        "is_read": notification.is_read,
        "is_actionable": notification.is_actionable,
        "created_at": notification.created_at.isoformat(),
        "course_id": str(notification.course_id) if notification.course_id else None,
        "assignment_id": str(notification.assignment_id) if notification.assignment_id else None,
    }


def _queue_email(notification: Notification):
    """Queue an async email task for a notification."""
    try:
        from .tasks import send_notification_email
        send_notification_email.delay(str(notification.id))
    except Exception as exc:
        logger.warning("Failed to queue notification email id=%s err=%s", notification.id, exc)


def create_notification(
    tenant,
    teacher,
    notification_type: str,
    title: str,
    message: str,
    course=None,
    assignment=None,
    send_email=False,
):
    """
    Create a notification for a teacher.
    Also sends real-time notification via WebSocket.
    Optionally queues an email via Celery.
    """
    # Guard against cross-tenant notifications
    if teacher.tenant_id != tenant.id:
        import logging
        logging.getLogger(__name__).warning(
            "Blocked cross-tenant notification: teacher=%s tenant=%s target_tenant=%s",
            teacher.id, teacher.tenant_id, tenant.id,
        )
        return None
    notification = Notification.objects.create(
        tenant=tenant,
        teacher=teacher,
        notification_type=notification_type,
        title=title,
        message=message,
        course=course,
        assignment=assignment,
        is_actionable=notification_type in ACTIONABLE_TYPES,
    )
    
    # Send real-time notification
    send_realtime_notification(
        str(teacher.id),
        serialize_notification(notification)
    )

    if send_email:
        _queue_email(notification)
    
    return notification


def create_bulk_notifications(
    tenant,
    teachers,
    notification_type: str,
    title: str,
    message: str,
    course=None,
    assignment=None,
    send_email=False,
):
    """
    Create notifications for multiple teachers.
    Also sends real-time notifications via WebSocket.
    Optionally queues emails via Celery.
    """
    is_actionable = notification_type in ACTIONABLE_TYPES

    notifications = [
        Notification(
            tenant=tenant,
            teacher=teacher,
            notification_type=notification_type,
            title=title,
            message=message,
            course=course,
            assignment=assignment,
            is_actionable=is_actionable,
        )
        for teacher in teachers
    ]
    created = Notification.objects.bulk_create(notifications)
    
    # Send real-time notifications and optionally queue emails
    for notification in created:
        send_realtime_notification(
            str(notification.teacher_id),
            serialize_notification(notification)
        )
        if send_email:
            _queue_email(notification)
    
    return created


def notify_course_assigned(tenant, teachers, course):
    """
    Notify teachers that they've been assigned to a course.
    Sends in-app notification and email (if COURSE_ASSIGNMENT_EMAIL_ENABLED).
    """
    from django.conf import settings as django_settings
    send_email = getattr(django_settings, "COURSE_ASSIGNMENT_EMAIL_ENABLED", True)

    deadline_info = ""
    if getattr(course, "deadline", None):
        deadline_info = f" Deadline: {course.deadline.strftime('%B %d, %Y')}."

    message = (
        f"You have been assigned to the course '{course.title}'.{deadline_info} "
        f"Log in to your dashboard to get started!"
    )

    return create_bulk_notifications(
        tenant=tenant,
        teachers=teachers,
        notification_type='COURSE_ASSIGNED',
        title=f"New Course: {course.title}",
        message=message,
        course=course,
        send_email=send_email,
    )


def notify_reminder(tenant, teachers, subject, message, course=None, assignment=None):
    """
    Create reminder notifications for teachers.
    Sends both in-app notification and email.
    """
    notification_type = 'ASSIGNMENT_DUE' if assignment else 'REMINDER'
    return create_bulk_notifications(
        tenant=tenant,
        teachers=teachers,
        notification_type=notification_type,
        title=subject,
        message=message,
        course=course,
        assignment=assignment,
        send_email=True,
    )
