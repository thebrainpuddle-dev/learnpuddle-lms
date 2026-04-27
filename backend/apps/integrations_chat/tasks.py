"""
Celery tasks for the integrations_chat app.

deliver_chat_message  — POSTs a pending ChatDelivery to the provider webhook.
prune_chat_deliveries — Deletes terminal delivery rows older than 30 days.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Delivery task
# ---------------------------------------------------------------------------


@shared_task(
    name="integrations_chat.deliver_chat_message",
    bind=True,
    autoretry_for=(RequestException,),
    retry_backoff=True,
    retry_backoff_max=300,  # cap at 5 minutes
    retry_kwargs={"max_retries": 3},
    # Don't store result — delivery state is in ChatDelivery.status.
    ignore_result=True,
)
def deliver_chat_message(self, delivery_id: str) -> dict:
    """
    POST a ChatDelivery's payload to the provider webhook.

    On success:  delivery.status = "sent"
    On 4xx/5xx:  raises RequestException → Celery retries up to 3x
    After 3 failures:  delivery.status = "dlq", audit log entry created.
    """
    from .models import ChatDelivery, ChatIntegration
    from .builders.slack import build_slack_message
    from .builders.teams import build_teams_message
    from .ssrf_guard import safe_post, SSRFError
    from apps.integrations_common.crypto import decrypt_secret
    from utils.audit import log_audit

    try:
        delivery = ChatDelivery.objects.select_related("integration").get(id=delivery_id)
    except ChatDelivery.DoesNotExist:
        logger.warning("deliver_chat_message: delivery %s not found", delivery_id)
        return {"skipped": True, "reason": "not_found"}

    if delivery.status in (ChatDelivery.STATUS_SENT, ChatDelivery.STATUS_DLQ):
        logger.debug("deliver_chat_message: delivery %s already terminal — skipping", delivery_id)
        return {"skipped": True, "reason": delivery.status}

    integration: ChatIntegration = delivery.integration

    # Decrypt webhook URL.
    webhook_url = decrypt_secret(integration.webhook_url_encrypted)
    if not webhook_url:
        logger.error(
            "deliver_chat_message: cannot decrypt webhook URL for integration=%s",
            integration.pk,
        )
        _mark_dlq(delivery, integration, "webhook_url_decryption_failed")
        return {"error": "webhook_url_decryption_failed"}

    # Build message body.
    payload = delivery.payload_json
    notification_type = delivery.notification_type or payload.get("notification_type", "SYSTEM")

    if integration.provider == ChatIntegration.PROVIDER_SLACK:
        body = build_slack_message(notification_type, payload)
    else:
        body = build_teams_message(notification_type, payload)

    # Update attempt counter.
    delivery.attempts += 1
    delivery.last_attempt_at = timezone.now()
    delivery.save(update_fields=["attempts", "last_attempt_at"])

    try:
        resp = safe_post(webhook_url, json=body)
        resp.raise_for_status()
    except SSRFError as exc:
        # SSRF / allowlist failure — don't retry, go straight to DLQ.
        logger.error(
            "deliver_chat_message: SSRF violation delivery=%s integration=%s err=%s",
            delivery_id, integration.pk, exc,
        )
        _mark_dlq(delivery, integration, str(exc)[:500], request=None)
        return {"error": "ssrf_blocked"}
    except RequestException as exc:
        # Celery autoretry_for handles RequestException; after max_retries
        # the task raises MaxRetriesExceededError which we catch below via
        # the on_failure mechanism.  We also update status to "failed" each time.
        delivery.status = ChatDelivery.STATUS_FAILED
        delivery.last_error = str(exc)[:500]
        delivery.save(update_fields=["status", "last_error"])

        # On the final attempt (retries exhausted), move to DLQ.
        if self.request.retries >= self.max_retries:
            _mark_dlq(delivery, integration, str(exc)[:500])
            return {"error": "max_retries_exceeded"}

        raise  # let Celery retry

    # --- Success ---
    delivery.status = ChatDelivery.STATUS_SENT
    delivery.last_error = ""
    delivery.save(update_fields=["status", "last_error"])

    integration.last_delivery_at = timezone.now()
    integration.last_delivery_status = "sent"
    integration.error = ""
    integration.save(update_fields=["last_delivery_at", "last_delivery_status", "error"])

    logger.info(
        "deliver_chat_message: sent delivery=%s integration=%s provider=%s",
        delivery_id, integration.pk, integration.provider,
    )
    return {"sent": True}


def _mark_dlq(delivery, integration, error_snippet: str, request=None):
    """Move delivery to DLQ and emit a single audit log entry."""
    from utils.audit import log_audit

    delivery.status = delivery.STATUS_DLQ
    delivery.last_error = error_snippet[:500]
    delivery.save(update_fields=["status", "last_error"])

    integration.last_delivery_status = "dlq"
    integration.error = error_snippet[:500]
    integration.save(update_fields=["last_delivery_status", "error"])

    log_audit(
        action="CHAT_DELIVERY_FAILED",
        target_type="ChatDelivery",
        target_id=str(delivery.pk),
        target_repr=str(delivery),
        changes={
            "integration_id": str(integration.pk),
            "notification_id": str(delivery.notification_id),
            "error": error_snippet[:200],
        },
        tenant=integration.tenant,
    )


# ---------------------------------------------------------------------------
# Prune task (Beat daily)
# ---------------------------------------------------------------------------


@shared_task(name="integrations_chat.prune_chat_deliveries", ignore_result=True)
def prune_chat_deliveries() -> dict:
    """
    Delete ChatDelivery rows older than 30 days with a terminal status
    (sent or dlq).  Runs daily via Celery Beat.
    """
    from .models import ChatDelivery

    cutoff = timezone.now() - timedelta(days=30)
    count, _ = ChatDelivery.objects.filter(
        created_at__lt=cutoff,
        status__in=[ChatDelivery.STATUS_SENT, ChatDelivery.STATUS_DLQ],
    ).delete()
    logger.info("prune_chat_deliveries: deleted %d old delivery rows", count)
    return {"deleted": count}
