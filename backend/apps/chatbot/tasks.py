"""
Celery tasks for the chatbot app (TASK-059).

purge_old_chat_queries — hard-deletes ChatQuery rows older than 30 days.
Scheduled daily at 01:00 UTC via settings.CELERY_BEAT_SCHEDULE.
"""

from __future__ import annotations

import datetime
import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

RETENTION_DAYS = 30


@shared_task(name="chatbot.purge_old_chat_queries")
def purge_old_chat_queries() -> dict:
    """
    Delete ChatQuery rows older than RETENTION_DAYS days.

    Returns a dict with ``deleted_count`` and ``cutoff`` for observability.
    """
    from .models import ChatQuery

    cutoff = timezone.now() - datetime.timedelta(days=RETENTION_DAYS)
    qs = ChatQuery.all_objects.filter(created_at__lt=cutoff)
    deleted_count, _ = qs.delete()

    logger.info(
        "chatbot.purge_old_chat_queries: deleted=%d cutoff=%s",
        deleted_count,
        cutoff.isoformat(),
    )
    return {"deleted_count": deleted_count, "cutoff": cutoff.isoformat()}
