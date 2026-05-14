"""
Signal handlers for integrations_calendar.

Hooks:
  - Assignment.post_save → enqueue sync_calendar_connection for any user
    whose CalendarConnection may be affected by a due_date change.
"""

from __future__ import annotations

import logging

from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _enqueue_syncs_for_users(user_pks):
    """
    For each user PK, enqueue sync_calendar_connection for their active connections.
    Imported lazily to avoid circular imports at module load time.
    """
    if not user_pks:
        return

    from apps.integrations_calendar.models import CalendarConnection
    from apps.integrations_calendar.tasks import sync_calendar_connection

    connections = CalendarConnection.objects.filter(
        user_id__in=user_pks,
        status=CalendarConnection.STATUS_ACTIVE,
    ).values_list("pk", flat=True)

    for conn_id in connections:
        try:
            sync_calendar_connection.delay(str(conn_id))
        except Exception:
            logger.exception(
                "signals: failed to enqueue sync for connection %s", conn_id
            )


def _course_assigned_user_pks(course):
    """
    Return active teacher/student IDs assigned to a course.

    The older calendar code referenced a removed Enrollment model. Current LMS
    assignment state lives directly on Course M2M fields and, for teacher
    cohorts, TeacherGroup membership.
    """
    from apps.users.models import User

    teacher_qs = User.objects.all_tenants().filter(
        tenant=course.tenant,
        role__in=["TEACHER", "HOD", "IB_COORDINATOR"],
        is_active=True,
        is_deleted=False,
    )
    if not course.assigned_to_all:
        group_ids = course.assigned_groups.values_list("id", flat=True)
        teacher_ids = course.assigned_teachers.values_list("id", flat=True)
        teacher_qs = teacher_qs.filter(
            Q(id__in=teacher_ids) | Q(teacher_groups__in=group_ids)
        ).distinct()

    student_qs = User.objects.all_tenants().filter(
        tenant=course.tenant,
        role="STUDENT",
        is_active=True,
        is_deleted=False,
    )
    if not course.assigned_to_all_students:
        student_ids = course.assigned_students.values_list("id", flat=True)
        student_qs = student_qs.filter(id__in=student_ids)

    return set(teacher_qs.values_list("id", flat=True)) | set(
        student_qs.values_list("id", flat=True)
    )


# ---------------------------------------------------------------------------
# Assignment post_save — trigger calendar sync when due_date changes
# ---------------------------------------------------------------------------


@receiver(post_save, sender="progress.Assignment")
def on_assignment_saved(sender, instance, created: bool, update_fields=None, **kwargs):
    """
    When an Assignment is saved with a due_date, push the updated event to
    calendar providers for all teachers enrolled in the course.
    """
    # Skip if due_date was not touched on an update (update_fields provided).
    if not created and update_fields is not None:
        if "due_date" not in update_fields:
            return

    if not instance.due_date:
        return

    # Collect user PKs assigned to this assignment's course.
    try:
        user_pks = _course_assigned_user_pks(instance.course)
    except Exception:
        logger.exception(
            "signals: failed to collect assigned users for assignment %s",
            instance.pk,
        )
        return

    _enqueue_syncs_for_users(user_pks)
