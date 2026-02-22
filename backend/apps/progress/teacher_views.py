import logging
from datetime import datetime, timezone

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.courses.models import Course, Content
from apps.progress.calendar import build_teacher_calendar_window
from apps.progress.gamification import build_teacher_gamification_summary, claim_quest_reward
from apps.progress.locking import get_content_lock_state

logger = logging.getLogger(__name__)
from apps.progress.models import (
    TeacherProgress,
    Assignment,
    AssignmentSubmission,
    QuizSubmission,
)
from utils.decorators import tenant_required, teacher_or_admin

from .teacher_serializers import (
    TeacherProgressSerializer,
    TeacherAssignmentListSerializer,
    TeacherAssignmentSubmissionSerializer,
)


def _utcnow():
    return datetime.now(timezone.utc)


def _teacher_assigned_to_course(user, course: Course) -> bool:
    if user.role in ["SCHOOL_ADMIN", "SUPER_ADMIN"]:
        return True
    if course.assigned_to_all:
        return True
    if course.assigned_teachers.filter(id=user.id).exists():
        return True
    if course.assigned_groups.filter(id__in=user.teacher_groups.values_list("id", flat=True)).exists():
        return True
    return False


def _teacher_assigned_courses_qs(request, with_prefetch=False):
    """Get courses assigned to the current teacher.
    
    Args:
        request: HTTP request with user and tenant
        with_prefetch: If True, prefetch modules and contents for N+1 optimization
    """
    user = request.user
    # Note: Course uses TenantSoftDeleteManager which auto-filters by tenant via get_current_tenant().
    # Do NOT add tenant=request.tenant here - it causes empty results when request.tenant and
    # get_current_tenant() diverge (middleware timing issues).
    qs = (
        Course.objects.filter(is_active=True, is_published=True)
        .filter(
            Q(assigned_to_all=True)
            | Q(assigned_teachers=user)
            | Q(assigned_groups__in=user.teacher_groups.all())
        )
        .distinct()
    )
    
    if with_prefetch:
        qs = qs.select_related('tenant', 'created_by').prefetch_related(
            'modules__contents',
            'assigned_teachers',
            'assigned_groups',
        )
    
    return qs


def _ensure_content_unlocked(request, course: Course, content: Content):
    if request.user.role in ["SCHOOL_ADMIN", "SUPER_ADMIN"]:
        return None
    lock_state = get_content_lock_state(course, str(content.id), request.user.id)
    if lock_state.is_locked:
        return Response(
            {
                "error": lock_state.lock_reason or "This lesson is locked.",
                "code": "CONTENT_LOCKED",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_dashboard(request):
    """
    Teacher dashboard data: stats, continue-learning, deadlines.
    """
    user = request.user
    courses = _teacher_assigned_courses_qs(request)
    total_courses = courses.count()

    # Overall progress: completed contents across assigned courses
    total_contents = Content.objects.filter(
        module__course__in=courses, is_active=True
    ).count()
    completed_contents = TeacherProgress.objects.filter(
        teacher=user,
        course__in=courses,
        content__isnull=False,
        status="COMPLETED",
    ).count()
    overall_progress = round((completed_contents / total_contents) * 100.0, 2) if total_contents else 0.0

    # Completed courses: course where completed contents == total contents (and total>0)
    completed_course_count = 0
    if total_courses:
        for course in courses:
            c_total = Content.objects.filter(module__course=course, is_active=True).count()
            if c_total == 0:
                continue
            c_completed = TeacherProgress.objects.filter(
                teacher=user,
                course=course,
                content__isnull=False,
                status="COMPLETED",
            ).count()
            if c_completed >= c_total:
                completed_course_count += 1

    # Assignments for assigned courses
    assignments = Assignment.objects.filter(course__in=courses, is_active=True)
    submissions = AssignmentSubmission.objects.filter(teacher=user, assignment__in=assignments)
    submitted_or_graded_ids = submissions.filter(status__in=["SUBMITTED", "GRADED"]).values_list("assignment_id", flat=True)
    pending_assignments = assignments.exclude(id__in=submitted_or_graded_ids).count()

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
    for course in courses.exclude(deadline__isnull=True).order_by("deadline")[:10]:
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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_calendar(request):
    """
    Returns a 3-7 day teaching plan window (default 5 days) with timeline events.
    """
    courses = _teacher_assigned_courses_qs(request)
    days_raw = request.GET.get("days") or 5
    try:
        days = int(days_raw)
    except (TypeError, ValueError):
        days = 5
    payload = build_teacher_calendar_window(
        request.user,
        courses,
        start_date_raw=request.GET.get("start_date"),
        days=days,
    )
    return Response(payload, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_gamification_summary(request):
    courses = _teacher_assigned_courses_qs(request)
    summary = build_teacher_gamification_summary(request.user, courses)
    return Response(summary, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_claim_quest(request, quest_key: str):
    courses = _teacher_assigned_courses_qs(request)
    try:
        summary = claim_quest_reward(request.user, courses, quest_key)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except PermissionError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(summary, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def progress_start(request, content_id):
    content = get_object_or_404(
        Content,
        id=content_id,
        is_active=True,
        module__course__tenant=request.tenant,
        module__course__is_published=True,
        module__course__is_active=True,
    )
    course = content.module.course
    if not _teacher_assigned_to_course(request.user, course):
        return Response({"error": "Not assigned to this course"}, status=status.HTTP_403_FORBIDDEN)
    lock_response = _ensure_content_unlocked(request, course, content)
    if lock_response:
        return lock_response

    obj, _created = TeacherProgress.objects.get_or_create(
        teacher=request.user,
        course=course,
        content=content,
        defaults={"status": "IN_PROGRESS", "started_at": _utcnow()},
    )
    if obj.status == "NOT_STARTED":
        obj.status = "IN_PROGRESS"
    if not obj.started_at:
        obj.started_at = _utcnow()
    obj.save()
    return Response(TeacherProgressSerializer(obj).data, status=status.HTTP_200_OK)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def progress_update(request, content_id):
    content = get_object_or_404(
        Content,
        id=content_id,
        is_active=True,
        module__course__tenant=request.tenant,
        module__course__is_published=True,
        module__course__is_active=True,
    )
    course = content.module.course
    if not _teacher_assigned_to_course(request.user, course):
        return Response({"error": "Not assigned to this course"}, status=status.HTTP_403_FORBIDDEN)
    lock_response = _ensure_content_unlocked(request, course, content)
    if lock_response:
        return lock_response

    obj, _created = TeacherProgress.objects.get_or_create(
        teacher=request.user,
        course=course,
        content=content,
        defaults={"status": "IN_PROGRESS", "started_at": _utcnow()},
    )

    video_seconds = request.data.get("video_progress_seconds")
    progress_pct = request.data.get("progress_percentage")

    if video_seconds is not None:
        try:
            video_seconds = int(video_seconds)
        except (TypeError, ValueError):
            return Response({"error": "video_progress_seconds must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        if video_seconds < 0:
            return Response({"error": "video_progress_seconds cannot be negative"}, status=status.HTTP_400_BAD_REQUEST)
        obj.video_progress_seconds = video_seconds
        
        # Auto-calculate progress_percentage from video duration
        if content.duration and content.duration > 0:
            calculated_pct = min(100.0, (video_seconds / content.duration) * 100)
            obj.progress_percentage = calculated_pct
            
            # Auto-complete when >= 95% watched (accounts for minor timing differences)
            if calculated_pct >= 95 and obj.status != "COMPLETED":
                obj.status = "COMPLETED"
                obj.completed_at = _utcnow()
                logger.info(f"[PROGRESS] Auto-completed content={content_id} teacher={request.user.id} "
                           f"video_seconds={video_seconds} duration={content.duration} pct={calculated_pct:.1f}%")
        
    if progress_pct is not None:
        try:
            progress_pct = float(progress_pct)
        except (TypeError, ValueError):
            return Response({"error": "progress_percentage must be a number"}, status=status.HTTP_400_BAD_REQUEST)
        if progress_pct < 0 or progress_pct > 100:
            return Response({"error": "progress_percentage must be between 0 and 100"}, status=status.HTTP_400_BAD_REQUEST)
        obj.progress_percentage = progress_pct

    if obj.status == "NOT_STARTED":
        obj.status = "IN_PROGRESS"
    if not obj.started_at:
        obj.started_at = _utcnow()

    obj.save()
    
    logger.info(f"[PROGRESS] Updated content={content_id} teacher={request.user.id} "
               f"video_seconds={obj.video_progress_seconds} pct={obj.progress_percentage} status={obj.status}")
    
    return Response(TeacherProgressSerializer(obj).data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def progress_complete(request, content_id):
    content = get_object_or_404(
        Content,
        id=content_id,
        is_active=True,
        module__course__tenant=request.tenant,
        module__course__is_published=True,
        module__course__is_active=True,
    )
    course = content.module.course
    if not _teacher_assigned_to_course(request.user, course):
        return Response({"error": "Not assigned to this course"}, status=status.HTTP_403_FORBIDDEN)
    lock_response = _ensure_content_unlocked(request, course, content)
    if lock_response:
        return lock_response

    # Block completion if VIDEO content hasn't finished processing
    if content.content_type == "VIDEO":
        asset = getattr(content, "video_asset", None)
        if not asset or asset.status != "READY":
            return Response(
                {"error": "Video is not ready yet. Please wait for processing to complete."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    obj, _created = TeacherProgress.objects.get_or_create(
        teacher=request.user,
        course=course,
        content=content,
        defaults={"status": "COMPLETED", "started_at": _utcnow(), "completed_at": _utcnow(), "progress_percentage": 100},
    )
    obj.status = "COMPLETED"
    obj.progress_percentage = 100
    if not obj.started_at:
        obj.started_at = _utcnow()
    obj.completed_at = _utcnow()
    obj.save()
    return Response(TeacherProgressSerializer(obj).data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def assignment_list(request):
    """
    List assignments for the teacher's assigned courses.
    Supports ?status=PENDING|SUBMITTED|GRADED.
    """
    status_filter = request.GET.get("status")
    courses = _teacher_assigned_courses_qs(request)
    qs = (
        Assignment.objects.filter(course__in=courses, is_active=True)
        .select_related("course")
        .select_related("quiz")
    )

    # Prefetch teacher submissions (both regular and quiz)
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
                setattr(a, "_submission_for_teacher", submissions_map.get(a.id))
                filtered.append(a)
        serializer = TeacherAssignmentListSerializer(filtered, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    # Attach submission for serializer
    items = []
    for a in qs:
        setattr(a, "_submission_for_teacher", submissions_map.get(a.id))
        items.append(a)
    serializer = TeacherAssignmentListSerializer(items, many=True, context={"request": request})
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def assignment_submit(request, assignment_id):
    """
    Submit/update teacher assignment submission.
    """
    assignment = get_object_or_404(
        Assignment,
        id=assignment_id,
        is_active=True,
        course__tenant=request.tenant,
        course__is_published=True,
        course__is_active=True,
    )
    if not _teacher_assigned_to_course(request.user, assignment.course):
        return Response({"error": "Not assigned to this course"}, status=status.HTTP_403_FORBIDDEN)

    submission_text = request.data.get("submission_text", "")
    file_url = request.data.get("file_url", "")

    obj, _created = AssignmentSubmission.objects.get_or_create(
        assignment=assignment,
        teacher=request.user,
        defaults={"submission_text": submission_text, "file_url": file_url, "status": "SUBMITTED"},
    )
    obj.submission_text = submission_text
    obj.file_url = file_url
    obj.status = "SUBMITTED"
    obj.save()

    return Response(TeacherAssignmentSubmissionSerializer(obj).data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def assignment_submission_detail(request, assignment_id):
    assignment = get_object_or_404(
        Assignment,
        id=assignment_id,
        is_active=True,
        course__tenant=request.tenant,
    )
    if not _teacher_assigned_to_course(request.user, assignment.course):
        return Response({"error": "Not assigned to this course"}, status=status.HTTP_403_FORBIDDEN)

    submission = get_object_or_404(AssignmentSubmission, assignment=assignment, teacher=request.user)
    return Response(TeacherAssignmentSubmissionSerializer(submission).data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def quiz_detail(request, assignment_id):
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
    if not _teacher_assigned_to_course(request.user, assignment.course):
        return Response({"error": "Not assigned to this course"}, status=status.HTTP_403_FORBIDDEN)

    quiz = getattr(assignment, "quiz", None)
    if not quiz:
        return Response({"error": "Quiz not found for assignment"}, status=status.HTTP_404_NOT_FOUND)

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
@teacher_or_admin
@tenant_required
def quiz_submit(request, assignment_id):
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
    if not _teacher_assigned_to_course(request.user, assignment.course):
        return Response({"error": "Not assigned to this course"}, status=status.HTTP_403_FORBIDDEN)

    quiz = getattr(assignment, "quiz", None)
    if not quiz:
        return Response({"error": "Quiz not found for assignment"}, status=status.HTTP_404_NOT_FOUND)

    answers = request.data.get("answers") or {}
    if not isinstance(answers, dict):
        return Response({"error": "answers must be an object"}, status=status.HTTP_400_BAD_REQUEST)

    # Limit answers payload size: max 200 keys, each value must be a flat dict
    max_answers = 200
    if len(answers) > max_answers:
        return Response({"error": f"Too many answers (max {max_answers})"}, status=status.HTTP_400_BAD_REQUEST)
    for key, val in answers.items():
        if not isinstance(val, dict):
            return Response({"error": f"Each answer must be an object, got {type(val).__name__} for '{key}'"}, status=status.HTTP_400_BAD_REQUEST)
        # Reject nested objects. Allow option_indices as a flat list for multi-select MCQ.
        for inner_key, inner_val in val.items():
            if isinstance(inner_val, dict):
                return Response({"error": "Answer values cannot contain nested objects"}, status=status.HTTP_400_BAD_REQUEST)
            if isinstance(inner_val, list):
                if inner_key != "option_indices":
                    return Response({"error": "Only option_indices may be an array value"}, status=status.HTTP_400_BAD_REQUEST)
                if any(isinstance(v, (dict, list)) for v in inner_val):
                    return Response({"error": "option_indices must be a flat array"}, status=status.HTTP_400_BAD_REQUEST)

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
        defaults={"answers": answers},
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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_search(request):
    """
    Global search across courses and assignments for the current teacher.
    Query param: q (required, min 2 chars)
    """
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return Response({"courses": [], "assignments": []})

    courses_qs = _teacher_assigned_courses_qs(request)
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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def course_certificate(request, course_id):
    """
    Generate and download a completion certificate for a course.
    
    The teacher must have completed the course (100% progress) to download.
    Tenant must have the 'certificates' feature enabled.
    """
    from django.http import FileResponse
    from .certificate_service import generate_certificate_pdf, get_certificate_filename
    
    # Check if tenant has certificates feature enabled
    tenant = request.tenant
    if not getattr(tenant, 'feature_certificates', False):
        return Response(
            {"error": "Certificates are not enabled for your organization."},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Get the course
    # Note: Course uses TenantSoftDeleteManager - no need for tenant= filter
    course = get_object_or_404(
        Course,
        id=course_id,
        is_active=True,
        is_published=True,
    )
    
    # Check if teacher is assigned to the course
    if not _teacher_assigned_to_course(request.user, course):
        return Response(
            {"error": "You are not assigned to this course."},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Get course progress
    progress = TeacherProgress.objects.filter(
        teacher=request.user,
        course=course,
        content__isnull=True,  # Course-level progress (not content-level)
    ).first()
    
    # If no course-level progress exists, calculate from content
    if not progress:
        # Check content-level progress
        # Note: Content is related via Course → modules → contents, not directly
        from apps.courses.models import Content
        total_contents = Content.objects.filter(module__course=course, is_active=True).count()
        if total_contents == 0:
            return Response(
                {"error": "This course has no content to complete."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        completed_contents = TeacherProgress.objects.filter(
            teacher=request.user,
            course=course,
            content__isnull=False,
            status='COMPLETED',
        ).count()
        
        progress_percentage = (completed_contents / total_contents) * 100
        completion_date = _utcnow()
        
        # Get the last completion date from content progress
        last_completed = TeacherProgress.objects.filter(
            teacher=request.user,
            course=course,
            content__isnull=False,
            status='COMPLETED',
        ).order_by('-completed_at').first()
        
        if last_completed and last_completed.completed_at:
            completion_date = last_completed.completed_at
    else:
        progress_percentage = float(progress.progress_percentage)
        completion_date = progress.completed_at or _utcnow()
    
    # Check if course is completed (100% or close to it)
    if progress_percentage < 99.9:
        return Response(
            {"error": f"You have not completed this course yet. Progress: {progress_percentage:.1f}%"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get tenant logo path if available
    logo_path = None
    if tenant.logo and hasattr(tenant.logo, 'path'):
        try:
            logo_path = tenant.logo.path
        except Exception:
            pass  # Logo not available locally
    
    # Generate certificate
    certificate_id = f"{str(course_id)[:8]}-{str(request.user.id)[:8]}"
    
    pdf_buffer = generate_certificate_pdf(
        teacher_name=request.user.get_full_name(),
        course_title=course.title,
        completion_date=completion_date,
        tenant_name=tenant.name,
        tenant_logo_path=logo_path,
        primary_color=tenant.primary_color or "#1F4788",
        certificate_id=certificate_id,
    )
    
    filename = get_certificate_filename(request.user.get_full_name(), course.title)
    
    response = FileResponse(
        pdf_buffer,
        content_type='application/pdf',
        as_attachment=True,
        filename=filename,
    )
    
    return response
