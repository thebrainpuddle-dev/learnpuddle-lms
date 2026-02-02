"""
Service functions to create notifications from various parts of the app.
"""
from .models import Notification


def create_notification(
    tenant,
    teacher,
    notification_type: str,
    title: str,
    message: str,
    course=None,
    assignment=None,
):
    """
    Create a notification for a teacher.
    """
    return Notification.objects.create(
        tenant=tenant,
        teacher=teacher,
        notification_type=notification_type,
        title=title,
        message=message,
        course=course,
        assignment=assignment,
    )


def create_bulk_notifications(
    tenant,
    teachers,
    notification_type: str,
    title: str,
    message: str,
    course=None,
    assignment=None,
):
    """
    Create notifications for multiple teachers.
    """
    notifications = [
        Notification(
            tenant=tenant,
            teacher=teacher,
            notification_type=notification_type,
            title=title,
            message=message,
            course=course,
            assignment=assignment,
        )
        for teacher in teachers
    ]
    return Notification.objects.bulk_create(notifications)


def notify_course_assigned(tenant, teachers, course):
    """
    Notify teachers that they've been assigned to a course.
    """
    return create_bulk_notifications(
        tenant=tenant,
        teachers=teachers,
        notification_type='COURSE_ASSIGNED',
        title=f"New Course: {course.title}",
        message=f"You have been assigned to the course '{course.title}'. Start learning now!",
        course=course,
    )


def notify_reminder(tenant, teachers, subject, message, course=None, assignment=None):
    """
    Create reminder notifications for teachers.
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
    )
