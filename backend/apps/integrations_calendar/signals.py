"""
Signal handlers for integrations_calendar.

Hooks:
  - Assignment.post_save → enqueue sync_calendar_connection for any user
    whose CalendarConnection may be affected by a due_date change.

Gap: Enrollment deadline signals are not fired explicitly — the sync_engine
already re-reads enrollment_end_date on every beat-triggered sync. If near-
realtime enrollment-deadline push is required, add a post_save handler on
apps.courses.models.Enrollment here (Slice B / TASK-054 follow-up).
"""

from __future__ import annotations

import logging

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

    # Collect user PKs enrolled in this assignment's course.
    try:
        from apps.courses.models import Enrollment

        user_pks = list(
            Enrollment.objects.filter(
                course_id=instance.course_id,
            ).values_list("user_id", flat=True)
        )
    except Exception:
        logger.exception(
            "signals: failed to collect enrolled users for assignment %s",
            instance.pk,
        )
        return

    _enqueue_syncs_for_users(user_pks)
