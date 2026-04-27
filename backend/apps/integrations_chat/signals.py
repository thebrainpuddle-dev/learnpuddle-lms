"""
Signal handlers for the integrations_chat app.

Hooks into ``apps.notifications.models.Notification`` post-save to dispatch
newly created notifications to configured chat integrations.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="notifications.Notification")
def on_notification_saved(sender, instance, created: bool, **kwargs):
    """
    Dispatch a newly created Notification to chat integrations.

    Only fires on *creation* (not updates like mark-as-read).
    Dispatched asynchronously via Celery so the HTTP response is unblocked.
    """
    if not created:
        return

    try:
        from .dispatcher import dispatch_notification
        dispatch_notification(instance)
    except Exception:
        logger.exception(
            "on_notification_saved: dispatch_notification failed for notification=%s",
            instance.pk,
        )
