"""
Sync engine for integrations_calendar.

``push_events_for_connection(connection)`` diffs the current LMS deadlines
against ``CalendarSyncedEvent`` rows for the given connection, then calls the
appropriate provider (Google / Outlook) to create, update, or delete events.

Design goals:
- Idempotent: re-running produces no duplicate provider events.
- Minimal: create / update / delete only — no bidirectional sync.
- Provider-agnostic: delegates actual HTTP calls to providers/google.py and
  providers/outlook.py.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import TYPE_CHECKING

from django.db.models import Q
from django.utils import timezone

if TYPE_CHECKING:
    from apps.integrations_calendar.models import CalendarConnection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def push_events_for_connection(connection: "CalendarConnection") -> dict:
    """
    Sync all LMS deadlines for *connection.user* to the provider calendar.

    Returns a summary dict::

        {
            "created": int,
            "updated": int,
            "deleted": int,
            "errors": int,
        }

    Raises nothing — all provider errors are caught and logged.  On a fatal
    auth error (401 / invalid_grant) the connection status is set to 'expired'.
    """
    from apps.integrations_calendar.models import CalendarSyncedEvent

    summary = {"created": 0, "updated": 0, "deleted": 0, "errors": 0}

    if connection.status != "active":
        logger.info(
            "sync_engine: skipping connection %s (status=%s)",
            connection.pk, connection.status,
        )
        return summary

    provider = _get_provider(connection)
    if provider is None:
        logger.error("sync_engine: unknown provider %r for connection %s", connection.provider, connection.pk)
        return summary

    # ------------------------------------------------------------------
    # 1. Collect all current LMS events for this user.
    # ------------------------------------------------------------------
    lms_events = _collect_lms_events(connection)

    # ------------------------------------------------------------------
    # 2. Load existing synced-event rows indexed by (source_type, source_id).
    # ------------------------------------------------------------------
    existing: dict[tuple[str, str], CalendarSyncedEvent] = {
        (row.source_type, row.source_id): row
        for row in CalendarSyncedEvent.objects.filter(connection=connection)
    }

    seen_keys: set[tuple[str, str]] = set()

    for event_data in lms_events:
        key = (event_data["source_type"], event_data["source_id"])
        seen_keys.add(key)
        title_hash = _hash_title(event_data["summary"])

        try:
            if key in existing:
                row = existing[key]
                if row.title_hash == title_hash:
                    # Nothing changed — skip.
                    continue
                # Update.
                provider_event_id = provider["upsert"](connection, event_data)
                row.provider_event_id = provider_event_id
                row.title_hash = title_hash
                row.last_pushed_at = timezone.now()
                row.save(update_fields=["provider_event_id", "title_hash", "last_pushed_at"])
                summary["updated"] += 1
            else:
                # Create.
                provider_event_id = provider["upsert"](connection, event_data)
                CalendarSyncedEvent.objects.create(
                    connection=connection,
                    source_type=event_data["source_type"],
                    source_id=event_data["source_id"],
                    provider_event_id=provider_event_id,
                    title_hash=title_hash,
                )
                summary["created"] += 1
        except Exception as exc:
            summary["errors"] += 1
            _handle_provider_error(connection, exc)

    # ------------------------------------------------------------------
    # 3. Delete events that no longer exist in LMS.
    # ------------------------------------------------------------------
    stale_keys = set(existing.keys()) - seen_keys
    for key in stale_keys:
        row = existing[key]
        if row.provider_event_id:
            try:
                provider["delete"](connection, row.provider_event_id)
                summary["deleted"] += 1
            except Exception as exc:
                summary["errors"] += 1
                _handle_provider_error(connection, exc)
        row.delete()

    if summary["errors"] == 0:
        connection.error = ""
        connection.last_synced_at = timezone.now()
        connection.save(update_fields=["error", "last_synced_at"])

    logger.info(
        "sync_engine: connection=%s provider=%s created=%d updated=%d deleted=%d errors=%d",
        connection.pk, connection.provider,
        summary["created"], summary["updated"], summary["deleted"], summary["errors"],
    )
    return summary


# ---------------------------------------------------------------------------
# LMS event collection
# ---------------------------------------------------------------------------


def _collect_lms_events(connection: "CalendarConnection") -> list[dict]:
    """
    Gather all deadline events for the connection's user.

    Returns a list of event dicts, each with:
      source_type, source_id, uid, summary, description, start_dt, end_dt
    """
    user = connection.user
    tenant = connection.tenant
    subdomain = tenant.subdomain if tenant else "learnpuddle"
    platform_domain = _platform_domain()
    events: list[dict] = []

    # --- Assignment due dates ---
    try:
        from apps.progress.models import Assignment

        qs = Assignment.all_objects.filter(
            course__in=_user_course_ids(user),
            due_date__isnull=False,
            is_active=True,
        ).select_related("course")

        for a in qs:
            dt = _to_utc_dt(a.due_date)
            events.append(_make_event(
                source_type="assignment",
                source_id=str(a.id),
                summary=f"[LearnPuddle] {a.title} — Due",
                description=getattr(a, "description", "") or "",
                start_dt=dt,
                end_dt=dt + timedelta(hours=1),
                subdomain=subdomain,
                platform_domain=platform_domain,
            ))
    except Exception:
        logger.exception("sync_engine: error collecting assignment events for user=%s", user.pk)

    return events


def _make_event(
    *,
    source_type: str,
    source_id: str,
    summary: str,
    description: str,
    start_dt: datetime,
    end_dt: datetime,
    subdomain: str,
    platform_domain: str,
) -> dict:
    uid = f"lp-{source_type}-{source_id}@{subdomain}.{platform_domain}"
    return {
        "source_type": source_type,
        "source_id": source_id,
        "uid": uid,
        "summary": summary,
        "description": description[:500] if description else "",
        "start_dt": start_dt,
        "end_dt": end_dt,
    }


# ---------------------------------------------------------------------------
# Provider dispatch
# ---------------------------------------------------------------------------


def _get_provider(connection: "CalendarConnection") -> dict | None:
    """Return a dict of callable provider operations."""
    from apps.integrations_calendar.models import CalendarConnection as CC

    if connection.provider == CC.PROVIDER_GOOGLE:
        from apps.integrations_calendar.providers import google as google_provider

        return {
            "upsert": google_provider.upsert_event,
            "delete": google_provider.delete_event,
        }
    elif connection.provider == CC.PROVIDER_OUTLOOK:
        from apps.integrations_calendar.providers import outlook as outlook_provider

        return {
            "upsert": outlook_provider.upsert_event,
            "delete": outlook_provider.delete_event,
        }
    return None


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def _handle_provider_error(connection: "CalendarConnection", exc: Exception) -> None:
    """
    Classify the exception and update the connection status accordingly.

    - HTTP 401 / 403 / token errors → mark 'expired'.
    - Other errors → log, leave 'active', store error message.
    """
    msg = str(exc)
    error_lower = msg.lower()

    is_auth_error = (
        "401" in msg
        or "403" in msg
        or "invalid_grant" in error_lower
        or "unauthorized" in error_lower
        or "token has been expired" in error_lower
        or "invalid credentials" in error_lower
    )

    if is_auth_error:
        logger.warning(
            "sync_engine: auth error for connection %s — marking expired. Error: %s",
            connection.pk, msg[:200],
        )
        connection.status = "expired"
        connection.error = msg[:500]
        connection.save(update_fields=["status", "error"])
    else:
        logger.error(
            "sync_engine: provider error for connection %s: %s",
            connection.pk, msg[:200],
        )
        connection.error = msg[:500]
        connection.save(update_fields=["error"])


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _to_utc_dt(value) -> datetime:
    """Normalise a date or datetime to UTC-aware datetime."""
    if value is None:
        return timezone.now()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=dt_timezone.utc)
        return value.astimezone(dt_timezone.utc)
    # date → midnight UTC
    return datetime(value.year, value.month, value.day, tzinfo=dt_timezone.utc)


def _hash_title(title: str) -> str:
    return hashlib.sha256(title.encode("utf-8")).hexdigest()


def _user_course_ids(user):
    tenant = getattr(user, "tenant", None)
    if tenant is None:
        return []

    from apps.courses.models import Course

    qs = Course.objects.all_tenants().filter(
        tenant=tenant,
        is_active=True,
        is_published=True,
    )
    if getattr(user, "role", None) == "STUDENT":
        qs = qs.filter(
            Q(assigned_to_all_students=True) | Q(assigned_students=user)
        )
    else:
        qs = qs.filter(
            Q(assigned_to_all=True)
            | Q(assigned_teachers=user)
            | Q(assigned_groups__in=user.teacher_groups.all())
        )
    return qs.distinct().values_list("id", flat=True)


def _platform_domain() -> str:
    from django.conf import settings
    return getattr(settings, "PLATFORM_DOMAIN", "learnpuddle.com")
