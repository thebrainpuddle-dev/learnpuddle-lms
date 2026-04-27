# apps/reports/engagement_views.py

"""
Engagement Heatmap API.

Aggregates tenant-wide teacher activity into a day-of-week x hour-of-day
grid so admins can spot when their teachers are actually engaging with
the LMS.

Signal used: ``TeacherProgress.last_accessed`` (auto_now on every progress
write). This is the most reliable "something happened" timestamp we have
for teachers — progress updates fire on video watches, content marks,
and quiz submissions.

Endpoint:
    GET /api/reports/engagement/heatmap/

Query params:
    tz     - IANA timezone name (e.g. "Asia/Kolkata"). Defaults to UTC.
             Invalid values fall back to UTC and surface a `tz_fallback`
             flag in the response.
    start  - optional ISO date (YYYY-MM-DD). Inclusive lower bound on
             `last_accessed` (interpreted in UTC).
    end    - optional ISO date (YYYY-MM-DD). Exclusive upper bound.
             Defaults: last 30 days window if neither is provided.

Response shape:
    {
      "timezone": "Asia/Kolkata",
      "tz_fallback": false,
      "start": "2026-03-21",
      "end":   "2026-04-20",
      "total_events": 1234,
      "max_cell": 42,
      "cells": [
        {"day": 0, "hour": 0, "count": 3},
        ...
      ]
    }

Cell count is always 7 * 24 = 168, even when count is zero — keeps
rendering simple on the frontend.

Access: SCHOOL_ADMIN or SUPER_ADMIN. Tenant-scoped.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone as dt_timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.progress.models import TeacherProgress
from utils.decorators import admin_only, tenant_required

# Python's datetime.weekday() is Monday=0..Sunday=6. We want Monday-first
# by default — matches how most schools think about the week. The frontend
# can re-label as needed.

DEFAULT_WINDOW_DAYS = 30
MAX_WINDOW_DAYS = 365


def _parse_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _resolve_tz(raw: Optional[str]) -> tuple[ZoneInfo, str, bool]:
    """Return (tzinfo, label, fallback_used)."""
    if not raw:
        return ZoneInfo("UTC"), "UTC", False
    try:
        return ZoneInfo(raw), raw, False
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC"), "UTC", True


def _empty_cells() -> list[dict]:
    return [{"day": d, "hour": h, "count": 0} for d in range(7) for h in range(24)]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def engagement_heatmap(request):
    """Day-of-week × hour-of-day activity grid for the current tenant."""
    tzinfo, tz_label, tz_fallback = _resolve_tz(request.GET.get("tz"))

    end = _parse_date(request.GET.get("end"))
    start = _parse_date(request.GET.get("start"))

    today_utc = datetime.now(dt_timezone.utc).date()
    if end is None:
        end = today_utc + timedelta(days=1)  # inclusive-of-today
    if start is None:
        start = end - timedelta(days=DEFAULT_WINDOW_DAYS)

    if start >= end:
        return Response(
            {"error": "start must be before end"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Clamp to sane upper bound so we don't scan years of history.
    if (end - start).days > MAX_WINDOW_DAYS:
        start = end - timedelta(days=MAX_WINDOW_DAYS)

    # Interpret the day bounds as UTC midnight — the tz only affects
    # bucketing, not the query window. This keeps the "last 30 days"
    # window deterministic regardless of tz choice.
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=dt_timezone.utc)
    end_dt = datetime.combine(end, datetime.min.time(), tzinfo=dt_timezone.utc)

    # Tenant-scoped. We deliberately use `all_objects` to avoid any
    # thread-local TenantManager surprises in tests, and filter by
    # tenant explicitly.
    qs = (
        TeacherProgress.all_objects.filter(
            tenant=request.tenant,
            last_accessed__gte=start_dt,
            last_accessed__lt=end_dt,
        )
        .values_list("last_accessed", flat=True)
    )

    # Initialise 7x24 grid.
    grid = [[0] * 24 for _ in range(7)]
    total = 0
    for ts in qs.iterator(chunk_size=2000):
        local = ts.astimezone(tzinfo)
        grid[local.weekday()][local.hour] += 1
        total += 1

    cells = [
        {"day": d, "hour": h, "count": grid[d][h]}
        for d in range(7)
        for h in range(24)
    ]
    max_cell = max((c["count"] for c in cells), default=0)

    return Response(
        {
            "timezone": tz_label,
            "tz_fallback": tz_fallback,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "total_events": total,
            "max_cell": max_cell,
            "cells": cells,
        },
        status=status.HTTP_200_OK,
    )
