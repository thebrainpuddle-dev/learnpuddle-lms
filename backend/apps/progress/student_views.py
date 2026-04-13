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

from .student_serializers import (
    StudentProgressSerializer,
    StudentAssignmentListSerializer,
    StudentAssignmentSubmissionSerializer,
)

logger = logging.getLogger(__name__)


def _utcnow():
    return datetime.now(timezone.utc)


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
        QuizSubmission.objects.filter(
            teacher=user,
            quiz__assignment__in=assignments,
        ).values_list("quiz__assignment_id", flat=True)
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

    quiz_submissions = QuizSubmission.objects.filter(teacher=request.user, quiz__assignment__in=qs).select_related("quiz")
    quiz_submissions_map = {qs_item.quiz.assignment_id: qs_item for qs_item in quiz_submissions}

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

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
def student_quiz_detail(request, assignment_id):
    """
    Fetch quiz questions for a quiz-type assignment.
    (Does not return correct answers.)
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

    submission = QuizSubmission.objects.filter(quiz=quiz, teacher=request.user).first()

    questions = []
    for q in quiz.questions.all().order_by("order"):
        questions.append(
            {
                "id": str(q.id),
                "order": q.order,
                "question_type": q.question_type,
                "selection_mode": q.selection_mode,
                "prompt": q.prompt,
                "options": q.options or [],
                "points": q.points,
            }
        )

    return Response(
        {
            "assignment_id": str(assignment.id),
            "quiz_id": str(quiz.id),
            "schema_version": quiz.schema_version,
            "questions": questions,
            "submission": (
                {
                    "answers": submission.answers,
                    "score": float(submission.score) if submission.score is not None else None,
                    "graded_at": submission.graded_at,
                    "submitted_at": submission.submitted_at,
                }
                if submission
                else None
            ),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
def student_quiz_submit(request, assignment_id):
    """
    Submit quiz answers. Objective questions are auto-graded; short answers are stored for review.

    Payload:
      {
        "answers": {
          "<question_uuid>": { "option_index": 1 }
            | { "option_indices": [0, 2] }
            | { "value": true }
            | { "text": "..." }
        }
      }
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

    answers = request.data.get("answers") or {}
    if not isinstance(answers, dict):
        return error_response("answers must be an object", status_code=status.HTTP_400_BAD_REQUEST)

    # Limit answers payload size: max 200 keys, each value must be a flat dict
    max_answers = 200
    if len(answers) > max_answers:
        return error_response(f"Too many answers (max {max_answers})", status_code=status.HTTP_400_BAD_REQUEST)
    for key, val in answers.items():
        if not isinstance(val, dict):
            return error_response(f"Each answer must be an object, got {type(val).__name__} for '{key}'", status_code=status.HTTP_400_BAD_REQUEST)
        # Reject nested objects. Allow option_indices as a flat list for multi-select MCQ.
        for inner_key, inner_val in val.items():
            if isinstance(inner_val, dict):
                return error_response("Answer values cannot contain nested objects", status_code=status.HTTP_400_BAD_REQUEST)
            if isinstance(inner_val, list):
                if inner_key != "option_indices":
                    return error_response("Only option_indices may be an array value", status_code=status.HTTP_400_BAD_REQUEST)
                if any(isinstance(v, (dict, list)) for v in inner_val):
                    return error_response("option_indices must be a flat array", status_code=status.HTTP_400_BAD_REQUEST)

    # Auto-grade objective questions; track whether manual review is needed for short-answer
    all_questions = list(quiz.questions.all())
    has_short_answer = any(q.question_type == "SHORT_ANSWER" for q in all_questions)
    mcq_score = 0.0
    for q in all_questions:
        if q.question_type == "SHORT_ANSWER":
            continue

        got = answers.get(str(q.id)) or {}
        if not isinstance(got, dict):
            continue

        if q.question_type == "MCQ":
            mode = (q.selection_mode or "SINGLE").upper()
            if mode == "MULTIPLE":
                expected_raw = (q.correct_answer or {}).get("option_indices") or []
                if not isinstance(expected_raw, list):
                    continue
                try:
                    expected = {int(v) for v in expected_raw}
                except Exception:
                    continue
                selected_raw = got.get("option_indices") or []
                if not isinstance(selected_raw, list):
                    continue
                try:
                    selected = {int(v) for v in selected_raw}
                except Exception:
                    continue
                if selected and selected == expected:
                    mcq_score += float(q.points or 1)
                continue

            try:
                expected = int((q.correct_answer or {}).get("option_index"))
            except Exception:
                continue
            try:
                selected = int(got.get("option_index"))
            except Exception:
                selected = None
            if selected is not None and selected == expected:
                mcq_score += float(q.points or 1)
            continue

        if q.question_type == "TRUE_FALSE":
            expected = (q.correct_answer or {}).get("value")
            selected = got.get("value")
            if isinstance(expected, bool) and isinstance(selected, bool) and selected == expected:
                mcq_score += float(q.points or 1)
            continue

    obj, _created = QuizSubmission.objects.get_or_create(
        quiz=quiz,
        teacher=request.user,
        defaults={"tenant": request.tenant, "answers": answers},
    )
    obj.answers = answers

    if has_short_answer:
        # Quiz needs manual review for short-answer questions.
        # Store the MCQ partial score so it can be combined with manual grading later.
        # Do NOT set graded_at — this keeps status as "SUBMITTED" until admin reviews.
        obj.score = mcq_score
        obj.graded_at = None
    else:
        # All questions are MCQ — fully auto-graded.
        obj.score = mcq_score
        obj.graded_at = _utcnow()

    obj.save()

    return Response(
        {
            "quiz_id": str(quiz.id),
            "assignment_id": str(assignment.id),
            "score": float(obj.score) if obj.score is not None else None,
            "graded_at": obj.graded_at,
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
