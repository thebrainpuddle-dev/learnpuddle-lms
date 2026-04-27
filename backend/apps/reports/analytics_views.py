# apps/reports/analytics_views.py

"""
Analytics chart endpoints introduced in FE-034.

Endpoints:
  GET /api/v1/reports/analytics/deadline-adherence/
  GET /api/v1/reports/analytics/approval-trends/
  GET /api/v1/reports/analytics/course-effectiveness/

All require @admin_only + @tenant_required and are tenant-isolated.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Optional

from django.db.models import Avg, Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.courses.models import Course
from apps.progress.models import AssignmentSubmission, QuizSubmission, TeacherProgress
from utils.decorators import admin_only, tenant_required


def _parse_date(raw: Optional[str]) -> Optional[date]:
    """Parse an ISO date string (YYYY-MM-DD). Returns None on failure."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# 1. Deadline Adherence
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def deadline_adherence(request):
    """
    Monthly breakdown of on-time vs late course completions.

    Only courses with a deadline set are included. A completion is "on time"
    when TeacherProgress.completed_at.date() <= course.deadline.

    Query params:
        start (str, optional): ISO date (YYYY-MM-DD), inclusive lower bound
                               on completed_at.
        end   (str, optional): ISO date (YYYY-MM-DD), inclusive upper bound
                               on completed_at.

    Response: list[DeadlineAdherencePoint]
        period          str   — "Jan 2026"
        adherencePercent float — 0–100
        totalTeachers   int
        onTime          int
        late            int
    """
    start = _parse_date(request.GET.get("start"))
    end = _parse_date(request.GET.get("end"))

    qs = (
        TeacherProgress.all_objects.filter(
            tenant=request.tenant,
            content__isnull=True,           # course-level rows only
            status="COMPLETED",
            completed_at__isnull=False,
            course__deadline__isnull=False,  # only courses with deadlines
        )
        .select_related("course")
    )

    if start:
        qs = qs.filter(completed_at__date__gte=start)
    if end:
        qs = qs.filter(completed_at__date__lte=end)

    # Group by calendar month of completion
    by_period: dict[str, dict] = {}
    for tp in qs:
        period = tp.completed_at.strftime("%b %Y")
        # Keep the first day of the month as a stable sort key
        sort_key = tp.completed_at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if period not in by_period:
            by_period[period] = {"sort_key": sort_key, "on_time": 0, "late": 0}
        if tp.completed_at.date() <= tp.course.deadline:
            by_period[period]["on_time"] += 1
        else:
            by_period[period]["late"] += 1

    result = []
    for period, data in sorted(by_period.items(), key=lambda x: x[1]["sort_key"]):
        on_time = data["on_time"]
        late = data["late"]
        total = on_time + late
        adherence = round(on_time / total * 100, 1) if total > 0 else 0.0
        result.append(
            {
                "period": period,
                "adherencePercent": adherence,
                "totalTeachers": total,
                "onTime": on_time,
                "late": late,
            }
        )

    return Response(result)


# ---------------------------------------------------------------------------
# 2. Approval Trends
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def approval_trends(request):
    """
    Monthly breakdown of AssignmentSubmission statuses.

    Mapping:
        approved  = GRADED with score >= assignment.passing_score
        rejected  = GRADED with score <  assignment.passing_score
                    Note: GRADED with score IS NULL also falls into the "rejected"
                    bucket — a graded submission without a recorded score is treated
                    as a failed/rejected attempt rather than pending re-grading.
        pending   = PENDING or SUBMITTED

    Query params:
        start (str, optional): ISO date (YYYY-MM-DD), inclusive lower bound
                               on submitted_at.
        end   (str, optional): ISO date (YYYY-MM-DD), inclusive upper bound
                               on submitted_at.

    Response: list[ApprovalTrendsPoint]
        period   str — "Jan 2026"
        approved int
        rejected int
        pending  int
    """
    start = _parse_date(request.GET.get("start"))
    end = _parse_date(request.GET.get("end"))

    qs = (
        AssignmentSubmission.all_objects.filter(
            tenant=request.tenant,
        )
        .select_related("assignment")
    )

    if start:
        qs = qs.filter(submitted_at__date__gte=start)
    if end:
        qs = qs.filter(submitted_at__date__lte=end)

    by_period: dict[str, dict] = {}
    for sub in qs:
        period = sub.submitted_at.strftime("%b %Y")
        sort_key = sub.submitted_at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if period not in by_period:
            by_period[period] = {
                "sort_key": sort_key,
                "approved": 0,
                "rejected": 0,
                "pending": 0,
            }
        if sub.status == "GRADED":
            passing = sub.assignment.passing_score
            if sub.score is not None and sub.score >= passing:
                by_period[period]["approved"] += 1
            else:
                by_period[period]["rejected"] += 1
        elif sub.status in ("PENDING", "SUBMITTED"):
            by_period[period]["pending"] += 1

    result = []
    for period, data in sorted(by_period.items(), key=lambda x: x[1]["sort_key"]):
        result.append(
            {
                "period": period,
                "approved": data["approved"],
                "rejected": data["rejected"],
                "pending": data["pending"],
            }
        )

    return Response(result)


# ---------------------------------------------------------------------------
# 3. Course Effectiveness
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def course_effectiveness(request):
    """
    Per-course effectiveness metrics for all published courses.

    Metrics:
        enrolledCount  = TeacherProgress rows with content=None (course-level)
        completionRate = (COMPLETED / enrolledCount) × 100
        avgScore       = mean QuizSubmission.score for quizzes in this course
                         (0.0 when no submissions)

    Unpublished (draft) courses are excluded.

    Response: list[CourseEffectivenessItem]
        courseId       str   — UUID string
        courseName     str
        completionRate float — 0–100
        avgScore       float — 0–100
        enrolledCount  int
    """
    # Published courses for this tenant (TenantSoftDeleteManager auto-filters by tenant)
    courses = list(
        Course.objects.filter(is_published=True, is_active=True).order_by("title")
    )

    if not courses:
        return Response([])

    course_ids = [c.id for c in courses]

    # --- enrollment and completion counts (course-level rows: content=None) ---
    enrolled_by_course: dict[str, int] = defaultdict(int)
    completed_by_course: dict[str, int] = defaultdict(int)

    progress_rows = (
        TeacherProgress.all_objects.filter(
            tenant=request.tenant,
            course_id__in=course_ids,
            content__isnull=True,
        )
        .values("course_id", "status")
    )
    for row in progress_rows:
        cid = str(row["course_id"])
        enrolled_by_course[cid] += 1
        if row["status"] == "COMPLETED":
            completed_by_course[cid] += 1

    # --- average quiz score per course ---
    # Path: QuizSubmission → quiz (FK) → assignment (OneToOneField) → course
    avg_by_course: dict[str, float] = {}
    quiz_score_rows = (
        QuizSubmission.all_objects.filter(
            tenant=request.tenant,
            quiz__assignment__course_id__in=course_ids,
            score__isnull=False,
        )
        .values("quiz__assignment__course_id")
        .annotate(avg_score=Avg("score"))
    )
    for row in quiz_score_rows:
        avg_by_course[str(row["quiz__assignment__course_id"])] = float(row["avg_score"])

    # --- assemble response ---
    result = []
    for course in courses:
        cid = str(course.id)
        enrolled = enrolled_by_course[cid]
        completed = completed_by_course[cid]
        completion_rate = round(completed / enrolled * 100, 1) if enrolled > 0 else 0.0
        avg_score = round(avg_by_course.get(cid, 0.0), 1)

        result.append(
            {
                "courseId": cid,
                "courseName": course.title,
                "completionRate": completion_rate,
                "avgScore": avg_score,
                "enrolledCount": enrolled,
            }
        )

    return Response(result)
