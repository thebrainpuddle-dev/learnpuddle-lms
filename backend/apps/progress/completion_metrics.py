from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, Iterable, Optional, Tuple

from django.db.models import Count, Max, Q, Sum, Value
from django.db.models.functions import Coalesce

from apps.courses.models import Content
from apps.progress.models import TeacherProgress

STATUS_COMPLETED = "COMPLETED"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_NOT_STARTED = "NOT_STARTED"


@dataclass(frozen=True)
class CourseCompletionSnapshot:
    course_id: str
    teacher_id: str
    total_content_count: int
    completed_content_count: int
    progress_percentage: float
    status: str
    has_activity: bool
    last_completed_at: Optional[datetime]


def _as_unique_list(values: Iterable) -> list:
    # Preserve order while removing duplicates.
    return list(dict.fromkeys(values))


def _aggregate_progress(course_ids: list, teacher_ids: Optional[list] = None) -> Dict[Tuple[str, str], dict]:
    if not course_ids:
        return {}

    qs = TeacherProgress.objects.filter(
        course_id__in=course_ids,
        content__isnull=False,
        content__is_active=True,
    )
    if teacher_ids is not None:
        qs = qs.filter(teacher_id__in=teacher_ids)

    rows = qs.values("course_id", "teacher_id").annotate(
        activity_count=Count("id"),
        completed_content_count=Count("id", filter=Q(status=STATUS_COMPLETED)),
        progress_sum=Coalesce(Sum("progress_percentage"), Value(Decimal("0.0"))),
        last_completed_at=Max("completed_at", filter=Q(status=STATUS_COMPLETED)),
    )
    return {
        (str(row["course_id"]), str(row["teacher_id"])): row
        for row in rows
    }


def get_active_content_totals(course_ids: Iterable) -> Dict[str, int]:
    normalized_course_ids = _as_unique_list(course_ids)
    if not normalized_course_ids:
        return {}

    rows = (
        Content.objects.filter(module__course_id__in=normalized_course_ids, is_active=True)
        .values("module__course_id")
        .annotate(total=Count("id"))
    )
    return {str(row["module__course_id"]): int(row["total"]) for row in rows}


def derive_completion_status(
    total_content_count: int,
    completed_content_count: int,
    has_activity: bool,
) -> str:
    if total_content_count > 0 and completed_content_count >= total_content_count:
        return STATUS_COMPLETED
    if has_activity:
        return STATUS_IN_PROGRESS
    return STATUS_NOT_STARTED


def derive_progress_percentage(total_content_count: int, progress_sum: Decimal | float | int) -> float:
    if total_content_count <= 0:
        return 0.0
    return round(float(progress_sum) / float(total_content_count), 2)


def build_teacher_course_snapshots(
    course_ids: Iterable,
    teacher_ids: Optional[Iterable] = None,
) -> Dict[Tuple[str, str], CourseCompletionSnapshot]:
    normalized_course_ids = _as_unique_list(course_ids)
    if not normalized_course_ids:
        return {}

    normalized_teacher_ids = _as_unique_list(teacher_ids) if teacher_ids is not None else None

    totals_by_course_id = get_active_content_totals(normalized_course_ids)
    aggregated_rows = _aggregate_progress(normalized_course_ids, normalized_teacher_ids)
    snapshots: Dict[Tuple[str, str], CourseCompletionSnapshot] = {}

    if normalized_teacher_ids is None:
        keys = list(aggregated_rows.keys())
    else:
        keys = [(str(course_id), str(teacher_id)) for course_id in normalized_course_ids for teacher_id in normalized_teacher_ids]

    for course_id_str, teacher_id_str in keys:
        row = aggregated_rows.get((course_id_str, teacher_id_str), {})
        total_content_count = int(totals_by_course_id.get(course_id_str, 0))
        completed_content_count = int(row.get("completed_content_count", 0) or 0)
        activity_count = int(row.get("activity_count", 0) or 0)
        progress_sum = row.get("progress_sum", Decimal("0.0"))
        has_activity = activity_count > 0

        snapshots[(course_id_str, teacher_id_str)] = CourseCompletionSnapshot(
            course_id=course_id_str,
            teacher_id=teacher_id_str,
            total_content_count=total_content_count,
            completed_content_count=completed_content_count,
            progress_percentage=derive_progress_percentage(total_content_count, progress_sum),
            status=derive_completion_status(total_content_count, completed_content_count, has_activity),
            has_activity=has_activity,
            last_completed_at=row.get("last_completed_at"),
        )

    return snapshots


def get_completed_teacher_ids_for_course(course_id, teacher_ids: Iterable) -> set:
    normalized_teacher_ids = _as_unique_list(teacher_ids)
    if not normalized_teacher_ids:
        return set()

    snapshots = build_teacher_course_snapshots([course_id], normalized_teacher_ids)
    completed = set()
    course_key = str(course_id)
    teacher_id_to_original = {str(teacher_id): teacher_id for teacher_id in normalized_teacher_ids}
    for teacher_id in normalized_teacher_ids:
        key = (course_key, str(teacher_id))
        snapshot = snapshots.get(key)
        if snapshot and snapshot.status == STATUS_COMPLETED:
            completed.add(teacher_id_to_original[str(teacher_id)])
    return completed
