from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.tenants.models import Tenant
from utils.decorators import super_admin_only

from .models import (
    MaintenanceSchedule,
    OpsActionLog,
    OpsEvent,
    OpsHealthSnapshot,
    OpsIncident,
    OpsReplayRun,
    OpsReplayStep,
    OpsRouteError,
)
from .replay import execute_replay_run, get_replay_case_catalog
from .services import (
    P1_MTTR_TARGET_MINUTES,
    P2_MTTR_TARGET_MINUTES,
    approve_guarded_action,
    apply_bulk_action,
    apply_tenant_maintenance,
    execute_guarded_action,
    get_ops_actions_catalog,
    get_pipeline_health,
    ingest_harness_event,
    lock_route_error_group,
    record_route_error,
    run_maintenance_scheduler,
    verify_harness_signature,
    weekly_report_csv,
)


class OpsTenantPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


def _parse_iso_dt(value: str | None, default: datetime) -> datetime:
    if not value:
        return default
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return default
    if timezone.is_naive(dt):
        return timezone.make_aware(dt)
    return dt


def _parse_bool(value, default=False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _serialize_route_error(error: OpsRouteError) -> dict:
    return {
        "id": str(error.id),
        "tenant_id": str(error.tenant_id) if error.tenant_id else None,
        "tenant_name": error.tenant.name if error.tenant_id else None,
        "portal": error.portal,
        "tab_key": error.tab_key,
        "route_path": error.route_path,
        "component_name": error.component_name,
        "endpoint": error.endpoint,
        "method": error.method,
        "status_code": error.status_code,
        "fingerprint": error.fingerprint,
        "first_seen_at": error.first_seen_at.isoformat(),
        "last_seen_at": error.last_seen_at.isoformat(),
        "last_request_id": error.last_request_id,
        "total_count": error.total_count,
        "count_1h": error.count_1h,
        "count_24h": error.count_24h,
        "sample_payload": error.sample_payload_json,
        "sample_response_excerpt": error.sample_response_excerpt,
        "sample_error_message": error.sample_error_message,
        "is_locked": error.is_locked,
        "locked_at": error.locked_at.isoformat() if error.locked_at else None,
        "locked_by": error.locked_by.email if error.locked_by_id else None,
    }


def _serialize_replay_run(run: OpsReplayRun) -> dict:
    return {
        "id": str(run.id),
        "tenant_id": str(run.tenant_id),
        "tenant_name": run.tenant.name,
        "portal": run.portal,
        "status": run.status,
        "priority": run.priority,
        "dry_run": run.dry_run,
        "requested_cases": run.requested_cases_json,
        "summary": run.summary_json,
        "incident_links": run.incident_links_json,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
        "created_at": run.created_at.isoformat(),
        "actor_email": run.actor.email if run.actor_id else None,
    }


def _serialize_replay_step(step: OpsReplayStep) -> dict:
    return {
        "id": str(step.id),
        "run_id": str(step.run_id),
        "case_id": step.case_id,
        "case_label": step.case_label,
        "endpoint": step.endpoint,
        "method": step.method,
        "request_payload": step.request_payload_json,
        "response_status": step.response_status,
        "response_excerpt": step.response_excerpt,
        "latency_ms": step.latency_ms,
        "pass_fail": step.pass_fail,
        "error_group_id": str(step.error_group_id) if step.error_group_id else None,
        "created_at": step.created_at.isoformat(),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@super_admin_only
def ops_overview(request):
    health = get_pipeline_health()

    total = Tenant.objects.filter(is_active=True).count()
    status_counts = {k: 0 for k in ["HEALTHY", "DEGRADED", "DOWN", "MAINTENANCE"]}
    for row in (
        OpsHealthSnapshot.objects.filter(tenant__is_active=True)
        .values("current_status")
        .annotate(count=Count("tenant_id"))
    ):
        status_counts[row["current_status"]] = row["count"]

    known = sum(status_counts.values())
    if total > known:
        status_counts["DEGRADED"] += total - known

    incidents_qs = (
        OpsIncident.objects.filter(status__in=["OPEN", "ACKED"])
        .select_related("tenant", "owner")
        .order_by("-started_at")[:10]
    )
    open_incidents = [
        {
            "id": str(i.id),
            "severity": i.severity,
            "status": i.status,
            "title": i.title,
            "started_at": i.started_at.isoformat(),
            "tenant_id": str(i.tenant_id) if i.tenant_id else None,
            "tenant_name": i.tenant.name if i.tenant_id else None,
            "owner_email": i.owner.email if i.owner_id else None,
            "scope": i.scope,
        }
        for i in incidents_qs
    ]

    last_24h = timezone.now() - timedelta(hours=24)
    top_categories_sorted = list(
        OpsEvent.objects.filter(status="FAIL", event_ts__gte=last_24h)
        .values("category")
        .annotate(count=Count("id"))
        .order_by("-count")[:8]
    )

    return Response(
        {
            **health,
            "refresh_seconds": 10,
            "totals": {
                "tenants": total,
                "healthy": status_counts.get("HEALTHY", 0),
                "degraded": status_counts.get("DEGRADED", 0),
                "down": status_counts.get("DOWN", 0),
                "maintenance": status_counts.get("MAINTENANCE", 0),
            },
            "mttr_targets": {
                "p1_minutes": P1_MTTR_TARGET_MINUTES,
                "p2_minutes": P2_MTTR_TARGET_MINUTES,
            },
            "open_incidents": open_incidents,
            "top_failure_categories": top_categories_sorted,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@super_admin_only
def ops_tenants(request):
    health = get_pipeline_health()
    status_filter = request.GET.get("status")
    category_filter = request.GET.get("category")
    search = request.GET.get("search")

    tenants_qs = Tenant.objects.filter(is_active=True).order_by("name")
    if search:
        tenants_qs = tenants_qs.filter(name__icontains=search)

    tenants = list(tenants_qs)
    tenant_ids = [t.id for t in tenants]
    snapshots = {s.tenant_id: s for s in OpsHealthSnapshot.objects.filter(tenant_id__in=tenant_ids)}

    week_start = timezone.now() - timedelta(days=7)
    day_start = timezone.now() - timedelta(hours=24)

    week_counts_rows = (
        OpsEvent.objects.filter(tenant_id__in=tenant_ids, status="FAIL", event_ts__gte=week_start)
        .values("tenant_id", "category")
        .annotate(count=Count("id"))
    )
    day_counts_rows = (
        OpsEvent.objects.filter(tenant_id__in=tenant_ids, status="FAIL", event_ts__gte=day_start)
        .values("tenant_id", "category")
        .annotate(count=Count("id"))
    )

    week_counts: dict[tuple[str, str], int] = {
        (str(row["tenant_id"]), row["category"]): row["count"] for row in week_counts_rows
    }
    day_counts: dict[tuple[str, str], int] = {
        (str(row["tenant_id"]), row["category"]): row["count"] for row in day_counts_rows
    }

    categories = [
        "availability_probe",
        "auth_probe",
        "background_jobs",
        "deliverability",
        "webhook_delivery",
        "harness_external",
    ]

    rows = []
    for tenant in tenants:
        snap = snapshots.get(tenant.id)
        status_value = snap.current_status if snap else "DEGRADED"
        if status_filter and status_value != status_filter:
            continue

        failures_week = {category: week_counts.get((str(tenant.id), category), 0) for category in categories}
        if category_filter and failures_week.get(category_filter, 0) == 0:
            continue

        rows.append(
            {
                "tenant_id": str(tenant.id),
                "name": tenant.name,
                "subdomain": tenant.subdomain,
                "status": status_value,
                "last_check_at": snap.last_probe_at.isoformat() if snap and snap.last_probe_at else None,
                "last_latency_ms": snap.last_latency_ms if snap else None,
                "active_failures_24h": sum(1 for c in categories if day_counts.get((str(tenant.id), c), 0) > 0),
                "failures_week": failures_week,
                "maintenance_mode": tenant.maintenance_mode_enabled,
            }
        )

    paginator = OpsTenantPagination()
    page = paginator.paginate_queryset(rows, request)
    response = paginator.get_paginated_response(page)
    response.data.update(health)
    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@super_admin_only
def ops_tenant_timeline(request, tenant_id):
    tenant = get_object_or_404(Tenant, id=tenant_id)
    health = get_pipeline_health()

    now = timezone.now()
    from_ts = _parse_iso_dt(request.GET.get("from"), now - timedelta(days=7))
    to_ts = _parse_iso_dt(request.GET.get("to"), now)
    if from_ts > to_ts:
        from_ts, to_ts = to_ts, from_ts

    events = OpsEvent.objects.filter(tenant=tenant, event_ts__gte=from_ts, event_ts__lte=to_ts).order_by("event_ts")

    status_series = []
    for event in events.filter(category="availability_probe"):
        status_to = event.payload_json.get("to")
        status_series.append(
            {
                "ts": event.event_ts.isoformat(),
                "status": status_to if status_to else ("HEALTHY" if event.status == "RECOVER" else "DEGRADED"),
                "latency_ms": event.payload_json.get("latency_ms"),
            }
        )

    category_counts = []
    day_cursor = from_ts.date()
    local_tz = timezone.get_current_timezone()
    while day_cursor <= to_ts.date():
        day_start = timezone.make_aware(datetime.combine(day_cursor, datetime.min.time()), local_tz)
        day_end = day_start + timedelta(days=1)
        day_events = (
            OpsEvent.objects.filter(tenant=tenant, status="FAIL", event_ts__gte=day_start, event_ts__lt=day_end)
            .values("category")
            .annotate(count=Count("id"))
        )
        counts = {row["category"]: row["count"] for row in day_events}
        category_counts.append(
            {
                "date": str(day_cursor),
                "availability_probe": counts.get("availability_probe", 0),
                "auth_probe": counts.get("auth_probe", 0),
                "background_jobs": counts.get("background_jobs", 0),
                "deliverability": counts.get("deliverability", 0),
                "webhook_delivery": counts.get("webhook_delivery", 0),
                "harness_external": counts.get("harness_external", 0),
            }
        )
        day_cursor += timedelta(days=1)

    event_rows = [
        {
            "ts": event.event_ts.isoformat(),
            "category": event.category,
            "severity": event.severity,
            "status": event.status,
            "message": event.payload_json.get("message") or event.payload_json.get("error") or "",
            "payload": event.payload_json,
        }
        for event in events.order_by("-event_ts")[:200]
    ]

    return Response(
        {
            **health,
            "tenant_id": str(tenant.id),
            "status_series": status_series,
            "category_counts": category_counts,
            "events": event_rows,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@super_admin_only
def ops_incidents(request):
    health = get_pipeline_health()
    qs = OpsIncident.objects.select_related("tenant", "owner").order_by("-started_at")

    status_filter = request.GET.get("status")
    severity_filter = request.GET.get("severity")
    if status_filter:
        qs = qs.filter(status=status_filter)
    if severity_filter:
        qs = qs.filter(severity=severity_filter)

    items = [
        {
            "id": str(i.id),
            "severity": i.severity,
            "scope": i.scope,
            "status": i.status,
            "rule_id": i.rule_id,
            "title": i.title,
            "description": i.description,
            "tenant_id": str(i.tenant_id) if i.tenant_id else None,
            "tenant_name": i.tenant.name if i.tenant_id else None,
            "owner_email": i.owner.email if i.owner_id else None,
            "started_at": i.started_at.isoformat(),
            "acknowledged_at": i.acknowledged_at.isoformat() if i.acknowledged_at else None,
            "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
            "mttr_seconds": i.mttr_seconds,
            "last_seen_at": i.last_seen_at.isoformat(),
            "metadata": i.metadata_json,
        }
        for i in qs[:200]
    ]

    return Response({**health, "results": items})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@super_admin_only
def ops_incident_acknowledge(request, incident_id):
    incident = get_object_or_404(OpsIncident, id=incident_id)
    if incident.status == "RESOLVED":
        return Response({"error": "Resolved incident cannot be acknowledged"}, status=400)
    incident.status = "ACKED"
    incident.owner = request.user
    incident.acknowledged_at = timezone.now()
    incident.save(update_fields=["status", "owner", "acknowledged_at", "updated_at"])
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@super_admin_only
def ops_incident_resolve(request, incident_id):
    incident = get_object_or_404(OpsIncident, id=incident_id)
    if incident.status == "RESOLVED":
        return Response({"ok": True})

    now = timezone.now()
    incident.status = "RESOLVED"
    incident.owner = request.user if not incident.owner_id else incident.owner
    incident.resolved_at = now
    incident.mttr_seconds = int((incident.resolved_at - incident.started_at).total_seconds())
    incident.save(update_fields=["status", "owner", "resolved_at", "mttr_seconds", "updated_at"])
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@super_admin_only
def ops_replay_cases(request):
    health = get_pipeline_health()
    portal = request.GET.get("portal")
    return Response({**health, "results": get_replay_case_catalog(portal=portal)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@super_admin_only
def ops_replay_runs_create(request):
    tenant_id = request.data.get("tenant_id")
    portal = str(request.data.get("portal", "")).upper().strip()
    requested_cases = request.data.get("cases") or []
    dry_run = _parse_bool(request.data.get("dry_run"), True)
    priority = str(request.data.get("priority", "NORMAL")).upper()
    async_mode = _parse_bool(request.data.get("async"), False)

    if not tenant_id:
        return Response({"error": "tenant_id is required"}, status=400)
    tenant = Tenant.objects.filter(id=tenant_id, is_active=True).first()
    if not tenant:
        return Response({"error": "Tenant not found"}, status=404)
    if portal not in {"TENANT_ADMIN", "TEACHER"}:
        return Response({"error": "portal must be TENANT_ADMIN or TEACHER"}, status=400)
    if not isinstance(requested_cases, list) or not requested_cases:
        return Response({"error": "cases must be a non-empty list"}, status=400)
    if priority not in {"NORMAL", "HIGH"}:
        priority = "NORMAL"

    run = OpsReplayRun.objects.create(
        tenant=tenant,
        portal=portal,
        status="PENDING",
        priority=priority,
        dry_run=dry_run,
        actor=request.user,
        requested_cases_json=requested_cases,
    )
    if async_mode:
        from .tasks import ops_execute_replay_run

        ops_execute_replay_run.delay(str(run.id))
        return Response({**_serialize_replay_run(run), "queued": True}, status=202)

    run = execute_replay_run(run)
    return Response(_serialize_replay_run(run), status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@super_admin_only
def ops_replay_run_detail(request, run_id):
    run = get_object_or_404(OpsReplayRun.objects.select_related("tenant", "actor"), id=run_id)
    return Response(_serialize_replay_run(run))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@super_admin_only
def ops_replay_run_steps(request, run_id):
    run = get_object_or_404(OpsReplayRun, id=run_id)
    steps = OpsReplayStep.objects.filter(run=run).select_related("error_group").order_by("created_at")
    return Response({"run_id": str(run.id), "results": [_serialize_replay_step(step) for step in steps]})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@super_admin_only
def ops_replay_run_cancel(request, run_id):
    run = get_object_or_404(OpsReplayRun, id=run_id)
    if run.status in {"COMPLETED", "FAILED", "CANCELLED"}:
        return Response({"ok": True, "status": run.status})
    run.status = "CANCELLED"
    run.ended_at = timezone.now()
    run.save(update_fields=["status", "ended_at", "updated_at"])
    return Response({"ok": True, "status": run.status})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@super_admin_only
def ops_errors(request):
    health = get_pipeline_health()
    qs = OpsRouteError.objects.select_related("tenant", "locked_by").order_by("-last_seen_at")

    tenant_id = request.GET.get("tenant_id")
    portal = request.GET.get("portal")
    tab = request.GET.get("tab")
    is_locked = request.GET.get("is_locked")
    since = request.GET.get("since")
    until = request.GET.get("until")
    codes = request.GET.get("status_codes")

    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)
    if portal:
        qs = qs.filter(portal=str(portal).upper())
    if tab:
        qs = qs.filter(tab_key=str(tab).lower())
    if is_locked is not None:
        qs = qs.filter(is_locked=_parse_bool(is_locked, False))
    if since:
        qs = qs.filter(last_seen_at__gte=_parse_iso_dt(since, timezone.now() - timedelta(days=7)))
    if until:
        qs = qs.filter(last_seen_at__lte=_parse_iso_dt(until, timezone.now()))
    if codes:
        try:
            parsed_codes = [int(part.strip()) for part in str(codes).split(",") if part.strip()]
            qs = qs.filter(status_code__in=parsed_codes)
        except Exception:
            qs = qs.filter(status_code__in=[429, 500])
    else:
        qs = qs.filter(status_code__in=[429, 500])

    return Response({**health, "results": [_serialize_route_error(row) for row in qs[:200]]})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@super_admin_only
def ops_error_detail(request, error_group_id):
    row = get_object_or_404(OpsRouteError.objects.select_related("tenant", "locked_by"), id=error_group_id)
    recent_steps = OpsReplayStep.objects.filter(error_group=row).select_related("run").order_by("-created_at")[:20]
    return Response(
        {
            "error_group": _serialize_route_error(row),
            "recent_replay_steps": [
                {
                    "id": str(step.id),
                    "run_id": str(step.run_id),
                    "run_status": step.run.status,
                    "case_id": step.case_id,
                    "response_status": step.response_status,
                    "created_at": step.created_at.isoformat(),
                }
                for step in recent_steps
            ],
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@super_admin_only
def ops_error_lock(request, error_group_id):
    row = get_object_or_404(OpsRouteError, id=error_group_id)
    note = str(request.data.get("note", "")).strip()
    incident = lock_route_error_group(error_group=row, actor=request.user, note=note)
    return Response(
        {
            "ok": True,
            "error_group_id": str(row.id),
            "incident_id": str(incident.id),
            "incident_status": incident.status,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@super_admin_only
def ops_actions_catalog(request):
    return Response({"results": get_ops_actions_catalog()})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@super_admin_only
def ops_actions_execute(request):
    tenant_id = request.data.get("tenant_id")
    action_key = str(request.data.get("action_key", "")).strip()
    target = request.data.get("target") or {}
    reason = str(request.data.get("reason", "")).strip()
    dry_run = _parse_bool(request.data.get("dry_run"), True)

    if not tenant_id:
        return Response({"error": "tenant_id is required"}, status=400)
    tenant = Tenant.objects.filter(id=tenant_id, is_active=True).first()
    if not tenant:
        return Response({"error": "Tenant not found"}, status=404)
    if not isinstance(target, dict):
        return Response({"error": "target must be an object"}, status=400)

    try:
        result = execute_guarded_action(
            tenant=tenant,
            action_key=action_key,
            target=target,
            reason=reason,
            dry_run=dry_run,
            actor=request.user,
        )
    except ValueError as exc:
        return Response({"error": str(exc)}, status=400)
    return Response(result, status=202 if result.get("requires_approval") else 200)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@super_admin_only
def ops_action_approve(request, action_id):
    action_log = get_object_or_404(OpsActionLog, id=action_id)
    approval_note = str(request.data.get("approval_note", "")).strip()
    try:
        result = approve_guarded_action(action_log=action_log, approved_by=request.user, approval_note=approval_note)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=400)
    return Response(result)


@api_view(["POST"])
@permission_classes([AllowAny])
def ops_client_error_ingest(request):
    payload = request.data if isinstance(request.data, dict) else {}
    status_code = int(payload.get("status_code") or 0)
    if status_code not in {429, 500}:
        return Response({"accepted": False, "reason": "status_not_tracked"}, status=202)

    observed_at = _parse_iso_dt(payload.get("observed_at"), timezone.now())
    row = record_route_error(
        tenant=getattr(request, "tenant", None),
        portal=str(payload.get("portal", "")).upper() or "UNKNOWN",
        tab_key=str(payload.get("tab_key") or payload.get("tab") or "").lower(),
        route_path=str(payload.get("route_path", "")),
        component_name=str(payload.get("component_name", "")),
        endpoint=str(payload.get("endpoint", "")),
        method=str(payload.get("method", "GET")).upper(),
        status_code=status_code,
        request_id=str(payload.get("request_id", "")),
        payload=payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
        response_excerpt=str(payload.get("response_excerpt", "")),
        error_message=str(payload.get("error_message", "")),
        observed_at=observed_at,
    )
    return Response({"accepted": True, "error_group_id": str(row.id) if row else None})


@api_view(["POST"])
@permission_classes([AllowAny])
def ops_proxy_errors_ingest(request):
    signature = request.headers.get("X-Harness-Signature", "")
    if not verify_harness_signature(request.body, signature):
        return Response({"error": "Invalid signature"}, status=status.HTTP_401_UNAUTHORIZED)

    payload = request.data if isinstance(request.data, dict) else {}
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    ingested = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        status_code = int(row.get("status_code") or 0)
        if status_code not in {429, 500}:
            continue

        tenant = None
        tenant_id = row.get("tenant_id")
        subdomain = row.get("tenant_subdomain")
        if tenant_id:
            tenant = Tenant.objects.filter(id=tenant_id).first()
        if not tenant and subdomain:
            tenant = Tenant.objects.filter(subdomain=subdomain).first()

        recorded = record_route_error(
            tenant=tenant,
            portal=str(row.get("portal") or "UNKNOWN"),
            tab_key=str(row.get("tab_key") or ""),
            route_path=str(row.get("route_path") or ""),
            component_name=str(row.get("component_name") or "proxy"),
            endpoint=str(row.get("endpoint") or "/"),
            method=str(row.get("method") or "GET"),
            status_code=status_code,
            request_id=str(row.get("request_id") or ""),
            payload=row if isinstance(row, dict) else {},
            response_excerpt=str(row.get("response_excerpt") or ""),
            error_message=str(row.get("error_message") or ""),
            observed_at=_parse_iso_dt(row.get("observed_at"), timezone.now()),
        )
        if recorded:
            ingested += 1
    return Response({"accepted": True, "ingested": ingested})


@api_view(["POST"])
@permission_classes([AllowAny])
def ops_harness_ingest(request):
    signature = request.headers.get("X-Harness-Signature", "")
    if not verify_harness_signature(request.body, signature):
        return Response({"error": "Invalid signature"}, status=status.HTTP_401_UNAUTHORIZED)

    payload = request.data if isinstance(request.data, dict) else {}
    ok, event_id_or_reason = ingest_harness_event(payload)
    if not ok:
        return Response({"accepted": False, "reason": event_id_or_reason}, status=400)

    return Response({"accepted": True, "event_id": event_id_or_reason})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@super_admin_only
def ops_weekly_report_csv(request):
    week_start_raw = request.GET.get("week_start")
    if week_start_raw:
        week_start = _parse_iso_dt(week_start_raw, timezone.now())
    else:
        now = timezone.now()
        week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)

    csv_text = weekly_report_csv(week_start)
    response = HttpResponse(csv_text, content_type="text/csv")
    response["Content-Disposition"] = f"attachment; filename=ops-weekly-{week_start.date()}.csv"
    return response


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@super_admin_only
def ops_tenant_maintenance(request, tenant_id):
    tenant = get_object_or_404(Tenant, id=tenant_id)
    enabled = bool(request.data.get("enabled", False))
    reason = str(request.data.get("reason", "")).strip()

    ends_at = None
    if enabled:
        ends_at = _parse_iso_dt(request.data.get("ends_at"), timezone.now() + timedelta(hours=3))

    apply_tenant_maintenance(
        tenant=tenant,
        enabled=enabled,
        reason=reason,
        ends_at=ends_at,
        actor=request.user,
        request=request,
    )

    return Response(
        {
            "tenant_id": str(tenant.id),
            "maintenance_mode_enabled": tenant.maintenance_mode_enabled,
            "maintenance_mode_reason": tenant.maintenance_mode_reason,
            "maintenance_mode_ends_at": tenant.maintenance_mode_ends_at.isoformat()
            if tenant.maintenance_mode_ends_at
            else None,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@super_admin_only
def ops_maintenance_schedule_monthly_weekend(request):
    enabled = bool(request.data.get("enabled", True))
    week_of_month = int(request.data.get("week_of_month", 1))
    day = str(request.data.get("day", "SUNDAY")).upper()
    start_time_raw = str(request.data.get("start_time", "01:00"))
    duration_minutes = int(request.data.get("duration_minutes", 180))
    tz = str(request.data.get("timezone", getattr(settings, "TIME_ZONE", "Asia/Kolkata")))

    if week_of_month < 1 or week_of_month > 5:
        return Response({"error": "week_of_month must be between 1 and 5"}, status=400)
    if day not in {"SATURDAY", "SUNDAY"}:
        return Response({"error": "day must be SATURDAY or SUNDAY"}, status=400)

    try:
        parsed_time = datetime.strptime(start_time_raw, "%H:%M").time()
    except ValueError:
        return Response({"error": "start_time must be HH:MM"}, status=400)

    schedule, _ = MaintenanceSchedule.objects.get_or_create(id=1)
    schedule.enabled = enabled
    schedule.week_of_month = week_of_month
    schedule.day = day
    schedule.start_time = parsed_time
    schedule.duration_minutes = duration_minutes
    schedule.timezone = tz
    schedule.updated_by = request.user
    if not schedule.created_by_id:
        schedule.created_by = request.user
    schedule.save()

    run_info = run_maintenance_scheduler()
    return Response(
        {
            "enabled": schedule.enabled,
            "week_of_month": schedule.week_of_month,
            "day": schedule.day,
            "start_time": schedule.start_time.strftime("%H:%M"),
            "duration_minutes": schedule.duration_minutes,
            "timezone": schedule.timezone,
            "runtime": run_info,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@super_admin_only
def ops_bulk_action(request):
    action = str(request.data.get("action", "")).upper()
    tenant_ids = request.data.get("tenant_ids") or []
    reason = str(request.data.get("reason", "")).strip()
    confirm_text = str(request.data.get("confirm_text", ""))

    if action not in {"ENABLE_MAINTENANCE", "DISABLE_MAINTENANCE", "ACTIVATE_TENANT", "DEACTIVATE_TENANT"}:
        return Response({"error": "Invalid action"}, status=400)
    if not isinstance(tenant_ids, list) or not tenant_ids:
        return Response({"error": "tenant_ids must be a non-empty list"}, status=400)

    expected_confirm = f"{action} {len(tenant_ids)}"
    if confirm_text != expected_confirm:
        return Response({"error": "Invalid confirm_text", "expected": expected_confirm}, status=400)

    result = apply_bulk_action(
        action=action,
        tenant_ids=tenant_ids,
        reason=reason,
        actor=request.user,
        request=request,
    )
    return Response({"ok": True, **result})
