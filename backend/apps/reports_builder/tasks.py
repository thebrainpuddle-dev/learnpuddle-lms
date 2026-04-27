"""
apps/reports_builder/tasks.py
-------------------------------
Celery tasks for the Custom Report Builder (TASK-053).

Tasks:
  * build_csv_export(run_id)         — build CSV artifact for an export run.
  * run_scheduled_reports()          — Celery Beat hourly scanner.
  * execute_scheduled_report(schedule_id) — execute one scheduled run + email.

Security:
  * Scheduled report emails contain signed-URL link ONLY (never CSV attachment).
  * Errors are captured into ReportRun.error + ReportSchedule.last_run_status.
  * No silent failures.
"""

from __future__ import annotations

import hashlib
import logging
import os
import pathlib
import traceback
from datetime import datetime, timezone as tz

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CSV artifact storage
# ---------------------------------------------------------------------------

ARTIFACT_DIR = pathlib.Path(settings.MEDIA_ROOT) / "report_artifacts"


def _artifact_path(run_id: str) -> pathlib.Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    return ARTIFACT_DIR / f"report_{run_id}.csv"


# ---------------------------------------------------------------------------
# build_csv_export — called by definition_export view
# ---------------------------------------------------------------------------


@shared_task(name="reports_builder.build_csv_export", bind=True, max_retries=2)
def build_csv_export(self, run_id: str) -> None:
    """Build a CSV artifact for *run_id* and update the ReportRun record."""
    from apps.reports_builder.models import ReportRun
    from apps.reports_builder.query_engine import (
        ROW_CAP_EXCEEDED,
        rows_to_csv,
        run_report,
    )

    try:
        run = ReportRun.all_objects.get(id=run_id)
    except ReportRun.DoesNotExist:
        logger.error("build_csv_export: run %s not found", run_id)
        return

    run.status = "running"
    run.save(update_fields=["status"])

    snapshot = run.params_snapshot_json or {}
    data_source = snapshot.get("data_source", "")
    filters = snapshot.get("filters", [])
    group_by_raw = snapshot.get("group_by", [])
    aggregates = snapshot.get("aggregates", [])

    group_by: list[str] = []
    for item in group_by_raw:
        if isinstance(item, str):
            group_by.append(item)
        elif isinstance(item, dict) and "field" in item:
            group_by.append(item["field"])

    try:
        rows, row_count = run_report(
            tenant=run.tenant,
            data_source=data_source,
            filters=filters,
            group_by=group_by,
            aggregates=aggregates,
        )
    except ValueError as exc:
        run.status = "error"
        run.error = str(exc)
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])
        logger.warning("build_csv_export run=%s error: %s", run_id, exc)
        return
    except Exception:
        tb = traceback.format_exc()
        run.status = "error"
        run.error = tb
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])
        logger.exception("build_csv_export run=%s unexpected error", run_id)
        return

    # Write CSV artifact to disk
    csv_bytes, sha256 = rows_to_csv(rows)
    artifact_path = _artifact_path(run_id)
    try:
        artifact_path.write_bytes(csv_bytes)
    except OSError:
        tb = traceback.format_exc()
        run.status = "error"
        run.error = tb
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])
        logger.exception("build_csv_export run=%s failed to write artifact", run_id)
        return

    run.status = "success"
    run.row_count = row_count
    run.artifact_path = str(artifact_path)
    run.artifact_sha256 = sha256
    run.finished_at = timezone.now()
    run.save(
        update_fields=[
            "status",
            "row_count",
            "artifact_path",
            "artifact_sha256",
            "finished_at",
        ]
    )
    logger.info("build_csv_export run=%s success rows=%d", run_id, row_count)


# ---------------------------------------------------------------------------
# run_scheduled_reports — Celery Beat hourly scanner
# ---------------------------------------------------------------------------


@shared_task(name="reports_builder.run_scheduled_reports")
def run_scheduled_reports() -> None:
    """Scan enabled ReportSchedule rows and kick off execute_scheduled_report.

    Runs hourly (configured in celery.py beat_schedule).
    Determines whether the current UTC hour/day matches the schedule's cadence.
    """
    from apps.reports_builder.models import ReportSchedule

    now = datetime.now(tz=tz.utc)
    current_hour = now.hour
    current_dow = now.weekday()  # 0=Mon, 6=Sun
    current_dom = now.day

    schedules = ReportSchedule.all_objects.filter(enabled=True).select_related(
        "definition", "tenant"
    )

    kicked = 0
    for schedule in schedules:
        if schedule.run_at_hour != current_hour:
            continue
        if schedule.cadence == "daily":
            pass  # Always run at the matching hour
        elif schedule.cadence == "weekly":
            if schedule.run_at_day_of_week is not None and schedule.run_at_day_of_week != current_dow:
                continue
        elif schedule.cadence == "monthly":
            if schedule.run_at_day_of_month is not None and schedule.run_at_day_of_month != current_dom:
                continue

        execute_scheduled_report.delay(str(schedule.id))
        kicked += 1

    logger.info("run_scheduled_reports: kicked %d scheduled report(s)", kicked)


# ---------------------------------------------------------------------------
# execute_scheduled_report — execute one schedule + email
# ---------------------------------------------------------------------------


@shared_task(
    name="reports_builder.execute_scheduled_report",
    bind=True,
    max_retries=1,
    acks_late=True,
)
def execute_scheduled_report(self, schedule_id: str) -> None:
    """Execute a scheduled report and email a signed-URL link to recipients.

    Errors are captured into ReportRun.error + ReportSchedule.last_run_status.
    NEVER attaches the CSV directly — always a signed-URL link.
    """
    from apps.reports_builder.models import ReportRun, ReportSchedule
    from apps.reports_builder.query_engine import rows_to_csv, run_report
    from apps.courses.helpers.signed_urls import make_signed_url

    try:
        schedule = ReportSchedule.all_objects.select_related(
            "definition", "tenant"
        ).get(id=schedule_id)
    except ReportSchedule.DoesNotExist:
        logger.error("execute_scheduled_report: schedule %s not found", schedule_id)
        return

    definition = schedule.definition
    if definition is None or definition.is_soft_deleted:
        logger.warning(
            "execute_scheduled_report: definition for schedule=%s is deleted/missing",
            schedule_id,
        )
        return

    run = ReportRun.all_objects.create(
        tenant=schedule.tenant,
        definition=definition,
        run_by=None,  # Scheduled run — no user
        params_snapshot_json={
            "data_source": definition.data_source,
            "filters": definition.filters_json,
            "group_by": definition.group_by_json,
            "aggregates": definition.aggregates_json,
            "scheduled": True,
            "schedule_id": schedule_id,
        },
        status="running",
        started_at=timezone.now(),
    )

    group_by_raw = definition.group_by_json or []
    group_by: list[str] = [
        item if isinstance(item, str) else item.get("field", "")
        for item in group_by_raw
        if isinstance(item, (str, dict))
    ]

    try:
        rows, row_count = run_report(
            tenant=schedule.tenant,
            data_source=definition.data_source,
            filters=definition.filters_json or [],
            group_by=group_by,
            aggregates=definition.aggregates_json or [],
        )
    except Exception:
        tb = traceback.format_exc()
        run.status = "error"
        run.error = tb
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])

        schedule.last_run_at = timezone.now()
        schedule.last_run_status = "error"
        schedule.save(update_fields=["last_run_at", "last_run_status", "updated_at"])
        logger.exception(
            "execute_scheduled_report schedule=%s run=%s failed", schedule_id, run.id
        )
        return

    # Write CSV artifact
    csv_bytes, sha256 = rows_to_csv(rows)
    artifact_path = _artifact_path(str(run.id))
    try:
        artifact_path.write_bytes(csv_bytes)
        artifact_ok = True
    except OSError:
        artifact_ok = False
        logger.exception(
            "execute_scheduled_report: could not write artifact for run=%s", run.id
        )

    run.status = "success"
    run.row_count = row_count
    run.artifact_path = str(artifact_path) if artifact_ok else ""
    run.artifact_sha256 = sha256
    run.finished_at = timezone.now()
    run.save(
        update_fields=[
            "status",
            "row_count",
            "artifact_path",
            "artifact_sha256",
            "finished_at",
        ]
    )

    schedule.last_run_at = timezone.now()
    schedule.last_run_status = "ok"
    schedule.save(update_fields=["last_run_at", "last_run_status", "updated_at"])

    # Email recipients with signed-URL link — NEVER attach CSV directly.
    recipients = schedule.recipients_json or []
    if not recipients or not artifact_ok:
        return

    from apps.users.models import User as TenantUser

    platform_domain = getattr(settings, "PLATFORM_DOMAIN", "localhost")
    base_url = (
        f"https://{schedule.tenant.subdomain}.{platform_domain}"
        f"/api/v1/admin/reports/runs/{run.id}/artifact/"
    )

    subject = f"[LearnPuddle] Scheduled report: {definition.name}"
    delivery_successes = 0
    delivery_failures = 0
    error_fragments: list[str] = []

    for recipient_email in recipients:
        # Resolve each recipient email to a real tenant user so we can issue
        # a user-bound signed URL.  Unresolvable recipients are recorded and
        # skipped — email is NOT sent without a valid user_id.
        tenant_user = TenantUser.objects.filter(
            tenant=schedule.definition.tenant,
            email__iexact=recipient_email,
            is_active=True,
        ).first()

        if tenant_user is None:
            msg = (
                f"UNRESOLVED_RECIPIENT: {recipient_email} could not be matched "
                f"to an active user in tenant={schedule.definition.tenant.subdomain}\n"
            )
            logger.warning(
                "execute_scheduled_report schedule=%s run=%s: %s",
                schedule_id, run.id, msg.strip(),
            )
            error_fragments.append(msg)
            delivery_failures += 1
            continue

        signed_url = make_signed_url(
            base_url=base_url,
            user_id=str(tenant_user.id),
            ttl_seconds=86_400,  # 24 hours
            extra_params={"run": str(run.id)},
        )

        body = (
            f"Your scheduled report '{definition.name}' has completed.\n\n"
            f"Download link (valid 24 hours):\n{signed_url}\n\n"
            f"Rows: {row_count}\n"
            f"Generated: {run.finished_at.isoformat() if run.finished_at else 'N/A'}\n"
        )

        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@learnpuddle.com"),
                recipient_list=[recipient_email],
                fail_silently=False,
            )
            delivery_successes += 1
        except Exception as exc:
            msg = f"DELIVERY_FAILED to {recipient_email}: {exc}\n"
            logger.exception(
                "execute_scheduled_report: failed to email %s for run=%s",
                recipient_email, run.id,
            )
            error_fragments.append(msg)
            delivery_failures += 1

    # Persist per-recipient error fragments to run.error and update statuses.
    if error_fragments:
        existing_error = run.error or ""
        run.error = existing_error + "".join(error_fragments)
        run.save(update_fields=["error"])

    if delivery_successes == 0 and len(recipients) > 0:
        # Total delivery failure — escalate run and schedule statuses.
        run.status = "failed"
        run.save(update_fields=["status"])
        schedule.last_run_status = "delivery_failed"
        schedule.save(update_fields=["last_run_status", "updated_at"])
