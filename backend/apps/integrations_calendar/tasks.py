"""
Celery tasks for integrations_calendar.

  sync_calendar_connection(connection_id)
      Push events for one active CalendarConnection.
      Retries 3x with exponential backoff on transient errors.
      Marks connection as 'expired' on 401 / invalid_grant.

  sync_all_calendar_connections
      Beat task: enqueues sync_calendar_connection for every active connection.
      Scheduled every 15 minutes in settings.CELERY_BEAT_SCHEDULE.
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="integrations_calendar.sync_calendar_connection",
    max_retries=3,
    default_retry_delay=60,  # seconds; doubled on each retry via countdown
)
def sync_calendar_connection(self, connection_id: str) -> dict:
    """
    Sync a single CalendarConnection.

    On 401 / invalid_grant: mark status='expired' and do NOT retry.
    On other exceptions: retry up to 3 times with exponential backoff.
    """
    from apps.integrations_calendar.models import CalendarConnection
    from apps.integrations_calendar.sync_engine import push_events_for_connection

    try:
        connection = CalendarConnection.objects.get(pk=connection_id)
    except CalendarConnection.DoesNotExist:
        logger.warning(
            "sync_calendar_connection: connection %s not found — skipping",
            connection_id,
        )
        return {"skipped": True, "reason": "not_found"}

    if connection.status != CalendarConnection.STATUS_ACTIVE:
        logger.info(
            "sync_calendar_connection: connection %s status=%s — skipping",
            connection_id, connection.status,
        )
        return {"skipped": True, "reason": connection.status}

    try:
        summary = push_events_for_connection(connection)
        return summary
    except Exception as exc:
        msg = str(exc)
        error_lower = msg.lower()
        is_auth_error = (
            "401" in msg
            or "403" in msg
            or "invalid_grant" in error_lower
            or "unauthorized" in error_lower
            or "token has been expired" in error_lower
        )
        if is_auth_error:
            logger.warning(
                "sync_calendar_connection: auth error for connection %s — marking expired",
                connection_id,
            )
            connection.status = CalendarConnection.STATUS_EXPIRED
            connection.error = msg[:500]
            connection.save(update_fields=["status", "error"])
            # Do not retry auth errors.
            return {"error": "auth_expired", "connection_id": connection_id}

        # Transient error — retry with exponential backoff.
        retry_number = self.request.retries
        countdown = 60 * (2 ** retry_number)  # 60s, 120s, 240s
        logger.warning(
            "sync_calendar_connection: transient error for connection %s (attempt %d/%d): %s",
            connection_id, retry_number + 1, self.max_retries + 1, msg[:200],
        )

        # On the final attempt, write an audit log row before re-raising so
        # the failure is visible in the tenant audit trail even without Flower.
        if retry_number >= self.max_retries:
            try:
                from apps.tenants.models import AuditLog
                AuditLog.objects.create(
                    tenant=connection.tenant,
                    actor=None,
                    action="SYNC_CALENDAR_ERROR",
                    target_type="CalendarConnection",
                    target_id=str(connection_id),
                    changes={
                        "provider": connection.provider,
                        "error": msg[:500],
                        "attempts": retry_number + 1,
                    },
                )
            except Exception:
                logger.exception(
                    "sync_calendar_connection: failed to write SYNC_CALENDAR_ERROR audit log "
                    "for connection %s", connection_id
                )

        raise self.retry(exc=exc, countdown=countdown)


@shared_task(name="integrations_calendar.sync_all_calendar_connections")
def sync_all_calendar_connections() -> dict:
    """
    Beat task: enqueue sync_calendar_connection for every active connection.
    Scheduled every 15 minutes in settings.CELERY_BEAT_SCHEDULE.
    """
    from apps.integrations_calendar.models import CalendarConnection

    connection_ids = list(
        CalendarConnection.objects.filter(
            status=CalendarConnection.STATUS_ACTIVE,
        ).values_list("pk", flat=True)
    )

    enqueued = 0
    for conn_id in connection_ids:
        try:
            sync_calendar_connection.delay(str(conn_id))
            enqueued += 1
        except Exception:
            logger.exception(
                "sync_all_calendar_connections: failed to enqueue connection %s", conn_id
            )

    logger.info(
        "sync_all_calendar_connections: enqueued %d / %d connections",
        enqueued, len(connection_ids),
    )
    return {"enqueued": enqueued, "total": len(connection_ids)}
