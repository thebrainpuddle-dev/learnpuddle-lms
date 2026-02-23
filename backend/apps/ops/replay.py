from __future__ import annotations

import json
import time
from typing import Any

from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.courses.models import Course
from apps.progress.models import Assignment
from apps.tenants.models import Tenant
from apps.users.models import User

from .models import OpsReplayRun, OpsReplayStep


REPLAY_CASES: dict[str, dict[str, Any]] = {
    # Tenant admin
    "tenant_admin.dashboard_stats": {
        "label": "Tenant Dashboard Stats",
        "portal": "TENANT_ADMIN",
        "tab": "dashboard",
        "method": "GET",
        "endpoint": "/api/tenants/stats/",
    },
    "tenant_admin.dashboard_analytics": {
        "label": "Tenant Analytics",
        "portal": "TENANT_ADMIN",
        "tab": "dashboard",
        "method": "GET",
        "endpoint": "/api/tenants/analytics/",
        "query_defaults": {"months": 6},
    },
    "tenant_admin.courses_list": {
        "label": "Course List",
        "portal": "TENANT_ADMIN",
        "tab": "courses",
        "method": "GET",
        "endpoint": "/api/courses/",
    },
    "tenant_admin.courses_create": {
        "label": "Create Course",
        "portal": "TENANT_ADMIN",
        "tab": "course_editor",
        "method": "POST",
        "endpoint": "/api/courses/",
        "payload_defaults": {
            "title": "Ops Replay Course",
            "description": "Created by Operations Replay",
            "estimated_hours": 2,
            "is_mandatory": False,
        },
    },
    "tenant_admin.module_create": {
        "label": "Create Module",
        "portal": "TENANT_ADMIN",
        "tab": "course_editor",
        "method": "POST",
        "endpoint": "/api/courses/{course_id}/modules/",
        "payload_defaults": {"title": "Ops Replay Module", "description": "Ops replay module", "order": 1},
    },
    "tenant_admin.assignments_list": {
        "label": "Assignment List",
        "portal": "TENANT_ADMIN",
        "tab": "assignments",
        "method": "GET",
        "endpoint": "/api/courses/{course_id}/assignments/",
    },
    "tenant_admin.assignment_ai_generate": {
        "label": "AI Generate Assignment",
        "portal": "TENANT_ADMIN",
        "tab": "assignments",
        "method": "POST",
        "endpoint": "/api/courses/{course_id}/assignments/ai-generate/",
        "payload_defaults": {
            "scope_type": "COURSE",
            "question_count": 6,
            "include_short_answer": True,
            "title_hint": "Ops replay quiz",
        },
    },
    "tenant_admin.media_list": {
        "label": "Media Library",
        "portal": "TENANT_ADMIN",
        "tab": "media",
        "method": "GET",
        "endpoint": "/api/media/",
    },
    "tenant_admin.teachers_list": {
        "label": "Teacher List",
        "portal": "TENANT_ADMIN",
        "tab": "teachers",
        "method": "GET",
        "endpoint": "/api/teachers/",
    },
    "tenant_admin.groups_list": {
        "label": "Group List",
        "portal": "TENANT_ADMIN",
        "tab": "groups",
        "method": "GET",
        "endpoint": "/api/teacher-groups/",
    },
    "tenant_admin.reminders_list": {
        "label": "Reminders List",
        "portal": "TENANT_ADMIN",
        "tab": "reminders",
        "method": "GET",
        "endpoint": "/api/reminders/",
    },
    "tenant_admin.announcements_list": {
        "label": "Announcements List",
        "portal": "TENANT_ADMIN",
        "tab": "announcements",
        "method": "GET",
        "endpoint": "/api/notifications/announcements/",
    },
    "tenant_admin.reports_course_progress": {
        "label": "Course Progress Report",
        "portal": "TENANT_ADMIN",
        "tab": "reports",
        "method": "GET",
        "endpoint": "/api/reports/course-progress/",
        "query_defaults": {},
    },
    "tenant_admin.settings_get": {
        "label": "Tenant Settings",
        "portal": "TENANT_ADMIN",
        "tab": "settings",
        "method": "GET",
        "endpoint": "/api/tenants/settings/",
    },
    # Teacher
    "teacher.dashboard": {
        "label": "Teacher Dashboard",
        "portal": "TEACHER",
        "tab": "dashboard",
        "method": "GET",
        "endpoint": "/api/teacher/dashboard/",
    },
    "teacher.calendar": {
        "label": "Teacher Calendar",
        "portal": "TEACHER",
        "tab": "dashboard",
        "method": "GET",
        "endpoint": "/api/teacher/calendar/",
        "query_defaults": {"days": 5},
    },
    "teacher.courses_list": {
        "label": "My Courses",
        "portal": "TEACHER",
        "tab": "courses",
        "method": "GET",
        "endpoint": "/api/teacher/courses/",
    },
    "teacher.course_detail": {
        "label": "Course Detail",
        "portal": "TEACHER",
        "tab": "courses",
        "method": "GET",
        "endpoint": "/api/teacher/courses/{course_id}/",
    },
    "teacher.assignments_list": {
        "label": "Assignments",
        "portal": "TEACHER",
        "tab": "assignments",
        "method": "GET",
        "endpoint": "/api/teacher/assignments/",
    },
    "teacher.quiz_detail": {
        "label": "Quiz Detail",
        "portal": "TEACHER",
        "tab": "quiz",
        "method": "GET",
        "endpoint": "/api/teacher/quizzes/{assignment_id}/",
    },
    "teacher.gamification_summary": {
        "label": "Gamification Summary",
        "portal": "TEACHER",
        "tab": "profile",
        "method": "GET",
        "endpoint": "/api/teacher/gamification/summary/",
    },
    "teacher.notifications": {
        "label": "Notifications",
        "portal": "TEACHER",
        "tab": "notifications",
        "method": "GET",
        "endpoint": "/api/notifications/",
    },
}


def get_replay_case_catalog(portal: str | None = None) -> list[dict[str, Any]]:
    portal_value = str(portal or "").upper().strip()
    rows: list[dict[str, Any]] = []
    for case_id, cfg in sorted(REPLAY_CASES.items()):
        if portal_value and cfg["portal"] != portal_value:
            continue
        rows.append(
            {
                "case_id": case_id,
                "label": cfg["label"],
                "portal": cfg["portal"],
                "tab": cfg["tab"],
                "method": cfg["method"],
                "endpoint": cfg["endpoint"],
                "supports_params": "{course_id}" in cfg["endpoint"] or "{assignment_id}" in cfg["endpoint"],
                "payload_defaults": cfg.get("payload_defaults", {}),
                "query_defaults": cfg.get("query_defaults", {}),
            }
        )
    return rows


def _pick_portal_user(tenant: Tenant, portal: str) -> User | None:
    if portal == "TENANT_ADMIN":
        return User.objects.filter(tenant=tenant, role="SCHOOL_ADMIN", is_active=True).order_by("created_at").first()
    if portal == "TEACHER":
        return User.objects.filter(
            tenant=tenant,
            role__in=["TEACHER", "HOD", "IB_COORDINATOR"],
            is_active=True,
        ).order_by("created_at").first()
    return None


def _pick_course_id(tenant: Tenant) -> str | None:
    course = Course.objects.filter(tenant=tenant, is_active=True).order_by("created_at").first()
    return str(course.id) if course else None


def _pick_assignment_id(tenant: Tenant) -> str | None:
    assignment = (
        Assignment.objects.filter(course__tenant=tenant, is_active=True)
        .order_by("created_at")
        .first()
    )
    return str(assignment.id) if assignment else None


def _resolve_endpoint(raw_endpoint: str, tenant: Tenant, params: dict[str, Any]) -> tuple[str | None, str | None]:
    endpoint = raw_endpoint
    if "{course_id}" in endpoint:
        course_id = str(params.get("course_id") or _pick_course_id(tenant) or "")
        if not course_id:
            return None, "Missing course_id"
        endpoint = endpoint.replace("{course_id}", course_id)
    if "{assignment_id}" in endpoint:
        assignment_id = str(params.get("assignment_id") or _pick_assignment_id(tenant) or "")
        if not assignment_id:
            return None, "Missing assignment_id"
        endpoint = endpoint.replace("{assignment_id}", assignment_id)
    return endpoint, None


def _extract_excerpt(response) -> str:
    data = getattr(response, "data", None)
    if data is not None:
        try:
            return json.dumps(data, default=str)[:2000]
        except Exception:
            return str(data)[:2000]
    try:
        return response.content.decode("utf-8", errors="ignore")[:2000]
    except Exception:
        return ""


def _request_headers(tenant: Tenant, portal: str, tab: str) -> dict[str, str]:
    platform_domain = getattr(settings, "PLATFORM_DOMAIN", "localhost")
    return {
        "HTTP_HOST": f"{tenant.subdomain}.{platform_domain}",
        "HTTP_X_LP_PORTAL": portal,
        "HTTP_X_LP_TAB": tab,
        "HTTP_X_LP_ROUTE": f"/{portal.lower()}",
    }


def _coerce_payload(case_cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    payload = {**(case_cfg.get("payload_defaults", {}) or {})}
    payload.update({k: v for k, v in params.items() if k not in {"course_id", "assignment_id"}})

    if case_cfg["endpoint"] == "/api/courses/" and "title" not in payload:
        payload["title"] = f"Ops Replay Course {timezone.now().strftime('%H%M%S')}"

    if case_cfg["endpoint"] == "/api/courses/{course_id}/modules/" and "title" not in payload:
        payload["title"] = "Ops Replay Module"
        payload["description"] = "Generated by replay run"
        payload["order"] = 1

    return payload


def execute_replay_run(run: OpsReplayRun) -> OpsReplayRun:
    from .services import record_route_error  # Local import to avoid circular import.

    run.status = "RUNNING"
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at", "updated_at"])

    tenant = run.tenant
    user = _pick_portal_user(tenant, run.portal)
    if not user:
        run.status = "FAILED"
        run.summary_json = {"error": f"No active user found for portal {run.portal}."}
        run.ended_at = timezone.now()
        run.save(update_fields=["status", "summary_json", "ended_at", "updated_at"])
        return run

    client = APIClient()
    client.force_authenticate(user=user)

    requested_cases = run.requested_cases_json if isinstance(run.requested_cases_json, list) else []
    if not requested_cases:
        run.status = "FAILED"
        run.summary_json = {"error": "No replay cases requested."}
        run.ended_at = timezone.now()
        run.save(update_fields=["status", "summary_json", "ended_at", "updated_at"])
        return run

    passed = 0
    failed = 0
    skipped = 0
    step_count = 0

    for requested in requested_cases:
        if run.status == "CANCELLED":
            break

        if isinstance(requested, str):
            case_id = requested
            params = {}
        else:
            case_id = str(requested.get("case_id", "")).strip()
            params = requested.get("params", {}) or {}

        step_count += 1
        case_cfg = REPLAY_CASES.get(case_id)
        if not case_cfg:
            OpsReplayStep.objects.create(
                run=run,
                case_id=case_id or "unknown",
                case_label="Unknown case",
                endpoint="",
                method="GET",
                request_payload_json=params,
                response_excerpt="Case not found in replay catalog.",
                pass_fail=False,
            )
            failed += 1
            continue

        if case_cfg["portal"] != run.portal:
            OpsReplayStep.objects.create(
                run=run,
                case_id=case_id,
                case_label=case_cfg["label"],
                endpoint=case_cfg["endpoint"],
                method=case_cfg["method"],
                request_payload_json=params,
                response_excerpt=f"Case portal mismatch: run={run.portal}, case={case_cfg['portal']}",
                pass_fail=False,
            )
            failed += 1
            continue

        endpoint, endpoint_error = _resolve_endpoint(case_cfg["endpoint"], tenant, params)
        if endpoint_error:
            OpsReplayStep.objects.create(
                run=run,
                case_id=case_id,
                case_label=case_cfg["label"],
                endpoint=case_cfg["endpoint"],
                method=case_cfg["method"],
                request_payload_json=params,
                response_excerpt=endpoint_error,
                pass_fail=False,
            )
            failed += 1
            continue

        method = case_cfg["method"].upper()
        headers = _request_headers(tenant, run.portal, case_cfg["tab"])
        query_params = {**(case_cfg.get("query_defaults", {}) or {})}
        query_params.update(params.get("query", {}) if isinstance(params.get("query"), dict) else {})
        payload = _coerce_payload(case_cfg, params)
        mutation = method in {"POST", "PUT", "PATCH", "DELETE"}

        if run.dry_run and mutation:
            OpsReplayStep.objects.create(
                run=run,
                case_id=case_id,
                case_label=case_cfg["label"],
                endpoint=endpoint,
                method=method,
                request_payload_json=payload,
                response_excerpt="Dry-run: mutation skipped.",
                pass_fail=True,
            )
            skipped += 1
            continue

        started = time.perf_counter()
        try:
            if method == "GET":
                response = client.get(endpoint, query_params, format="json", **headers)
            elif method == "POST":
                response = client.post(endpoint, payload, format="json", **headers)
            elif method == "PATCH":
                response = client.patch(endpoint, payload, format="json", **headers)
            elif method == "PUT":
                response = client.put(endpoint, payload, format="json", **headers)
            elif method == "DELETE":
                response = client.delete(endpoint, payload, format="json", **headers)
            else:
                raise ValueError(f"Unsupported method: {method}")
            latency_ms = int((time.perf_counter() - started) * 1000)
            status_code = int(getattr(response, "status_code", 0) or 0)
            excerpt = _extract_excerpt(response)
            pass_fail = 200 <= status_code < 300
            error_group = None
            if status_code in {429, 500}:
                error_group = record_route_error(
                    tenant=tenant,
                    portal=run.portal,
                    tab_key=case_cfg["tab"],
                    route_path=f"/{run.portal.lower()}",
                    component_name="ReplayRunner",
                    endpoint=endpoint,
                    method=method,
                    status_code=status_code,
                    request_id=str(getattr(response, "headers", {}).get("X-Request-ID", ""))[:64],
                    payload=payload if mutation else query_params,
                    response_excerpt=excerpt,
                    error_message="",
                )
            OpsReplayStep.objects.create(
                run=run,
                case_id=case_id,
                case_label=case_cfg["label"],
                endpoint=endpoint,
                method=method,
                request_payload_json=payload if mutation else query_params,
                response_status=status_code,
                response_excerpt=excerpt,
                latency_ms=latency_ms,
                pass_fail=pass_fail,
                error_group=error_group,
            )
            if pass_fail:
                passed += 1
            else:
                failed += 1
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            OpsReplayStep.objects.create(
                run=run,
                case_id=case_id,
                case_label=case_cfg["label"],
                endpoint=endpoint,
                method=method,
                request_payload_json=payload if mutation else query_params,
                response_excerpt=str(exc)[:2000],
                latency_ms=latency_ms,
                pass_fail=False,
            )
            failed += 1

    if run.status != "CANCELLED":
        run.status = "COMPLETED" if failed == 0 else "FAILED"
    run.ended_at = timezone.now()
    run.summary_json = {
        "requested": step_count,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "duration_seconds": (
            int((run.ended_at - run.started_at).total_seconds()) if run.started_at and run.ended_at else 0
        ),
    }
    run.save(update_fields=["status", "ended_at", "summary_json", "updated_at"])
    return run
