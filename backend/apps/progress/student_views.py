"""
Student-facing progress, assignment, and quiz views.

Dashboard:
    GET /api/v1/student/dashboard/

Progress tracking:
    POST  /api/v1/student/progress/content/<content_id>/start/
    PATCH /api/v1/student/progress/content/<content_id>/
    POST  /api/v1/student/progress/content/<content_id>/complete/

Assignments:
    GET  /api/v1/student/assignments/
    POST /api/v1/student/assignments/<assignment_id>/submit/
    GET  /api/v1/student/assignments/<assignment_id>/submission/

Quizzes:
    GET  /api/v1/student/quizzes/<assignment_id>/
    POST /api/v1/student/quizzes/<assignment_id>/submit/

Gamification:
    GET /api/v1/student/gamification/summary/

Search:
    GET /api/v1/student/search/
"""

import logging
from datetime import datetime, timezone

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.courses.models import Course, Content
from apps.progress.completion_metrics import (
    STATUS_COMPLETED,
    build_teacher_course_snapshots,
)
from apps.progress.models import (
    TeacherProgress,
    Assignment,
    AssignmentSubmission,
    QuizSubmission,
)
from utils.decorators import student_only, student_or_admin, tenant_required
from utils.course_access import is_student_assigned_to_course as _student_assigned_to_course
from utils.responses import error_response
# Shared quiz helpers (extracted to apps.progress.quiz_helpers so both role
# view modules import from a neutral location — see m1 in review TASK-013).
from .quiz_helpers import (
    _utcnow,
    get_in_progress_attempt,
    grade_quiz_answers,
    serialize_attempt,
    start_quiz_attempt,
    validate_answers_payload,
)

from .student_serializers import (
    StudentProgressSerializer,
    StudentAssignmentListSerializer,
    StudentAssignmentSubmissionSerializer,
)

logger = logging.getLogger(__name__)
# _utcnow is imported from teacher_views above


def _student_assigned_courses_qs(request):
    """Get published, active courses assigned to the current student.

    Note: Course uses TenantSoftDeleteManager which auto-filters by tenant
    via get_current_tenant(). Do NOT add tenant=request.tenant here.
    """
    user = request.user
    return (
        Course.objects.filter(is_active=True, is_published=True)
        .filter(
            Q(assigned_to_all_students=True)
            | Q(assigned_students=user)
        )
        .distinct()
    )


# ═══════════════════════════════════════════════════════════════════════════
# Dashboard
# ═══════════════════════════════════════════════════════════════════════════

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
def student_dashboard(request):
    """
    Student dashboard data: stats, continue-learning, deadlines.
    """
    user = request.user
    courses = list(_student_assigned_courses_qs(request))
    total_courses = len(courses)
    course_ids = [course.id for course in courses]
    completion_snapshots = build_teacher_course_snapshots(course_ids, [user.id])
    course_snapshot_values = list(completion_snapshots.values())

    # Overall progress is content-based across all assigned courses.
    total_contents = sum(snapshot.total_content_count for snapshot in course_snapshot_values)
    completed_contents = sum(snapshot.completed_content_count for snapshot in course_snapshot_values)
    overall_progress = round((completed_contents / total_contents) * 100.0, 2) if total_contents else 0.0
    completed_course_count = sum(1 for snapshot in course_snapshot_values if snapshot.status == STATUS_COMPLETED)

    # Assignments for assigned courses
    assignments = Assignment.objects.filter(course__in=courses, is_active=True)
    submissions = AssignmentSubmission.objects.filter(teacher=user, assignment__in=assignments)
    submitted_regular_ids = set(
        submissions.filter(status__in=["SUBMITTED", "GRADED"]).values_list("assignment_id", flat=True)
    )
    submitted_quiz_ids = set(
        # Only count completed submissions (score IS NOT NULL).
        # In-progress attempts (score IS NULL) are not yet submitted.
        QuizSubmission.objects.filter(
            teacher=user,
            quiz__assignment__in=assignments,
        ).exclude(score__isnull=True).values_list("quiz__assignment_id", flat=True)
    )
    submitted_assignment_ids = submitted_regular_ids | submitted_quiz_ids
    pending_assignments = assignments.exclude(id__in=submitted_assignment_ids).count()

    # Continue learning: most recently accessed in-progress content
    last_progress = (
        TeacherProgress.objects.filter(
            teacher=user,
            course__in=courses,
            content__isnull=False,
            status__in=["IN_PROGRESS", "NOT_STARTED"],
        )
        .select_related("course", "content")
        .order_by("-last_accessed")
        .first()
    )
    continue_learning = None
    if last_progress and last_progress.course and last_progress.content:
        continue_learning = {
            "course_id": str(last_progress.course_id),
            "course_title": last_progress.course.title,
            "content_id": str(last_progress.content_id),
            "content_title": last_progress.content.title,
            "progress_percentage": float(last_progress.progress_percentage),
        }

    # Upcoming deadlines: course deadline (date) + assignment due_date (datetime)
    now = _utcnow()
    deadline_items = []
    for course in sorted((c for c in courses if c.deadline is not None), key=lambda item: item.deadline)[:10]:
        days_left = (datetime.combine(course.deadline, datetime.min.time(), tzinfo=timezone.utc) - now).days
        deadline_items.append(
            {
                "type": "course",
                "id": str(course.id),
                "title": course.title,
                "days_left": days_left,
            }
        )
    for a in assignments.exclude(due_date__isnull=True).order_by("due_date")[:10]:
        days_left = (a.due_date - now).days
        deadline_items.append(
            {"type": "assignment", "id": str(a.id), "title": a.title, "days_left": days_left}
        )
    deadline_items = sorted(deadline_items, key=lambda x: x["days_left"])[:10]

    return Response(
        {
            "stats": {
                "overall_progress": overall_progress,
                "total_courses": total_courses,
                "completed_courses": completed_course_count,
                "pending_assignments": pending_assignments,
            },
            "continue_learning": continue_learning,
            "deadlines": deadline_items,
        },
        status=status.HTTP_200_OK,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Progress Tracking
# ═══════════════════════════════════════════════════════════════════════════

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
def student_progress_start(request, content_id):
    """Start tracking progress for a content item."""
    content = get_object_or_404(
        Content,
        id=content_id,
        is_active=True,
        module__course__tenant=request.tenant,
        module__course__is_published=True,
        module__course__is_active=True,
    )
    course = content.module.course
    if not _student_assigned_to_course(request.user, course):
        return error_response("Not assigned to this course", status_code=status.HTTP_403_FORBIDDEN)

    obj, _created = TeacherProgress.objects.get_or_create(
        teacher=request.user,
        course=course,
        content=content,
        defaults={"tenant": request.tenant, "status": "IN_PROGRESS", "started_at": _utcnow()},
    )
    if obj.status == "NOT_STARTED":
        obj.status = "IN_PROGRESS"
    if not obj.started_at:
        obj.started_at = _utcnow()
    obj.save()
    return Response(StudentProgressSerializer(obj).data, status=status.HTTP_200_OK)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
def student_progress_update(request, content_id):
    """Update progress for a content item (video seconds, percentage)."""
    content = get_object_or_404(
        Content,
        id=content_id,
        is_active=True,
        module__course__tenant=request.tenant,
        module__course__is_published=True,
        module__course__is_active=True,
    )
    course = content.module.course
    if not _student_assigned_to_course(request.user, course):
        return error_response("Not assigned to this course", status_code=status.HTTP_403_FORBIDDEN)

    obj, _created = TeacherProgress.objects.get_or_create(
        teacher=request.user,
        course=course,
        content=content,
        defaults={"tenant": request.tenant, "status": "IN_PROGRESS", "started_at": _utcnow()},
    )

    video_seconds = request.data.get("video_progress_seconds")
    progress_pct = request.data.get("progress_percentage")

    if video_seconds is not None:
        try:
            video_seconds = int(video_seconds)
        except (TypeError, ValueError):
            return error_response("video_progress_seconds must be an integer", status_code=status.HTTP_400_BAD_REQUEST)
        if video_seconds < 0:
            return error_response("video_progress_seconds cannot be negative", status_code=status.HTTP_400_BAD_REQUEST)
        obj.video_progress_seconds = video_seconds

        # Auto-calculate progress_percentage from video duration
        if content.duration and content.duration > 0:
            calculated_pct = min(100.0, (video_seconds / content.duration) * 100)
            obj.progress_percentage = calculated_pct

            # Auto-complete when >= 95% watched (accounts for minor timing differences)
            if calculated_pct >= 95 and obj.status != "COMPLETED":
                obj.status = "COMPLETED"
                obj.completed_at = _utcnow()

    if progress_pct is not None:
        try:
            progress_pct = float(progress_pct)
        except (TypeError, ValueError):
            return error_response("progress_percentage must be a number", status_code=status.HTTP_400_BAD_REQUEST)
        if progress_pct < 0 or progress_pct > 100:
            return error_response("progress_percentage must be between 0 and 100", status_code=status.HTTP_400_BAD_REQUEST)
        obj.progress_percentage = progress_pct

    if obj.status == "NOT_STARTED":
        obj.status = "IN_PROGRESS"
    if not obj.started_at:
        obj.started_at = _utcnow()

    obj.save()

    return Response(StudentProgressSerializer(obj).data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
def student_progress_complete(request, content_id):
    """Mark content as completed."""
    content = get_object_or_404(
        Content,
        id=content_id,
        is_active=True,
        module__course__tenant=request.tenant,
        module__course__is_published=True,
        module__course__is_active=True,
    )
    course = content.module.course
    if not _student_assigned_to_course(request.user, course):
        return error_response("Not assigned to this course", status_code=status.HTTP_403_FORBIDDEN)

    # Block completion if VIDEO content hasn't finished processing
    if content.content_type == "VIDEO":
        asset = getattr(content, "video_asset", None)
        if not asset or asset.status != "READY":
            return error_response(
                "Video is not ready yet. Please wait for processing to complete.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    obj, _created = TeacherProgress.objects.get_or_create(
        teacher=request.user,
        course=course,
        content=content,
        defaults={"tenant": request.tenant, "status": "COMPLETED", "started_at": _utcnow(), "completed_at": _utcnow(), "progress_percentage": 100},
    )
    obj.status = "COMPLETED"
    obj.progress_percentage = 100
    if not obj.started_at:
        obj.started_at = _utcnow()
    obj.completed_at = _utcnow()
    obj.save()
    return Response(StudentProgressSerializer(obj).data, status=status.HTTP_200_OK)


# ═══════════════════════════════════════════════════════════════════════════
# Assignments
# ═══════════════════════════════════════════════════════════════════════════

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
def student_assignment_list(request):
    """
    List assignments for the student's assigned courses.
    Supports ?status=PENDING|SUBMITTED|GRADED.
    """
    status_filter = request.GET.get("status")
    courses = _student_assigned_courses_qs(request)
    qs = (
        Assignment.objects.filter(course__in=courses, is_active=True)
        .select_related("course")
        .select_related("quiz")
    )

    # Prefetch student submissions (both regular and quiz)
    submissions = AssignmentSubmission.objects.filter(teacher=request.user, assignment__in=qs).select_related("assignment")
    submissions_map = {s.assignment_id: s for s in submissions}

    # Only completed submissions (score IS NOT NULL) — highest score per assignment.
    quiz_submissions = (
        QuizSubmission.objects.filter(teacher=request.user, quiz__assignment__in=qs)
        .exclude(score__isnull=True)
        .select_related("quiz")
        .order_by("-score", "-attempt_number")
    )
    # Keep best-scoring submission per assignment.
    quiz_submissions_map = {}
    for qs_item in quiz_submissions:
        asgn_id = qs_item.quiz.assignment_id
        if asgn_id not in quiz_submissions_map:
            quiz_submissions_map[asgn_id] = qs_item

    def _derive_status(assignment):
        """Derive display status for an assignment, handling both quiz and regular types."""
        if getattr(assignment, "quiz", None):
            qs_item = quiz_submissions_map.get(assignment.id)
            if not qs_item:
                return "PENDING"
            return "GRADED" if qs_item.graded_at is not None else "SUBMITTED"
        sub = submissions_map.get(assignment.id)
        return sub.status if sub else "PENDING"

    # Apply filter by derived status
    if status_filter in {"PENDING", "SUBMITTED", "GRADED"}:
        filtered = []
        for a in qs:
            derived = _derive_status(a)
            if derived == status_filter:
                setattr(a, "_submission_for_student", submissions_map.get(a.id))
                filtered.append(a)
        serializer = StudentAssignmentListSerializer(filtered, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    # Attach submission for serializer
    items = []
    for a in qs:
        setattr(a, "_submission_for_student", submissions_map.get(a.id))
        items.append(a)
    serializer = StudentAssignmentListSerializer(items, many=True, context={"request": request})
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
def student_assignment_submit(request, assignment_id):
    """
    Submit/update student assignment submission.
    """
    assignment = get_object_or_404(
        Assignment,
        id=assignment_id,
        is_active=True,
        course__tenant=request.tenant,
        course__is_published=True,
        course__is_active=True,
    )
    if not _student_assigned_to_course(request.user, assignment.course):
        return error_response("Not assigned to this course", status_code=status.HTTP_403_FORBIDDEN)

    submission_text = request.data.get("submission_text", "")
    file_url = request.data.get("file_url", "")

    obj, _created = AssignmentSubmission.objects.get_or_create(
        assignment=assignment,
        teacher=request.user,
        defaults={"tenant": request.tenant, "submission_text": submission_text, "file_url": file_url, "status": "SUBMITTED"},
    )
    obj.submission_text = submission_text
    obj.file_url = file_url
    obj.status = "SUBMITTED"
    obj.save()

    return Response(StudentAssignmentSubmissionSerializer(obj).data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
def student_assignment_submission_detail(request, assignment_id):
    """Get submission detail for an assignment."""
    assignment = get_object_or_404(
        Assignment,
        id=assignment_id,
        is_active=True,
        course__tenant=request.tenant,
    )
    if not _student_assigned_to_course(request.user, assignment.course):
        return error_response("Not assigned to this course", status_code=status.HTTP_403_FORBIDDEN)

    submission = get_object_or_404(AssignmentSubmission, assignment=assignment, teacher=request.user)
    return Response(StudentAssignmentSubmissionSerializer(submission).data, status=status.HTTP_200_OK)


# ═══════════════════════════════════════════════════════════════════════════
# Quizzes
# ═══════════════════════════════════════════════════════════════════════════

def _build_student_quiz_detail_response(*, assignment, quiz, teacher):
    """Shared payload builder for student quiz detail / start responses.

    Read-only — never creates a ``QuizSubmission`` row. Mirror of the teacher
    helper but kept local so student_views has no cross-module dependency on
    teacher_views (see m1 in review TASK-013).
    """
    completed_submissions = list(
        QuizSubmission.all_objects.filter(quiz=quiz, teacher=teacher)
        .exclude(score__isnull=True)
        .order_by("attempt_number")
    )
    attempts_used = len(completed_submissions)
    max_attempts = quiz.max_attempts  # 0 = unlimited

    in_progress = get_in_progress_attempt(quiz, teacher)

    best_score = None
    if completed_submissions:
        scores = [float(s.score) for s in completed_submissions if s.score is not None]
        best_score = max(scores) if scores else None

    best_submission = None
    if completed_submissions:
        best_submission = max(
            completed_submissions,
            key=lambda s: (float(s.score) if s.score is not None else -1.0, s.attempt_number),
        )

    questions = [
        {
            "id": str(q.id),
            "order": q.order,
            "question_type": q.question_type,
            "selection_mode": q.selection_mode,
            "prompt": q.prompt,
            "options": q.options or [],
            "points": q.points,
        }
        for q in quiz.questions.all().order_by("order")
    ]

    attempts_exhausted = (
        max_attempts > 0
        and attempts_used >= max_attempts
        and in_progress is None
    )

    return {
        "assignment_id": str(assignment.id),
        "quiz_id": str(quiz.id),
        "schema_version": quiz.schema_version,
        "max_attempts": max_attempts,
        "time_limit_minutes": quiz.time_limit_minutes,
        "attempts_used": attempts_used,
        "attempts_remaining": (
            None if max_attempts == 0 else max(0, max_attempts - attempts_used)
        ),
        "best_score": best_score,
        "current_attempt": (
            {
                "attempt_number": in_progress.attempt_number,
                "started_at": in_progress.started_at,
            }
            if in_progress
            else None
        ),
        "attempts_exhausted": attempts_exhausted,
        "attempt_history": [serialize_attempt(s) for s in completed_submissions],
        "questions": questions,
        # Legacy field — aligned to best-score (m5 in review TASK-013).
        "submission": (
            serialize_attempt(best_submission) if best_submission else None
        ),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
def student_quiz_detail(request, assignment_id):
    """
    Fetch quiz questions for a quiz-type assignment (student role).

    GET is read-only — clients must POST to ``/start/`` to begin an attempt.
    See ``teacher_views.quiz_detail`` for the full response schema.
    """
    assignment = get_object_or_404(
        Assignment,
        id=assignment_id,
        is_active=True,
        course__tenant=request.tenant,
        course__is_published=True,
        course__is_active=True,
    )
    if not _student_assigned_to_course(request.user, assignment.course):
        return error_response("Not assigned to this course", status_code=status.HTTP_403_FORBIDDEN)

    quiz = getattr(assignment, "quiz", None)
    if not quiz:
        return error_response("Quiz not found for assignment", status_code=status.HTTP_404_NOT_FOUND)

    payload = _build_student_quiz_detail_response(
        assignment=assignment, quiz=quiz, teacher=request.user,
    )
    return Response(payload, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
def student_quiz_start(request, assignment_id):
    """
    Explicitly start (or resume) a quiz attempt (student role).

    See ``teacher_views.quiz_start`` for behaviour documentation.
    """
    assignment = get_object_or_404(
        Assignment,
        id=assignment_id,
        is_active=True,
        course__tenant=request.tenant,
        course__is_published=True,
        course__is_active=True,
    )
    if not _student_assigned_to_course(request.user, assignment.course):
        return error_response("Not assigned to this course", status_code=status.HTTP_403_FORBIDDEN)

    quiz = getattr(assignment, "quiz", None)
    if not quiz:
        return error_response("Quiz not found for assignment", status_code=status.HTTP_404_NOT_FOUND)

    _submission, error = start_quiz_attempt(quiz, request.user, request.tenant)
    if error:
        return error_response(error, status_code=status.HTTP_400_BAD_REQUEST)

    payload = _build_student_quiz_detail_response(
        assignment=assignment, quiz=quiz, teacher=request.user,
    )
    return Response(payload, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
def student_quiz_submit(request, assignment_id):
    """
    Submit quiz answers for the current in-progress attempt (student role).

    See teacher_views.quiz_submit for full documentation.
    """
    assignment = get_object_or_404(
        Assignment,
        id=assignment_id,
        is_active=True,
        course__tenant=request.tenant,
        course__is_published=True,
        course__is_active=True,
    )
    if not _student_assigned_to_course(request.user, assignment.course):
        return error_response("Not assigned to this course", status_code=status.HTTP_403_FORBIDDEN)

    quiz = getattr(assignment, "quiz", None)
    if not quiz:
        return error_response("Quiz not found for assignment", status_code=status.HTTP_404_NOT_FOUND)

    # Validate answers payload.
    answers = request.data.get("answers") or {}
    payload_error = validate_answers_payload(answers)
    if payload_error:
        return error_response(payload_error, status_code=status.HTTP_400_BAD_REQUEST)

    from django.db import transaction as _transaction
    from django.utils import timezone as _tz

    with _transaction.atomic():
        # Lock the in-progress row so parallel submits serialise (m3 in
        # review TASK-013).
        in_progress = (
            QuizSubmission.all_objects.select_for_update()
            .filter(quiz=quiz, teacher=request.user, score__isnull=True)
            .order_by("-attempt_number")
            .first()
        )
        if not in_progress:
            completed_count = QuizSubmission.all_objects.filter(
                quiz=quiz, teacher=request.user,
            ).exclude(score__isnull=True).count()
            max_attempts = quiz.max_attempts
            if max_attempts > 0 and completed_count >= max_attempts:
                return error_response(
                    f"Maximum attempts reached ({max_attempts})",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            return error_response(
                "No in-progress attempt found. POST to /start/ to begin an attempt.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Check time limit.
        time_expired = False
        if quiz.time_limit_minutes and in_progress.started_at:
            elapsed_seconds = (_tz.now() - in_progress.started_at).total_seconds()
            if elapsed_seconds > quiz.time_limit_minutes * 60:
                time_expired = True

        # Grade the answers.
        mcq_score, has_short_answer = grade_quiz_answers(quiz, answers)

        # Save the submission.
        in_progress.answers = answers
        in_progress.time_expired = time_expired

        if has_short_answer:
            in_progress.score = mcq_score
            in_progress.graded_at = None
        else:
            in_progress.score = mcq_score
            in_progress.graded_at = _utcnow()

        in_progress.save()

    return Response(
        {
            "quiz_id": str(quiz.id),
            "assignment_id": str(assignment.id),
            "attempt_number": in_progress.attempt_number,
            "score": float(in_progress.score) if in_progress.score is not None else None,
            "graded_at": in_progress.graded_at,
            "time_expired": time_expired,
        },
        status=status.HTTP_200_OK,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Gamification
# ═══════════════════════════════════════════════════════════════════════════

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
def student_gamification_summary(request):
    """Student gamification summary (XP, badges, streaks)."""
    from apps.progress.gamification import build_teacher_gamification_summary

    courses = _student_assigned_courses_qs(request)
    summary = build_teacher_gamification_summary(request.user, courses)
    return Response(summary, status=status.HTTP_200_OK)


# ═══════════════════════════════════════════════════════════════════════════
# Search
# ═══════════════════════════════════════════════════════════════════════════

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
def student_search(request):
    """
    Global search across courses and assignments for the current student.
    Query param: q (required, min 2 chars)
    """
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return Response({"courses": [], "assignments": []})

    courses_qs = _student_assigned_courses_qs(request)
    matched_courses = courses_qs.filter(
        Q(title__icontains=q) | Q(description__icontains=q)
    )[:10]

    matched_assignments = Assignment.objects.filter(
        course__in=courses_qs,
        is_active=True,
    ).filter(Q(title__icontains=q) | Q(description__icontains=q))[:10]

    return Response({
        "courses": [
            {"id": str(c.id), "title": c.title, "type": "course"}
            for c in matched_courses
        ],
        "assignments": [
            {"id": str(a.id), "title": a.title, "course_id": str(a.course_id), "type": "assignment"}
            for a in matched_assignments
        ],
    })
