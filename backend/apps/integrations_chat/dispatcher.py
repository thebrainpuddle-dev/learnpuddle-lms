"""
Notification dispatcher for chat integrations.

``dispatch_notification(notification_obj)`` is the single entry-point called
from the Notification post-save signal.  It:

1. Finds all active ChatIntegration rows for the notification's tenant.
2. Filters by matching ChatRoutingRule (notification_type + optional role_filter).
3. Creates ChatDelivery rows (idempotent — skips if already exists).
4. Enqueues ``deliver_chat_message`` Celery tasks.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.notifications.models import Notification

logger = logging.getLogger(__name__)


def dispatch_notification(notification: "Notification") -> list[uuid.UUID]:
    """
    Dispatch *notification* to all matching chat integrations.

    Returns a list of ChatDelivery IDs that were enqueued.
    Idempotent: calling twice with the same notification will not create
    duplicate delivery rows (enforced by DB unique constraint on
    ``(integration_id, notification_id)``).
    """
    from .models import ChatDelivery, ChatIntegration, ChatRoutingRule

    tenant = getattr(notification, "tenant", None)
    if tenant is None:
        logger.warning("dispatch_notification: notification %s has no tenant", notification.pk)
        return []

    notification_type = getattr(notification, "notification_type", None)
    if not notification_type:
        return []

    # Recipient role (for role_filter matching).
    recipient_role = None
    teacher = getattr(notification, "teacher", None)
    if teacher is not None:
        recipient_role = getattr(teacher, "role", None)

    # Find all active integrations for this tenant.
    # Use all_tenants() to bypass TenantManager's context-based filter —
    # tenant is explicitly specified in the filter(), so isolation is preserved.
    integrations = ChatIntegration.objects.all_tenants().filter(
        tenant=tenant, is_active=True
    )

    delivery_ids: list[uuid.UUID] = []

    for integration in integrations:
        # Check routing rules.
        rules = ChatRoutingRule.objects.filter(
            integration=integration,
            notification_type=notification_type,
            enabled=True,
        )

        matched = False
        for rule in rules:
            if rule.role_filter is None:
                matched = True
                break
            if rule.role_filter == recipient_role:
                matched = True
                break

        if not matched:
            continue

        # Build a minimal payload for the builder (no PII stored in DB).
        payload = _build_payload(notification)

        # Create delivery row (get_or_create for idempotency).
        delivery, created = ChatDelivery.objects.get_or_create(
            integration=integration,
            notification_id=notification.pk,
            defaults={
                "notification_type": notification_type,
                "payload_json": payload,
                "status": ChatDelivery.STATUS_PENDING,
            },
        )

        if not created:
            logger.debug(
                "dispatch_notification: delivery already exists for "
                "notification=%s integration=%s — skipping",
                notification.pk,
                integration.pk,
            )
            continue

        # Enqueue Celery task.
        try:
            from .tasks import deliver_chat_message  # avoid circular import
            deliver_chat_message.delay(str(delivery.id))
            delivery_ids.append(delivery.id)
        except Exception:
            logger.exception(
                "dispatch_notification: failed to enqueue deliver_chat_message "
                "for delivery=%s",
                delivery.pk,
            )

    return delivery_ids


def _build_payload(notification: "Notification") -> dict:
    """
    Build a safe, non-PII payload dict from a Notification for builder input.
    """
    teacher = getattr(notification, "teacher", None)
    tenant = getattr(notification, "tenant", None)

    payload: dict = {
        "title": getattr(notification, "title", ""),
        "message": getattr(notification, "message", ""),
        "notification_type": getattr(notification, "notification_type", ""),
        "school_name": tenant.name if tenant else "LearnPuddle",
    }

    if teacher:
        payload["recipient_name"] = teacher.get_full_name() if hasattr(teacher, "get_full_name") else str(teacher)

    return payload
