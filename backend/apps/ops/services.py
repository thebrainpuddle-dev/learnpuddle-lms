import csv
import hashlib
import hmac
import io
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.core.mail import send_mail
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.courses.models import Content, Course
from apps.courses.video_models import VideoAsset
from apps.reminders.models import ReminderDelivery
from apps.tenants.models import Tenant
from apps.tenants.services import TenantService
from apps.users.models import User
from apps.webhooks.models import WebhookDelivery
from utils.audit import log_audit

from .models import (
    MaintenanceRun,
    MaintenanceSchedule,
    OpsActionApproval,
    OpsActionLog,
    OpsCollectorCursor,
    OpsDeadLetter,
    OpsEvent,
    OpsHealthSnapshot,
    OpsIncident,
    OpsReplayRun,
    OpsRouteError,
)


P1_MTTR_TARGET_MINUTES = 15
P2_MTTR_TARGET_MINUTES = 60

PROBE_TIMEOUT_SECONDS = int(getattr(settings, "OPS_PROBE_TIMEOUT_SECONDS", 5))
PROBE_BASE_URL = getattr(settings, "OPS_PROBE_BASE_URL", "").rstrip("/")
PROBE_SCHEME = getattr(settings, "OPS_PROBE_SCHEME", "https" if not settings.DEBUG else "http")
HARNESS_SHARED_SECRET = getattr(settings, "OPS_HARNESS_SHARED_SECRET", "")
OPS_RETENTION_DAYS = int(getattr(settings, "OPS_RETENTION_DAYS", 30))

HARNESS_REQUIRED_FIELDS = {"status", "observed_at"}


@dataclass
class ProbeResult:
    tenant: Tenant
    theme_ok: bool
    auth_ok: bool
    latency_ms: int | None
    errors: list[str]


def _now() -> datetime:
    return timezone.now()


def _safe_create_event(**kwargs) -> OpsEvent | None:
    try:
        return OpsEvent.objects.create(**kwargs)
    except IntegrityError:
        return None


def create_ops_event(
    *,
    tenant: Tenant | None,
    source: str,
    category: str,
    severity: str,
    status: str,
    event_ts: datetime,
    event_key: str,
    payload_json: dict[str, Any] | None = None,
    confidence: str = "high",
) -> OpsEvent | None:
    return _safe_create_event(
        tenant=tenant,
        source=source,
        category=category,
        severity=severity,
        status=status,
        event_ts=event_ts,
        event_key=event_key,
        payload_json=payload_json or {},
        confidence=confidence,
    )


def _cursor(name: str) -> OpsCollectorCursor:
    obj, _ = OpsCollectorCursor.objects.get_or_create(collector_name=name)
    return obj


def _update_cursor(name: str, ts: datetime | None, row_id: str = "") -> None:
    cur = _cursor(name)
    cur.watermark_ts = ts
    cur.watermark_id = row_id
    cur.save(update_fields=["watermark_ts", "watermark_id", "updated_at"])


def _probe_url(host: str, path: str) -> tuple[str, dict[str, str]]:
    headers: dict[str, str] = {}
    if PROBE_BASE_URL:
        headers["Host"] = host
        return f"{PROBE_BASE_URL}{path}", headers
    return f"{PROBE_SCHEME}://{host}{path}", headers


def _probe_tenant(tenant: Tenant) -> ProbeResult:
    host = f"{tenant.subdomain}.{settings.PLATFORM_DOMAIN}"
    errors: list[str] = []

    # Theme probe
    theme_url, theme_headers = _probe_url(host, "/api/tenants/theme/")
    theme_ok = False
    auth_ok = False
    latency_ms = None

    started = timezone.now()
    try:
        resp = requests.get(theme_url, timeout=PROBE_TIMEOUT_SECONDS, headers=theme_headers)
        payload = resp.json() if "application/json" in resp.headers.get("Content-Type", "") else {}
        theme_ok = resp.status_code < 500 and bool(payload.get("tenant_found", False))
        if not theme_ok:
            errors.append(f"theme_probe_status={resp.status_code}")
    except Exception as exc:
        errors.append(f"theme_probe_error={exc}")

    # Auth probe
    auth_url, auth_headers = _probe_url(host, "/api/users/auth/login/")
    try:
        auth_resp = requests.post(
            auth_url,
            timeout=PROBE_TIMEOUT_SECONDS,
            headers={**auth_headers, "Content-Type": "application/json"},
            json={
                "email": "healthcheck@example.test",
                "password": "not-a-real-password",
                "portal": "tenant",
            },
        )
        auth_ok = auth_resp.status_code in {200, 400, 401, 403, 429}
        if not auth_ok:
            errors.append(f"auth_probe_status={auth_resp.status_code}")
    except Exception as exc:
        errors.append(f"auth_probe_error={exc}")

    latency_ms = int((timezone.now() - started).total_seconds() * 1000)

    return ProbeResult(
        tenant=tenant,
        theme_ok=theme_ok,
        auth_ok=auth_ok,
        latency_ms=latency_ms,
        errors=errors,
    )


def _apply_probe_to_snapshot(result: ProbeResult, now: datetime) -> OpsHealthSnapshot:
    snapshot, _ = OpsHealthSnapshot.objects.get_or_create(tenant=result.tenant)

    prev_status = snapshot.current_status
    prev_auth_ok = snapshot.auth_probe_ok

    full_success = result.theme_ok and result.auth_ok

    snapshot.theme_probe_ok = result.theme_ok
    snapshot.auth_probe_ok = result.auth_ok

    snapshot.theme_consecutive_failures = 0 if result.theme_ok else snapshot.theme_consecutive_failures + 1
    snapshot.auth_consecutive_failures = 0 if result.auth_ok else snapshot.auth_consecutive_failures + 1
    snapshot.consecutive_failures = 0 if full_success else snapshot.consecutive_failures + 1

    snapshot.last_probe_at = now
    snapshot.last_latency_ms = result.latency_ms
    snapshot.freshness_seconds = 0
    snapshot.last_probe_error = " | ".join(result.errors)[:1000]

    if full_success:
        snapshot.last_ok_at = now

    if result.tenant.maintenance_mode_enabled:
        next_status = "MAINTENANCE"
    elif full_success:
        next_status = "HEALTHY"
    elif snapshot.consecutive_failures >= 2:
        next_status = "DOWN"
    else:
        next_status = "DEGRADED"

    if next_status != prev_status:
        snapshot.status_changed_at = now
    snapshot.current_status = next_status
    snapshot.save()

    # Emit transition events only
    if next_status != prev_status:
        if next_status in {"DEGRADED", "DOWN"}:
            create_ops_event(
                tenant=result.tenant,
                source="synthetic",
                category="availability_probe",
                severity="P1" if next_status == "DOWN" else "P2",
                status="FAIL",
                event_ts=now,
                event_key=f"probe_status:{result.tenant.id}:{prev_status}->{next_status}:{now.isoformat()}",
                payload_json={
                    "from": prev_status,
                    "to": next_status,
                    "theme_ok": result.theme_ok,
                    "auth_ok": result.auth_ok,
                    "latency_ms": result.latency_ms,
                    "errors": result.errors,
                },
            )
        elif prev_status in {"DEGRADED", "DOWN", "MAINTENANCE"} and next_status == "HEALTHY":
            create_ops_event(
                tenant=result.tenant,
                source="synthetic",
                category="availability_probe",
                severity="P2",
                status="RECOVER",
                event_ts=now,
                event_key=f"probe_recover:{result.tenant.id}:{now.isoformat()}",
                payload_json={"from": prev_status, "to": next_status},
            )

    # Auth probe transition event for incident analytics
    if prev_auth_ok != result.auth_ok:
        create_ops_event(
            tenant=result.tenant,
            source="synthetic",
            category="auth_probe",
            severity="P1" if not result.auth_ok else "P2",
            status="FAIL" if not result.auth_ok else "RECOVER",
            event_ts=now,
            event_key=f"auth_probe:{result.tenant.id}:{prev_auth_ok}->{result.auth_ok}:{now.isoformat()}",
            payload_json={"auth_ok": result.auth_ok},
        )

    return snapshot


def run_synthetic_probes() -> dict[str, int]:
    now = _now()
    tenants = list(Tenant.objects.filter(is_active=True).only("id", "name", "subdomain", "maintenance_mode_enabled"))
    checked = 0

    for tenant in tenants:
        result = _probe_tenant(tenant)
        _apply_probe_to_snapshot(result, now)
        checked += 1

    evaluate_incidents(now=now)
    return {"checked": checked}


def _iter_incremental(qs, ts_field: str, cursor_name: str, limit: int = 500):
    cur = _cursor(cursor_name)
    ts = cur.watermark_ts
    row_id = cur.watermark_id

    if ts:
        filt = Q(**{f"{ts_field}__gt": ts})
        if row_id:
            filt = filt | (Q(**{ts_field: ts}) & Q(id__gt=row_id))
        qs = qs.filter(filt)

    rows = list(qs.order_by(ts_field, "id")[:limit])
    if rows:
        last = rows[-1]
        _update_cursor(cursor_name, getattr(last, ts_field), str(last.id))
    return rows


def _create_internal_failure_events(now: datetime) -> dict[str, int]:
    counts = {"video": 0, "reminder": 0, "webhook": 0, "webhook_recover": 0}

    # Video failures
    video_rows = _iter_incremental(
        VideoAsset.objects.select_related("content__module__course__tenant").filter(status="FAILED"),
        "updated_at",
        "video_failed_sweep",
    )
    for row in video_rows:
        tenant = row.content.module.course.tenant
        key = f"video_failed:{row.id}:{row.updated_at.isoformat()}"
        evt = create_ops_event(
            tenant=tenant,
            source="internal",
            category="background_jobs",
            severity="P2",
            status="FAIL",
            event_ts=row.updated_at,
            event_key=key,
            payload_json={"video_asset_id": str(row.id), "error": row.error_message[:500]},
        )
        if evt:
            counts["video"] += 1

    # Reminder failures
    reminder_rows = _iter_incremental(
        ReminderDelivery.objects.select_related("campaign__tenant", "teacher").filter(status="FAILED"),
        "created_at",
        "reminder_failed_sweep",
    )
    for row in reminder_rows:
        key = f"reminder_failed:{row.id}:{row.created_at.isoformat()}"
        evt = create_ops_event(
            tenant=row.campaign.tenant,
            source="internal",
            category="deliverability",
            severity="P2",
            status="FAIL",
            event_ts=row.created_at,
            event_key=key,
            payload_json={"delivery_id": str(row.id), "teacher_id": str(row.teacher_id), "error": row.error[:500]},
        )
        if evt:
            counts["reminder"] += 1

    # Webhook failures: incremental by created_at cursor
    webhook_fail_rows = _iter_incremental(
        WebhookDelivery.objects.select_related("endpoint__tenant").filter(status__in=["failed", "retrying"]),
        "created_at",
        "webhook_failed_sweep",
    )
    for row in webhook_fail_rows:
        key = f"webhook_failed:{row.id}:{row.status}:{row.created_at.isoformat()}"
        evt = create_ops_event(
            tenant=row.endpoint.tenant,
            source="internal",
            category="webhook_delivery",
            severity="P2",
            status="FAIL",
            event_ts=row.created_at,
            event_key=key,
            payload_json={
                "delivery_id": str(row.id),
                "status": row.status,
                "attempt_count": row.attempt_count,
                "error": row.error_message[:500],
            },
        )
        if evt:
            counts["webhook"] += 1

    # Webhook recoveries: incremental by delivered_at cursor
    webhook_success_rows = _iter_incremental(
        WebhookDelivery.objects.select_related("endpoint__tenant").filter(
            delivered_at__isnull=False,
            status="success",
        ),
        "delivered_at",
        "webhook_recover_sweep",
    )
    for row in webhook_success_rows:
        had_fail = OpsEvent.objects.filter(
            category="webhook_delivery",
            tenant=row.endpoint.tenant,
            status="FAIL",
            payload_json__delivery_id=str(row.id),
        ).exists()
        if not had_fail:
            continue
        key = f"webhook_recover:{row.id}:{row.delivered_at.isoformat()}"
        evt = create_ops_event(
            tenant=row.endpoint.tenant,
            source="internal",
            category="webhook_delivery",
            severity="P2",
            status="RECOVER",
            event_ts=row.delivered_at,
            event_key=key,
            payload_json={"delivery_id": str(row.id), "response_status_code": row.response_status_code},
        )
        if evt:
            counts["webhook_recover"] += 1

    return counts


def sweep_internal_failure_events() -> dict[str, int]:
    now = _now()
    counts = _create_internal_failure_events(now)
    evaluate_incidents(now=now)
    return counts


def _incident_open_or_update(
    *,
    dedupe_key: str,
    severity: str,
    scope: str,
    rule_id: str,
    title: str,
    tenant: Tenant | None,
    description: str,
    metadata: dict[str, Any] | None = None,
    now: datetime,
) -> OpsIncident:
    incident, created = OpsIncident.objects.get_or_create(
        dedupe_key=dedupe_key,
        defaults={
            "severity": severity,
            "scope": scope,
            "rule_id": rule_id,
            "title": title,
            "tenant": tenant,
            "description": description,
            "status": "OPEN",
            "started_at": now,
            "last_seen_at": now,
            "metadata_json": metadata or {},
        },
    )
    if not created and incident.status in {"OPEN", "ACKED"}:
        incident.last_seen_at = now
        incident.metadata_json = {**incident.metadata_json, **(metadata or {})}
        incident.save(update_fields=["last_seen_at", "metadata_json", "updated_at"])
    if created:
        _notify_super_admins_incident_open(incident)
    return incident


def _resolve_incident(incident: OpsIncident, now: datetime) -> None:
    if incident.status == "RESOLVED":
        return
    incident.status = "RESOLVED"
    incident.resolved_at = now
    incident.mttr_seconds = int((incident.resolved_at - incident.started_at).total_seconds())
    incident.save(update_fields=["status", "resolved_at", "mttr_seconds", "updated_at"])


def evaluate_incidents(now: datetime | None = None) -> dict[str, int]:
    now = now or _now()
    opened = 0
    resolved = 0

    active_tenants = Tenant.objects.filter(is_active=True)
    total_active = active_tenants.count()
    down_snapshots = OpsHealthSnapshot.objects.filter(tenant__is_active=True, current_status="DOWN")
    down_count = down_snapshots.count()

    # P1: multi-tenant outage
    p1_threshold = max(5, math.ceil(0.2 * total_active)) if total_active else 5
    p1_multi_key = "p1_multi_tenant_outage:global"
    p1_multi_incident = OpsIncident.objects.filter(dedupe_key=p1_multi_key).first()
    if down_count >= p1_threshold:
        if not p1_multi_incident or p1_multi_incident.status == "RESOLVED":
            opened += 1
        _incident_open_or_update(
            dedupe_key=p1_multi_key,
            severity="P1",
            scope="GLOBAL",
            rule_id="p1_multi_tenant_outage",
            title="Multi-tenant outage detected",
            tenant=None,
            description=f"{down_count} tenants are DOWN (threshold={p1_threshold}).",
            metadata={"down_count": down_count, "threshold": p1_threshold},
            now=now,
        )
    elif p1_multi_incident and p1_multi_incident.status in {"OPEN", "ACKED"}:
        if now - p1_multi_incident.last_seen_at >= timedelta(minutes=10):
            _resolve_incident(p1_multi_incident, now)
            resolved += 1

    # P1: platform auth outage
    auth_bad_count = OpsHealthSnapshot.objects.filter(
        tenant__is_active=True,
        auth_consecutive_failures__gte=2,
        tenant__maintenance_mode_enabled=False,
    ).count()
    auth_threshold = max(1, math.ceil(0.2 * total_active)) if total_active else 1
    p1_auth_key = "p1_auth_outage:global"
    p1_auth_incident = OpsIncident.objects.filter(dedupe_key=p1_auth_key).first()
    if auth_bad_count >= auth_threshold:
        if not p1_auth_incident or p1_auth_incident.status == "RESOLVED":
            opened += 1
        _incident_open_or_update(
            dedupe_key=p1_auth_key,
            severity="P1",
            scope="GLOBAL",
            rule_id="p1_auth_outage",
            title="Platform auth probe outage",
            tenant=None,
            description=f"{auth_bad_count} tenants failing auth probes (threshold={auth_threshold}).",
            metadata={"auth_bad_count": auth_bad_count, "threshold": auth_threshold},
            now=now,
        )
    elif p1_auth_incident and p1_auth_incident.status in {"OPEN", "ACKED"}:
        if now - p1_auth_incident.last_seen_at >= timedelta(minutes=10):
            _resolve_incident(p1_auth_incident, now)
            resolved += 1

    # P2: tenant status persistence
    for snapshot in OpsHealthSnapshot.objects.select_related("tenant").filter(tenant__is_active=True):
        if snapshot.tenant.maintenance_mode_enabled:
            continue

        rule_id = None
        title = None
        if snapshot.current_status == "DOWN" and snapshot.status_changed_at <= now - timedelta(minutes=2):
            rule_id = "p2_tenant_down"
            title = f"Tenant down: {snapshot.tenant.name}"
        elif snapshot.current_status == "DEGRADED" and snapshot.status_changed_at <= now - timedelta(minutes=10):
            rule_id = "p2_tenant_degraded"
            title = f"Tenant degraded: {snapshot.tenant.name}"

        if rule_id:
            key = f"{rule_id}:{snapshot.tenant_id}"
            existing = OpsIncident.objects.filter(dedupe_key=key).first()
            if not existing or existing.status == "RESOLVED":
                opened += 1
            _incident_open_or_update(
                dedupe_key=key,
                severity="P2",
                scope="TENANT",
                rule_id=rule_id,
                title=title,
                tenant=snapshot.tenant,
                description=f"Status persisted as {snapshot.current_status}.",
                metadata={"status": snapshot.current_status},
                now=now,
            )

    # P2: internal burst thresholds
    fifteen_min_ago = now - timedelta(minutes=15)
    burst_events = (
        OpsEvent.objects.filter(
            status="FAIL",
            event_ts__gte=fifteen_min_ago,
            category__in=["background_jobs", "webhook_delivery", "deliverability"],
            tenant__is_active=True,
        )
        .values("tenant_id", "category")
        .annotate(c=Count("id"))
    )
    thresholds = {
        "background_jobs": 3,
        "webhook_delivery": 10,
        "deliverability": 10,
    }
    for row in burst_events:
        if row["c"] < thresholds[row["category"]]:
            continue
        tenant = Tenant.objects.filter(id=row["tenant_id"]).first()
        if not tenant:
            continue
        rule_id = f"p2_{row['category']}_burst"
        key = f"{rule_id}:{tenant.id}"
        existing = OpsIncident.objects.filter(dedupe_key=key).first()
        if not existing or existing.status == "RESOLVED":
            opened += 1
        _incident_open_or_update(
            dedupe_key=key,
            severity="P2",
            scope="TENANT",
            rule_id=rule_id,
            title=f"{row['category']} burst: {tenant.name}",
            tenant=tenant,
            description=f"{row['c']} failures in 15 minutes.",
            metadata={"count": row["c"], "category": row["category"]},
            now=now,
        )

    # Auto-resolve tenant incidents on recovery gate
    five_min_ago = now - timedelta(minutes=5)
    for incident in OpsIncident.objects.select_related("tenant").filter(scope="TENANT", status__in=["OPEN", "ACKED"]):
        if not incident.tenant_id:
            continue
        snapshot = OpsHealthSnapshot.objects.filter(tenant_id=incident.tenant_id).first()
        healthy_gate = bool(
            snapshot
            and snapshot.current_status == "HEALTHY"
            and snapshot.status_changed_at <= now - timedelta(minutes=1)
        )
        no_recent_related_fails = not OpsEvent.objects.filter(
            tenant_id=incident.tenant_id,
            status="FAIL",
            event_ts__gte=five_min_ago,
        ).exists()
        if healthy_gate and no_recent_related_fails:
            _resolve_incident(incident, now)
            resolved += 1

    return {"opened": opened, "resolved": resolved}


def _notify_super_admins_incident_open(incident: OpsIncident) -> None:
    try:
        recipients = list(
            User.objects.filter(role="SUPER_ADMIN", is_active=True).values_list("email", flat=True)
        )
        if not recipients:
            return
        send_mail(
            subject=f"[{incident.severity}] Ops incident opened: {incident.title}",
            message=(
                f"Incident: {incident.title}\n"
                f"Severity: {incident.severity}\n"
                f"Scope: {incident.scope}\n"
                f"Started at: {incident.started_at.isoformat()}\n"
                f"Rule: {incident.rule_id}\n"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=True,
        )
    except Exception:
        pass


def verify_harness_signature(raw_body: bytes, signature: str) -> bool:
    if not HARNESS_SHARED_SECRET:
        return False
    sig = signature.strip()
    if sig.startswith("sha256="):
        sig = sig.split("=", 1)[1]
    expected = hmac.new(HARNESS_SHARED_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def _validate_harness_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "payload_not_object"

    missing = sorted(field for field in HARNESS_REQUIRED_FIELDS if not payload.get(field))
    if missing:
        return False, f"missing_required_fields:{','.join(missing)}"

    if not payload.get("tenant_id") and not payload.get("tenant_subdomain"):
        return False, "tenant_reference_required"

    status_value = str(payload.get("status", "")).upper()
    if status_value not in {"FAILED", "FAIL", "RECOVERED", "RECOVER", "OK", "SUCCESS"}:
        return False, "invalid_status"

    return True, "ok"


def ingest_harness_event(payload: dict[str, Any], received_at: datetime | None = None) -> tuple[bool, str]:
    received_at = received_at or _now()

    valid, reason = _validate_harness_payload(payload)
    if not valid:
        OpsDeadLetter.objects.create(
            source="harness",
            reason=reason,
            payload_json=payload if isinstance(payload, dict) else {"raw": str(payload)},
            received_at=received_at,
        )
        return False, reason

    tenant = None
    if payload.get("tenant_id"):
        tenant = Tenant.objects.filter(id=payload.get("tenant_id"), is_active=True).first()
    if tenant is None and payload.get("tenant_subdomain"):
        tenant = Tenant.objects.filter(subdomain=payload.get("tenant_subdomain"), is_active=True).first()

    if tenant is None:
        OpsDeadLetter.objects.create(
            source="harness",
            reason="unknown_tenant",
            payload_json=payload,
            received_at=received_at,
        )
        return False, "unknown_tenant"

    observed_at = payload.get("observed_at")
    try:
        event_ts = datetime.fromisoformat(observed_at.replace("Z", "+00:00")) if observed_at else received_at
        if timezone.is_naive(event_ts):
            event_ts = timezone.make_aware(event_ts, timezone=dt_timezone.utc)
    except Exception:
        event_ts = received_at

    age = received_at - event_ts
    if age > timedelta(hours=24):
        OpsDeadLetter.objects.create(
            source="harness",
            reason="late_event_over_24h",
            payload_json=payload,
            received_at=received_at,
        )
        return False, "late_event_over_24h"

    confidence = "medium" if age > timedelta(minutes=10) else "high"

    harness_event_id = payload.get("harness_event_id")
    if harness_event_id:
        event_key = f"harness:{harness_event_id}"
    else:
        event_key = (
            f"harness:{tenant.id}:{payload.get('check_name', 'unknown')}:{event_ts.isoformat()}:{payload.get('status', 'UNKNOWN')}"
        )

    input_status = str(payload.get("status", "")).upper()
    status = "FAIL" if input_status in {"FAILED", "FAIL"} else "RECOVER"
    severity = payload.get("severity", "P2") if payload.get("severity") in {"P1", "P2"} else "P2"

    evt = create_ops_event(
        tenant=tenant,
        source="harness",
        category="harness_external",
        severity=severity,
        status=status,
        event_ts=event_ts,
        event_key=event_key,
        payload_json=payload,
        confidence=confidence,
    )
    if evt is None:
        return True, "duplicate"

    evaluate_incidents(now=received_at)
    return True, str(evt.id)


def _data_quality(freshness_seconds: int, lag_seconds: int) -> str:
    worst = max(freshness_seconds, lag_seconds)
    if worst <= 120:
        return "ok"
    if worst <= 300:
        return "degraded"
    return "stale"


def get_pipeline_health() -> dict[str, Any]:
    now = _now()
    oldest_probe = OpsHealthSnapshot.objects.exclude(last_probe_at__isnull=True).order_by("last_probe_at").first()
    freshness_seconds = int((now - oldest_probe.last_probe_at).total_seconds()) if oldest_probe else 999999

    oldest_cursor = OpsCollectorCursor.objects.exclude(watermark_ts__isnull=True).order_by("watermark_ts").first()
    lag_seconds = int((now - oldest_cursor.watermark_ts).total_seconds()) if oldest_cursor else 999999

    return {
        "generated_at": now,
        "data_freshness_seconds": freshness_seconds,
        "pipeline_lag_seconds": lag_seconds,
        "data_quality": _data_quality(freshness_seconds, lag_seconds),
    }


def apply_tenant_maintenance(
    *,
    tenant: Tenant,
    enabled: bool,
    reason: str,
    ends_at: datetime | None,
    actor: User | None = None,
    request=None,
) -> Tenant:
    tenant.maintenance_mode_enabled = bool(enabled)
    tenant.maintenance_mode_reason = reason[:500] if enabled else ""
    tenant.maintenance_mode_ends_at = ends_at if enabled else None
    tenant.save(update_fields=["maintenance_mode_enabled", "maintenance_mode_reason", "maintenance_mode_ends_at", "updated_at"])

    OpsActionLog.objects.create(
        actor=actor,
        action="TENANT_MAINTENANCE_ON" if enabled else "TENANT_MAINTENANCE_OFF",
        target_type="Tenant",
        target_id=str(tenant.id),
        reason=reason,
        details_json={"ends_at": ends_at.isoformat() if ends_at else None},
    )

    create_ops_event(
        tenant=tenant,
        source="internal",
        category="maintenance",
        severity="P2",
        status="INFO" if enabled else "RECOVER",
        event_ts=_now(),
        event_key=f"maintenance:{tenant.id}:{enabled}:{_now().isoformat()}",
        payload_json={"reason": reason, "ends_at": ends_at.isoformat() if ends_at else None},
    )

    if request is not None:
        log_audit(
            "SETTINGS_CHANGE",
            "Tenant",
            target_id=str(tenant.id),
            target_repr=tenant.name,
            changes={
                "maintenance_mode_enabled": enabled,
                "maintenance_mode_reason": reason,
                "maintenance_mode_ends_at": ends_at.isoformat() if ends_at else None,
            },
            request=request,
        )

    _notify_tenant_admin_maintenance(tenant)
    return tenant


def _notify_tenant_admin_maintenance(tenant: Tenant) -> None:
    admin = User.objects.filter(tenant=tenant, role="SCHOOL_ADMIN", is_active=True).first()
    if not admin:
        return
    try:
        if tenant.maintenance_mode_enabled:
            subject = f"Scheduled maintenance for {tenant.name}"
            message = (
                f"Hi {admin.first_name or 'Admin'},\n\n"
                f"Your LMS tenant is in maintenance mode.\n"
                f"Reason: {tenant.maintenance_mode_reason or 'Planned maintenance'}\n"
                f"Ends at: {tenant.maintenance_mode_ends_at.isoformat() if tenant.maintenance_mode_ends_at else 'TBD'}\n"
            )
        else:
            subject = f"Maintenance completed for {tenant.name}"
            message = (
                f"Hi {admin.first_name or 'Admin'},\n\n"
                f"Maintenance mode has ended for your LMS tenant.\n"
            )

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[admin.email],
            fail_silently=True,
        )
    except Exception:
        pass


def _weekday_index(day_name: str) -> int:
    mapping = {
        "MONDAY": 0,
        "TUESDAY": 1,
        "WEDNESDAY": 2,
        "THURSDAY": 3,
        "FRIDAY": 4,
        "SATURDAY": 5,
        "SUNDAY": 6,
    }
    return mapping.get(day_name.upper(), 6)


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> datetime:
    d = datetime(year, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    candidate = d + timedelta(days=7 * (n - 1))
    if candidate.month == month:
        return candidate

    # If requested weekday occurrence does not exist (e.g. 5th Sunday), use last one in month.
    last_valid = d
    while True:
        nxt = last_valid + timedelta(days=7)
        if nxt.month != month:
            return last_valid
        last_valid = nxt


def run_maintenance_scheduler(now: datetime | None = None) -> dict[str, Any]:
    now = now or _now()
    schedule = MaintenanceSchedule.objects.filter(enabled=True).first()
    if not schedule:
        return {"running": False, "reason": "schedule_disabled"}

    tz = ZoneInfo(schedule.timezone)
    now_local = now.astimezone(tz)
    start_local_date = _nth_weekday_of_month(
        now_local.year,
        now_local.month,
        _weekday_index(schedule.day),
        schedule.week_of_month,
    )
    start_local = datetime.combine(start_local_date.date(), schedule.start_time, tzinfo=tz)
    end_local = start_local + timedelta(minutes=schedule.duration_minutes)

    start_utc = start_local.astimezone(dt_timezone.utc)
    end_utc = end_local.astimezone(dt_timezone.utc)

    running = MaintenanceRun.objects.filter(status="RUNNING").first()

    if start_utc <= now <= end_utc:
        if not running:
            run = MaintenanceRun.objects.create(
                schedule=schedule,
                starts_at=start_utc,
                ends_at=end_utc,
                status="RUNNING",
                reason="Scheduled monthly maintenance",
            )
            with transaction.atomic():
                active_tenants = Tenant.objects.filter(is_active=True)
                active_tenants.update(
                    maintenance_mode_enabled=True,
                    maintenance_mode_reason="Scheduled monthly maintenance",
                    maintenance_mode_ends_at=end_utc,
                )
            OpsActionLog.objects.create(action="GLOBAL_MAINTENANCE_ON", reason="Scheduled monthly maintenance")
            create_ops_event(
                tenant=None,
                source="internal",
                category="maintenance",
                severity="P2",
                status="INFO",
                event_ts=now,
                event_key=f"global_maintenance_on:{run.id}",
                payload_json={"run_id": str(run.id), "ends_at": end_utc.isoformat()},
            )
        return {"running": True, "starts_at": start_utc, "ends_at": end_utc}

    if running and now > running.ends_at:
        running.status = "COMPLETED"
        running.save(update_fields=["status", "updated_at"])
        with transaction.atomic():
            Tenant.objects.filter(
                maintenance_mode_enabled=True,
                maintenance_mode_reason="Scheduled monthly maintenance",
                maintenance_mode_ends_at__lte=now,
            ).update(
                maintenance_mode_enabled=False,
                maintenance_mode_reason="",
                maintenance_mode_ends_at=None,
            )
        OpsActionLog.objects.create(action="GLOBAL_MAINTENANCE_OFF", reason="Scheduled monthly maintenance completed")
        create_ops_event(
            tenant=None,
            source="internal",
            category="maintenance",
            severity="P2",
            status="RECOVER",
            event_ts=now,
            event_key=f"global_maintenance_off:{running.id}:{now.isoformat()}",
            payload_json={"run_id": str(running.id)},
        )

    return {"running": False, "starts_at": start_utc, "ends_at": end_utc}


def apply_bulk_action(
    *,
    action: str,
    tenant_ids: list[str],
    reason: str,
    actor: User | None,
    request=None,
) -> dict[str, int]:
    tenants = list(Tenant.objects.filter(id__in=tenant_ids))
    touched = 0
    now = _now()

    with transaction.atomic():
        for tenant in tenants:
            if action == "ENABLE_MAINTENANCE":
                apply_tenant_maintenance(
                    tenant=tenant,
                    enabled=True,
                    reason=reason or "Bulk maintenance",
                    ends_at=now + timedelta(hours=3),
                    actor=actor,
                    request=request,
                )
                touched += 1
            elif action == "DISABLE_MAINTENANCE":
                apply_tenant_maintenance(
                    tenant=tenant,
                    enabled=False,
                    reason="",
                    ends_at=None,
                    actor=actor,
                    request=request,
                )
                touched += 1
            elif action == "ACTIVATE_TENANT":
                if not tenant.is_active:
                    tenant.is_active = True
                    tenant.save(update_fields=["is_active", "updated_at"])
                    touched += 1
            elif action == "DEACTIVATE_TENANT":
                if tenant.is_active:
                    tenant.is_active = False
                    tenant.save(update_fields=["is_active", "updated_at"])
                    touched += 1

    OpsActionLog.objects.create(
        actor=actor,
        action=f"BULK_{action}",
        reason=reason,
        details_json={"tenant_ids": tenant_ids, "touched": touched},
    )
    return {"requested": len(tenant_ids), "touched": touched}


PROBLEM_STATUS_CODES = {429, 500}
OPS_ACTION_REQUIRING_APPROVAL = {
    "requeue_video_pipeline",
    "replay_course_publish",
    "toggle_tenant_maintenance",
    "clear_tenant_cache_scope",
}


def _normalize_portal(value: str | None) -> str:
    normalized = str(value or "").upper().strip()
    if normalized in {"SUPER_ADMIN", "TENANT_ADMIN", "TEACHER"}:
        return normalized
    return "UNKNOWN"


def _normalize_tab(value: str | None) -> str:
    return str(value or "").strip().lower()[:64]


def _normalize_endpoint(value: str | None) -> str:
    endpoint = str(value or "").strip()[:255]
    if not endpoint:
        return "/"
    return endpoint.split("?", 1)[0]


def _normalize_method(value: str | None) -> str:
    method = str(value or "GET").upper().strip()
    return method if method else "GET"


def _build_error_fingerprint(
    *,
    tenant_id: str | None,
    portal: str,
    tab_key: str,
    method: str,
    endpoint: str,
    status_code: int,
) -> str:
    return f"{tenant_id or 'global'}::{portal}::{tab_key or '-'}::{method}::{endpoint}::{status_code}"


def record_route_error(
    *,
    tenant: Tenant | None,
    portal: str,
    tab_key: str,
    route_path: str = "",
    component_name: str = "",
    endpoint: str,
    method: str,
    status_code: int,
    request_id: str = "",
    payload: dict[str, Any] | None = None,
    response_excerpt: str = "",
    error_message: str = "",
    observed_at: datetime | None = None,
) -> OpsRouteError | None:
    status_code_int = int(status_code or 0)
    if status_code_int not in PROBLEM_STATUS_CODES:
        return None

    observed_at = observed_at or _now()
    portal_value = _normalize_portal(portal)
    tab_value = _normalize_tab(tab_key)
    endpoint_value = _normalize_endpoint(endpoint)
    method_value = _normalize_method(method)
    route_value = str(route_path or "")[:255]
    component_value = str(component_name or "")[:128]
    fingerprint = _build_error_fingerprint(
        tenant_id=str(tenant.id) if tenant else None,
        portal=portal_value,
        tab_key=tab_value,
        method=method_value,
        endpoint=endpoint_value,
        status_code=status_code_int,
    )

    payload_json = payload if isinstance(payload, dict) else {}
    sample_response = str(response_excerpt or "")[:2000]
    sample_error = str(error_message or "")[:1000]
    request_id_value = str(request_id or "")[:64]

    error_group, created = OpsRouteError.objects.get_or_create(
        fingerprint=fingerprint,
        defaults={
            "tenant": tenant,
            "portal": portal_value,
            "tab_key": tab_value,
            "route_path": route_value,
            "component_name": component_value,
            "endpoint": endpoint_value,
            "method": method_value,
            "status_code": status_code_int,
            "first_seen_at": observed_at,
            "last_seen_at": observed_at,
            "last_request_id": request_id_value,
            "total_count": 1,
            "count_1h": 1,
            "count_24h": 1,
            "sample_payload_json": payload_json,
            "sample_response_excerpt": sample_response,
            "sample_error_message": sample_error,
        },
    )
    if created:
        return error_group

    within_1h = (observed_at - error_group.last_seen_at) <= timedelta(hours=1)
    within_24h = (observed_at - error_group.last_seen_at) <= timedelta(hours=24)

    error_group.tenant = tenant or error_group.tenant
    error_group.portal = portal_value
    error_group.tab_key = tab_value
    error_group.route_path = route_value or error_group.route_path
    error_group.component_name = component_value or error_group.component_name
    error_group.last_seen_at = observed_at
    error_group.last_request_id = request_id_value or error_group.last_request_id
    error_group.total_count = error_group.total_count + 1
    error_group.count_1h = (error_group.count_1h + 1) if within_1h else 1
    error_group.count_24h = (error_group.count_24h + 1) if within_24h else 1
    if payload_json:
        error_group.sample_payload_json = payload_json
    if sample_response:
        error_group.sample_response_excerpt = sample_response
    if sample_error:
        error_group.sample_error_message = sample_error
    error_group.save()
    return error_group


def lock_route_error_group(
    *,
    error_group: OpsRouteError,
    actor: User | None,
    note: str = "",
) -> OpsIncident:
    now = _now()
    if not error_group.is_locked:
        error_group.is_locked = True
        error_group.locked_at = now
        error_group.locked_by = actor
        error_group.save(update_fields=["is_locked", "locked_at", "locked_by", "updated_at"])

    severity = "P1" if error_group.status_code == 500 else "P2"
    title = f"{error_group.status_code} on {error_group.tab_key or 'unknown-tab'}"
    dedupe_key = f"ops_route_error:{hashlib.sha256(error_group.fingerprint.encode('utf-8')).hexdigest()[:64]}"

    incident, _created = OpsIncident.objects.get_or_create(
        dedupe_key=dedupe_key,
        defaults={
            "severity": severity,
            "scope": "TENANT" if error_group.tenant_id else "GLOBAL",
            "tenant": error_group.tenant,
            "rule_id": "ops_route_error",
            "title": title,
            "description": note[:1000] if note else f"Locked route error for {error_group.endpoint}",
            "status": "OPEN",
            "started_at": now,
            "last_seen_at": now,
            "metadata_json": {
                "error_group_id": str(error_group.id),
                "status_code": error_group.status_code,
                "endpoint": error_group.endpoint,
                "tab_key": error_group.tab_key,
                "request_id": error_group.last_request_id,
            },
        },
    )
    if incident.status == "RESOLVED":
        incident.status = "OPEN"
        incident.resolved_at = None
        incident.mttr_seconds = None
    incident.last_seen_at = now
    incident.metadata_json = {
        **(incident.metadata_json or {}),
        "error_group_id": str(error_group.id),
        "status_code": error_group.status_code,
        "endpoint": error_group.endpoint,
        "tab_key": error_group.tab_key,
        "request_id": error_group.last_request_id,
    }
    incident.save()
    return incident


def get_ops_actions_catalog() -> list[dict[str, Any]]:
    return [
        {
            "key": "requeue_video_pipeline",
            "label": "Requeue Video Pipeline",
            "description": "Re-run validation/transcode/thumbnail/transcript for a failed video asset.",
            "risk": "high",
            "requires_approval": True,
            "required_target_keys": ["content_id"],
        },
        {
            "key": "regenerate_transcript",
            "label": "Regenerate Transcript",
            "description": "Re-run transcript generation for a video content item.",
            "risk": "medium",
            "requires_approval": False,
            "required_target_keys": ["content_id"],
        },
        {
            "key": "refresh_signed_media_urls",
            "label": "Refresh Signed Media URLs",
            "description": "Refresh signed media URLs or clear stale URL caches.",
            "risk": "low",
            "requires_approval": False,
            "required_target_keys": [],
        },
        {
            "key": "replay_course_publish",
            "label": "Replay Course Publish",
            "description": "Re-run publish transition for a blocked course draft.",
            "risk": "high",
            "requires_approval": True,
            "required_target_keys": ["course_id"],
        },
        {
            "key": "resync_course_assignments",
            "label": "Resync Course Assignments",
            "description": "Re-evaluate teacher assignment visibility for a course.",
            "risk": "medium",
            "requires_approval": False,
            "required_target_keys": ["course_id"],
        },
        {
            "key": "retry_reminder_dispatch",
            "label": "Retry Reminder Dispatch",
            "description": "Trigger reminder automation/dispatch retry for the tenant.",
            "risk": "medium",
            "requires_approval": False,
            "required_target_keys": [],
        },
        {
            "key": "recompute_tenant_analytics",
            "label": "Recompute Tenant Analytics",
            "description": "Warm and recompute tenant analytics snapshots used by dashboards.",
            "risk": "low",
            "requires_approval": False,
            "required_target_keys": [],
        },
        {
            "key": "toggle_tenant_maintenance",
            "label": "Toggle Tenant Maintenance",
            "description": "Enable or disable tenant maintenance mode with a reason and optional end time.",
            "risk": "high",
            "requires_approval": True,
            "required_target_keys": ["enabled"],
        },
        {
            "key": "clear_tenant_cache_scope",
            "label": "Clear Tenant Cache Scope",
            "description": "Clear cache entries for the tenant scope to unblock stale UI state.",
            "risk": "high",
            "requires_approval": True,
            "required_target_keys": [],
        },
    ]


def _catalog_entry(action_key: str) -> dict[str, Any] | None:
    for action in get_ops_actions_catalog():
        if action["key"] == action_key:
            return action
    return None


def _validate_action_target(action_key: str, target: dict[str, Any]) -> tuple[bool, str]:
    action = _catalog_entry(action_key)
    if not action:
        return False, "Unknown action key."
    required = action.get("required_target_keys", [])
    for key in required:
        if target.get(key) in (None, ""):
            return False, f"Missing target.{key}"
    return True, ""


def _action_requeue_video_pipeline(tenant: Tenant, target: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    content_id = target.get("content_id")
    content = Content.objects.filter(id=content_id, module__course__tenant=tenant).select_related("video_asset").first()
    if not content or not hasattr(content, "video_asset"):
        raise ValueError("Video content not found for tenant.")

    asset = content.video_asset
    if dry_run:
        return {"video_asset_id": str(asset.id), "status_before": asset.status, "queued": False}

    from celery import chain
    from apps.courses.tasks import (
        finalize_video_asset,
        generate_assignments,
        generate_thumbnail,
        transcode_to_hls,
        transcribe_video,
        validate_duration,
    )

    chain(
        validate_duration.s(str(asset.id)),
        transcode_to_hls.s(),
        generate_thumbnail.s(),
        finalize_video_asset.s(),
    ).apply_async(link=transcribe_video.si(str(asset.id), "en"))
    generate_assignments.delay(str(asset.id))
    return {"video_asset_id": str(asset.id), "status_before": asset.status, "queued": True}


def _action_regenerate_transcript(tenant: Tenant, target: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    content_id = target.get("content_id")
    content = Content.objects.filter(id=content_id, module__course__tenant=tenant).select_related("video_asset").first()
    if not content or not hasattr(content, "video_asset"):
        raise ValueError("Video content not found for tenant.")
    asset = content.video_asset
    if dry_run:
        return {"video_asset_id": str(asset.id), "queued": False}
    from apps.courses.tasks import transcribe_video

    transcribe_video.delay(str(asset.id), "en")
    return {"video_asset_id": str(asset.id), "queued": True}


def _action_refresh_signed_media_urls(_tenant: Tenant, _target: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    return {"cache_cleared": False, "dry_run": dry_run, "note": "Signed URLs are generated on demand."}


def _action_replay_course_publish(tenant: Tenant, target: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    course_id = target.get("course_id")
    course = Course.objects.filter(id=course_id, tenant=tenant).first()
    if not course:
        raise ValueError("Course not found for tenant.")
    if dry_run:
        return {"course_id": str(course.id), "was_published": course.is_published, "updated": False}

    if not course.is_published:
        course.is_published = True
        course.save(update_fields=["is_published", "updated_at"])
    return {"course_id": str(course.id), "is_published": course.is_published, "updated": True}


def _action_resync_course_assignments(tenant: Tenant, target: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    course_id = target.get("course_id")
    course = Course.objects.filter(id=course_id, tenant=tenant).first()
    if not course:
        raise ValueError("Course not found for tenant.")

    teacher_count = (
        User.objects.filter(tenant=tenant, role__in=["TEACHER", "HOD", "IB_COORDINATOR"], is_active=True).count()
        if course.assigned_to_all
        else User.objects.filter(
            Q(assigned_courses=course) | Q(teacher_groups__in=course.assigned_groups.all()),
            tenant=tenant,
            role__in=["TEACHER", "HOD", "IB_COORDINATOR"],
            is_active=True,
        )
        .distinct()
        .count()
    )
    return {"course_id": str(course.id), "affected_teachers": teacher_count, "dry_run": dry_run}


def _action_retry_reminder_dispatch(tenant: Tenant, _target: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"queued": False, "note": "Would trigger automated course deadline reminder run."}
    from apps.reminders.tasks import send_automated_course_deadline_reminders

    send_automated_course_deadline_reminders.delay()
    return {"queued": True}


def _action_recompute_tenant_analytics(tenant: Tenant, _target: dict[str, Any], _dry_run: bool) -> dict[str, Any]:
    analytics = TenantService.get_tenant_analytics(tenant, months=6)
    stats = TenantService.get_tenant_stats(tenant)
    return {
        "analytics_keys": sorted(list(analytics.keys())),
        "stats_keys": sorted(list(stats.keys())),
    }


def _action_toggle_tenant_maintenance(tenant: Tenant, target: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    enabled = bool(target.get("enabled", False))
    reason = str(target.get("reason", "")).strip() or "Ops Center action"
    ends_at = None
    if enabled:
        ends_at = _now() + timedelta(hours=3)
    if dry_run:
        return {"enabled": enabled, "reason": reason, "ends_at": ends_at.isoformat() if ends_at else None, "updated": False}
    apply_tenant_maintenance(tenant=tenant, enabled=enabled, reason=reason, ends_at=ends_at, actor=None, request=None)
    return {"enabled": tenant.maintenance_mode_enabled, "reason": tenant.maintenance_mode_reason, "updated": True}


def _action_clear_tenant_cache_scope(tenant: Tenant, _target: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"cleared": False, "scope": f"tenant:{tenant.id}", "method": "dry-run"}
    try:
        if hasattr(cache, "delete_pattern"):
            cache.delete_pattern(f"*{tenant.id}*")
            return {"cleared": True, "scope": f"tenant:{tenant.id}", "method": "delete_pattern"}
        cache.clear()
        return {"cleared": True, "scope": "global-cache-clear", "method": "clear"}
    except Exception as exc:
        return {"cleared": False, "error": str(exc)}


ACTION_EXECUTORS: dict[str, Callable[[Tenant, dict[str, Any], bool], dict[str, Any]]] = {
    "requeue_video_pipeline": _action_requeue_video_pipeline,
    "regenerate_transcript": _action_regenerate_transcript,
    "refresh_signed_media_urls": _action_refresh_signed_media_urls,
    "replay_course_publish": _action_replay_course_publish,
    "resync_course_assignments": _action_resync_course_assignments,
    "retry_reminder_dispatch": _action_retry_reminder_dispatch,
    "recompute_tenant_analytics": _action_recompute_tenant_analytics,
    "toggle_tenant_maintenance": _action_toggle_tenant_maintenance,
    "clear_tenant_cache_scope": _action_clear_tenant_cache_scope,
}


def execute_guarded_action(
    *,
    tenant: Tenant,
    action_key: str,
    target: dict[str, Any],
    reason: str,
    dry_run: bool,
    actor: User | None,
) -> dict[str, Any]:
    is_valid, validation_error = _validate_action_target(action_key, target)
    if not is_valid:
        raise ValueError(validation_error)

    action = _catalog_entry(action_key)
    if not action:
        raise ValueError("Unknown action.")

    requires_approval = bool(action.get("requires_approval", False)) and not dry_run
    action_log = OpsActionLog.objects.create(
        actor=actor,
        action=f"OPS_ACTION_{action_key.upper()}",
        target_type="Tenant",
        target_id=str(tenant.id),
        reason=reason[:1000],
        details_json={
            "tenant_id": str(tenant.id),
            "action_key": action_key,
            "target": target,
            "dry_run": dry_run,
            "status": "PENDING_APPROVAL" if requires_approval else "EXECUTING",
        },
    )

    if requires_approval:
        approval = OpsActionApproval.objects.create(
            action_log=action_log,
            requested_by=actor,
            approval_status="PENDING",
            approval_note="Awaiting explicit approval from super admin.",
        )
        return {
            "requires_approval": True,
            "action_log_id": str(action_log.id),
            "approval_id": str(approval.id),
            "status": approval.approval_status,
        }

    executor = ACTION_EXECUTORS[action_key]
    result = executor(tenant, target, dry_run)
    action_log.details_json = {
        **(action_log.details_json or {}),
        "status": "EXECUTED",
        "result": result,
    }
    action_log.save(update_fields=["details_json"])
    OpsActionApproval.objects.create(
        action_log=action_log,
        requested_by=actor,
        approved_by=actor,
        approval_status="AUTO_APPROVED",
        approval_note="Auto-approved (safe action or dry run).",
    )
    return {
        "requires_approval": False,
        "action_log_id": str(action_log.id),
        "status": "EXECUTED",
        "result": result,
    }


def approve_guarded_action(
    *,
    action_log: OpsActionLog,
    approved_by: User,
    approval_note: str,
) -> dict[str, Any]:
    approval = getattr(action_log, "approval", None)
    if not approval or approval.approval_status != "PENDING":
        raise ValueError("No pending approval found for this action.")

    details = action_log.details_json or {}
    action_key = details.get("action_key")
    tenant_id = details.get("tenant_id")
    target = details.get("target") or {}
    dry_run = bool(details.get("dry_run", False))
    tenant = Tenant.objects.filter(id=tenant_id, is_active=True).first()
    if not tenant:
        raise ValueError("Tenant not found.")
    if action_key not in ACTION_EXECUTORS:
        raise ValueError("Unsupported action.")

    executor = ACTION_EXECUTORS[action_key]
    result = executor(tenant, target, dry_run)
    details["status"] = "EXECUTED"
    details["result"] = result
    action_log.details_json = details
    action_log.save(update_fields=["details_json"])

    approval.approval_status = "APPROVED"
    approval.approved_by = approved_by
    approval.approval_note = str(approval_note or "")[:2000]
    approval.save(update_fields=["approval_status", "approved_by", "approval_note", "updated_at"])

    return {"action_log_id": str(action_log.id), "status": "EXECUTED", "result": result}


def cleanup_ops_data(now: datetime | None = None) -> dict[str, int]:
    now = now or _now()
    cutoff = now - timedelta(days=OPS_RETENTION_DAYS)

    deleted_events, _ = OpsEvent.objects.filter(event_ts__lt=cutoff).delete()
    deleted_dead, _ = OpsDeadLetter.objects.filter(received_at__lt=cutoff).delete()

    return {"deleted_events": deleted_events, "deleted_dead_letters": deleted_dead}


def weekly_report_csv(week_start: datetime) -> str:
    week_end = week_start + timedelta(days=7)

    rows = []
    tenants = list(Tenant.objects.filter(is_active=True).values("id", "name", "subdomain"))

    fail_counts = (
        OpsEvent.objects.filter(status="FAIL", event_ts__gte=week_start, event_ts__lt=week_end)
        .values("tenant_id", "category")
        .annotate(c=Count("id"))
    )
    fail_map: dict[tuple[str, str], int] = {
        (str(r["tenant_id"]), r["category"]): r["c"] for r in fail_counts if r["tenant_id"]
    }

    for t in tenants:
        tid = str(t["id"])
        tenant_incidents = OpsIncident.objects.filter(
            tenant_id=t["id"],
            scope="TENANT",
            resolved_at__gte=week_start,
            resolved_at__lt=week_end,
            mttr_seconds__isnull=False,
        )
        p1_mttr = tenant_incidents.filter(severity="P1").values_list("mttr_seconds", flat=True)
        p2_mttr = tenant_incidents.filter(severity="P2").values_list("mttr_seconds", flat=True)

        rows.append(
            {
                "tenant_name": t["name"],
                "subdomain": t["subdomain"],
                "availability_probe_failures": fail_map.get((tid, "availability_probe"), 0),
                "auth_probe_failures": fail_map.get((tid, "auth_probe"), 0),
                "background_job_failures": fail_map.get((tid, "background_jobs"), 0),
                "deliverability_failures": fail_map.get((tid, "deliverability"), 0),
                "webhook_failures": fail_map.get((tid, "webhook_delivery"), 0),
                "harness_external_failures": fail_map.get((tid, "harness_external"), 0),
                "p1_mttr_seconds_avg": int(sum(p1_mttr) / len(p1_mttr)) if p1_mttr else "",
                "p2_mttr_seconds_avg": int(sum(p2_mttr) / len(p2_mttr)) if p2_mttr else "",
            }
        )

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "tenant_name",
            "subdomain",
            "availability_probe_failures",
            "auth_probe_failures",
            "background_job_failures",
            "deliverability_failures",
            "webhook_failures",
            "harness_external_failures",
            "p1_mttr_seconds_avg",
            "p2_mttr_seconds_avg",
        ],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

    return output.getvalue()
