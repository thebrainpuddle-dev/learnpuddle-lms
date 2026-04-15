"""
Parent Portal API views.

Endpoints:
    POST /api/v1/parent/auth/request-link/              — Request magic link email
    POST /api/v1/parent/auth/verify/                     — Verify token, create session
    POST /api/v1/parent/auth/refresh/                    — Refresh session tokens
    POST /api/v1/parent/auth/logout/                     — Deactivate session
    GET  /api/v1/parent/children/                        — List linked students
    GET  /api/v1/parent/children/<child_id>/overview/    — Child dashboard data
"""

import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from apps.courses.parent_auth import parent_required
from apps.courses.parent_email import send_parent_magic_link
from apps.courses.parent_models import ParentMagicToken, ParentSession
from apps.users.models import User

logger = logging.getLogger(__name__)


# ─── Throttle classes ────────────────────────────────────────────────────────

class ParentMagicLinkThrottle(AnonRateThrottle):
    rate = '3/hour'


# ─── Auth: Request Magic Link ───────────────────────────────────────────────

@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([ParentMagicLinkThrottle])
def parent_request_magic_link(request):
    """
    Request a magic link email for parent portal access.

    Accepts {"email": "parent@example.com"}.
    Always returns success to prevent email enumeration.
    """
    email = (request.data.get("email") or "").strip().lower()
    if not email:
        return Response(
            {"error": "Email is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return Response(
            {"message": "If an account exists, a login link has been sent."},
            status=status.HTTP_200_OK,
        )

    # Find students with matching parent_email in this tenant
    students = User.objects.filter(
        tenant=tenant,
        role='STUDENT',
        is_active=True,
        is_deleted=False,
        parent_email__iexact=email,
    )

    if students.exists():
        # Create magic token (15-minute expiry)
        token_str = secrets.token_urlsafe(48)
        ParentMagicToken.objects.create(
            tenant=tenant,
            parent_email=email,
            token=token_str,
            expires_at=timezone.now() + timedelta(minutes=15),
        )

        # Send email (fire-and-forget; failure logged inside)
        send_parent_magic_link(parent_email=email, tenant=tenant, token=token_str)

    # Always return success to prevent enumeration
    return Response(
        {"message": "If an account exists, a login link has been sent."},
        status=status.HTTP_200_OK,
    )


# ─── Auth: Verify Token ─────────────────────────────────────────────────────

@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def parent_verify_token(request):
    """
    Verify a magic link token and create a parent session.

    Accepts {"token": "<token_string>"}.
    Returns session credentials and linked children on success.
    """
    token_str = (request.data.get("token") or "").strip()
    if not token_str:
        return Response(
            {"error": "Token is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        magic_token = ParentMagicToken.objects.select_related('tenant').get(
            token=token_str,
        )
    except ParentMagicToken.DoesNotExist:
        return Response(
            {"error": "Invalid or expired link. Please request a new one."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not magic_token.is_valid:
        return Response(
            {"error": "This link has already been used or has expired. Please request a new one."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate tenant matches (prevent cross-tenant token use)
    if hasattr(request, 'tenant') and request.tenant and request.tenant != magic_token.tenant:
        return Response(
            {"error": "Invalid or expired link. Please request a new one."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Mark token as used
    magic_token.is_used = True
    magic_token.save(update_fields=['is_used'])

    tenant = magic_token.tenant
    parent_email = magic_token.parent_email

    # Find all linked students
    students = User.objects.filter(
        tenant=tenant,
        role='STUDENT',
        is_active=True,
        is_deleted=False,
        parent_email__iexact=parent_email,
    )

    # Create session
    session = ParentSession.create_session(
        tenant=tenant,
        parent_email=parent_email,
        students=students,
    )

    # Build children list for response
    children = []
    for student in students:
        children.append({
            "id": str(student.id),
            "first_name": student.first_name,
            "last_name": student.last_name,
            "grade_level": student.grade_level,
            "section": student.section,
        })

    return Response({
        "session_token": session.session_token,
        "refresh_token": session.refresh_token,
        "expires_at": session.expires_at.isoformat(),
        "parent_email": parent_email,
        "children": children,
    })


# ─── Auth: Refresh Session ──────────────────────────────────────────────────

@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def parent_refresh_session(request):
    """
    Refresh a parent session using the refresh token.

    Accepts {"refresh_token": "<token>"}.
    Returns new session and refresh tokens.
    """
    refresh_token = (request.data.get("refresh_token") or "").strip()
    if not refresh_token:
        return Response(
            {"error": "refresh_token is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        old_session = ParentSession.objects.select_related('tenant').prefetch_related(
            'students',
        ).get(
            refresh_token=refresh_token,
            is_active=True,
        )
    except ParentSession.DoesNotExist:
        return Response(
            {"error": "Invalid refresh token. Please log in again."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    # Check refresh window (7 days from session creation)
    refresh_deadline = old_session.created_at + timedelta(days=7)
    if timezone.now() > refresh_deadline:
        old_session.is_active = False
        old_session.save(update_fields=['is_active'])
        return Response(
            {"error": "Refresh token expired. Please log in again."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    # Deactivate old session
    old_session.is_active = False
    old_session.save(update_fields=['is_active'])

    # Create new session with the same students
    students = old_session.students.all()
    new_session = ParentSession.create_session(
        tenant=old_session.tenant,
        parent_email=old_session.parent_email,
        students=students,
    )

    return Response({
        "session_token": new_session.session_token,
        "refresh_token": new_session.refresh_token,
        "expires_at": new_session.expires_at.isoformat(),
    })


# ─── Auth: Logout ───────────────────────────────────────────────────────────

@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@parent_required
def parent_logout(request):
    """
    Deactivate the current parent session.
    """
    session = request.parent_session
    session.is_active = False
    session.save(update_fields=['is_active'])

    return Response({"message": "Logged out successfully."})


# ─── Children List ───────────────────────────────────────────────────────────

@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
@parent_required
def parent_children_list(request):
    """
    List all children linked to the current parent session.
    """
    students = request.parent_session.students.filter(
        is_active=True,
        is_deleted=False,
    )

    children = []
    for student in students:
        children.append({
            "id": str(student.id),
            "first_name": student.first_name,
            "last_name": student.last_name,
            "email": student.email,
            "grade_level": student.grade_level,
            "section": student.section,
            "student_id": student.student_id,
        })

    return Response({"children": children})


# ─── Child Overview ──────────────────────────────────────────────────────────

@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
@parent_required
def parent_child_overview(request, child_id):
    """
    Comprehensive dashboard data for a specific child.

    Returns student info, courses with progress, assignments,
    attendance stats, study time, and recent activity.
    """
    session = request.parent_session

    # Validate child is linked to this parent session
    try:
        student = session.students.get(pk=child_id, is_active=True, is_deleted=False)
    except User.DoesNotExist:
        return Response(
            {"error": "Child not found or not linked to your account"},
            status=status.HTTP_404_NOT_FOUND,
        )

    tenant = session.tenant

    # ── Student Info ──────────────────────────────────────────────────────
    student_info = {
        "id": str(student.id),
        "first_name": student.first_name,
        "last_name": student.last_name,
        "email": student.email,
        "grade_level": student.grade_level,
        "section": student.section,
        "student_id": student.student_id,
        "enrollment_date": student.enrollment_date.isoformat() if student.enrollment_date else None,
    }

    # ── Courses with Progress ─────────────────────────────────────────────
    from apps.courses.models import Course
    from apps.progress.models import TeacherProgress

    # Get courses assigned to this student
    courses_qs = Course.objects.filter(
        tenant=tenant,
        is_active=True,
        is_published=True,
    ).filter(
        Q(assigned_to_all_students=True) | Q(assigned_students=student)
    ).distinct().order_by('title')

    courses_data = []
    for course in courses_qs:
        # Get progress records for this student in this course
        progress_records = TeacherProgress.all_objects.filter(
            tenant=tenant,
            teacher=student,
            course=course,
        )

        total_contents = course.modules.filter(
            is_active=True, is_deleted=False,
        ).aggregate(
            count=Count('contents', filter=Q(
                contents__is_active=True, contents__is_deleted=False,
            ))
        )['count'] or 0

        completed_contents = progress_records.filter(
            status='COMPLETED',
            content__isnull=False,
        ).count()

        progress_pct = 0
        if total_contents > 0:
            progress_pct = round((completed_contents / total_contents) * 100, 1)

        # Get course-level progress record
        course_progress = progress_records.filter(content__isnull=True).first()
        course_status = 'NOT_STARTED'
        if course_progress:
            course_status = course_progress.status

        courses_data.append({
            "id": str(course.id),
            "title": course.title,
            "course_type": course.course_type,
            "is_mandatory": course.is_mandatory,
            "deadline": course.deadline.isoformat() if course.deadline else None,
            "total_contents": total_contents,
            "completed_contents": completed_contents,
            "progress_percentage": progress_pct,
            "status": course_status,
            "last_accessed": (
                course_progress.last_accessed.isoformat()
                if course_progress and course_progress.last_accessed
                else None
            ),
        })

    # ── Assignments ───────────────────────────────────────────────────────
    from apps.progress.models import Assignment, AssignmentSubmission

    # Assignments from courses the student is enrolled in
    assignments_qs = Assignment.objects.filter(
        tenant=tenant,
        course__id__in=[c.id for c in courses_qs],
        is_active=True,
    ).select_related('course').order_by('-due_date')[:20]

    assignments_data = []
    for assignment in assignments_qs:
        # Check if student has submitted
        submission = AssignmentSubmission.all_objects.filter(
            assignment=assignment,
            teacher=student,
        ).first()

        assignments_data.append({
            "id": str(assignment.id),
            "title": assignment.title,
            "course_title": assignment.course.title,
            "due_date": assignment.due_date.isoformat() if assignment.due_date else None,
            "max_score": float(assignment.max_score),
            "is_mandatory": assignment.is_mandatory,
            "submission_status": submission.status if submission else "NOT_SUBMITTED",
            "score": float(submission.score) if submission and submission.score is not None else None,
        })

    # ── Attendance Stats ────────────────────────────────────────────────
    from django.db.models import Count, Q as _Q
    from apps.academics.attendance_models import Attendance

    att_qs = Attendance.objects.filter(tenant=tenant, student=student)
    att_totals = att_qs.aggregate(
        total=Count('id'),
        present=Count('id', filter=_Q(status__in=['PRESENT', 'LATE'])),
        absent=Count('id', filter=_Q(status='ABSENT')),
    )
    att_total = att_totals['total'] or 0
    att_present = att_totals['present'] or 0
    att_absent = att_totals['absent'] or 0
    att_pct = round((att_present / att_total) * 100, 1) if att_total > 0 else 0

    attendance_stats = {
        "total_days": att_total,
        "present_days": att_present,
        "absent_days": att_absent,
        "attendance_percentage": att_pct,
        "note": "" if att_total > 0 else "Attendance tracking is not yet configured.",
    }

    # ── Study Time ────────────────────────────────────────────────────────
    all_progress = TeacherProgress.all_objects.filter(
        tenant=tenant,
        teacher=student,
    )

    total_video_seconds = 0
    for p in all_progress.filter(video_progress_seconds__gt=0):
        total_video_seconds += p.video_progress_seconds

    study_time = {
        "total_video_seconds": total_video_seconds,
        "total_video_minutes": round(total_video_seconds / 60, 1),
        "courses_in_progress": all_progress.filter(
            status='IN_PROGRESS', content__isnull=True,
        ).count(),
        "courses_completed": all_progress.filter(
            status='COMPLETED', content__isnull=True,
        ).count(),
    }

    # ── Recent Activity ───────────────────────────────────────────────────
    recent_progress = TeacherProgress.all_objects.filter(
        tenant=tenant,
        teacher=student,
    ).select_related(
        'course', 'content',
    ).order_by('-last_accessed')[:10]

    recent_activity = []
    for p in recent_progress:
        activity = {
            "course_title": p.course.title if p.course else "Unknown",
            "content_title": p.content.title if p.content else None,
            "status": p.status,
            "last_accessed": p.last_accessed.isoformat() if p.last_accessed else None,
        }
        if p.completed_at:
            activity["completed_at"] = p.completed_at.isoformat()
        recent_activity.append(activity)

    return Response({
        "student": student_info,
        "courses": courses_data,
        "assignments": assignments_data,
        "attendance": attendance_stats,
        "study_time": study_time,
        "recent_activity": recent_activity,
    })


# ─── Demo Login (DEBUG only) ────────────────────────────────────────────────

@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def parent_demo_login(request):
    """
    Skip magic link flow and create a session directly.
    Only available when DEBUG=True.

    Accepts {"email": "parent@keystoneeducation.in"}.
    """
    if not getattr(settings, 'DEBUG', False):
        return Response(
            {"error": "Demo login is not available in production."},
            status=status.HTTP_404_NOT_FOUND,
        )

    email = (request.data.get("email") or "").strip().lower()
    if not email:
        return Response(
            {"error": "Email is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return Response(
            {"error": "Tenant not found"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Find students with matching parent_email
    students = User.objects.filter(
        tenant=tenant,
        role='STUDENT',
        is_active=True,
        is_deleted=False,
        parent_email__iexact=email,
    )

    if not students.exists():
        return Response(
            {"error": "No students found with this parent email."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Create session directly
    session = ParentSession.create_session(
        tenant=tenant,
        parent_email=email,
        students=students,
    )

    children = []
    for student in students:
        children.append({
            "id": str(student.id),
            "first_name": student.first_name,
            "last_name": student.last_name,
            "grade_level": student.grade_level,
            "section": student.section,
        })

    return Response({
        "session_token": session.session_token,
        "refresh_token": session.refresh_token,
        "expires_at": session.expires_at.isoformat(),
        "parent_email": email,
        "children": children,
    })
