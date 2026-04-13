# apps/reports/manager_views.py

"""
Manager Dashboard API endpoints.

These views serve HODs, IB Coordinators, and School Admins with
aggregated views of team progress, overdue assignments, compliance,
and skill gaps.
"""

import logging
from datetime import datetime, timezone as dt_timezone

from django.db.models import Avg, Count, F, Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.courses.models import Course
from apps.progress.certification_models import TeacherCertification
from apps.progress.completion_metrics import build_teacher_course_snapshots
from apps.progress.models import Assignment, AssignmentSubmission, QuizSubmission
from apps.progress.skills_models import TeacherSkill
from apps.users.models import User
from utils.decorators import admin_only, teacher_or_admin, tenant_required
from utils.helpers import course_assigned_teachers, tenant_teachers_qs

logger = logging.getLogger(__name__)


def _utcnow():
    return datetime.now(dt_timezone.utc)


def _get_managed_teachers(request):
    """
    Get teachers managed by the requesting user.
    - SCHOOL_ADMIN / SUPER_ADMIN: all teachers in the tenant.
    - HOD: teachers in the same department.
    - IB_COORDINATOR: all teachers in the tenant.
    """
    user = request.user
    teachers = tenant_teachers_qs(request.tenant)

    if user.role == 'HOD' and user.department:
        teachers = teachers.filter(department=user.department)

    # Support ?department= filter for admins
    department = request.GET.get("department")
    if department and user.role in ('SCHOOL_ADMIN', 'SUPER_ADMIN', 'IB_COORDINATOR'):
        teachers = teachers.filter(department__iexact=department)

    return teachers


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def manager_team_progress(request):
    """
    Aggregated progress for teachers under the manager.

    Returns per-teacher summary: total assigned courses, completed courses,
    overall progress percentage.

    Query params:
      - department: filter by department (optional)
    """
    teachers = _get_managed_teachers(request).prefetch_related(
        'assigned_courses', 'teacher_groups__courses',
    )
    teacher_ids = list(teachers.values_list("id", flat=True))

    if not teacher_ids:
        return Response({"results": [], "summary": {}}, status=status.HTTP_200_OK)

    # Get all active published courses for this tenant
    courses = Course.objects.filter(is_active=True, is_published=True)
    course_ids = list(courses.values_list("id", flat=True))

    # Build completion snapshots for all teacher-course combinations
    snapshots = build_teacher_course_snapshots(course_ids, teacher_ids)

    # Aggregate per teacher
    teacher_data = []
    total_completion = 0.0

    for teacher in teachers.order_by("last_name", "first_name"):
        # Find which courses are assigned to this teacher
        assigned_courses = courses.filter(
            Q(assigned_to_all=True)
            | Q(assigned_teachers=teacher)
            | Q(assigned_groups__in=teacher.teacher_groups.all())
        ).distinct()

        assigned_count = assigned_courses.count()
        completed_count = 0
        total_content = 0
        completed_content = 0

        for course in assigned_courses:
            key = (str(course.id), str(teacher.id))
            snapshot = snapshots.get(key)
            if snapshot:
                if snapshot.status == 'COMPLETED':
                    completed_count += 1
                total_content += snapshot.total_content_count
                completed_content += snapshot.completed_content_count

        progress_pct = round(
            (completed_content / total_content) * 100, 2
        ) if total_content > 0 else 0.0
        total_completion += progress_pct

        teacher_data.append({
            "teacher_id": str(teacher.id),
            "teacher_name": teacher.get_full_name() or teacher.email,
            "teacher_email": teacher.email,
            "department": teacher.department,
            "assigned_courses": assigned_count,
            "completed_courses": completed_count,
            "progress_percentage": progress_pct,
        })

    avg_progress = round(total_completion / len(teacher_data), 2) if teacher_data else 0.0

    summary = {
        "total_teachers": len(teacher_data),
        "average_progress": avg_progress,
        "fully_completed_teachers": sum(
            1 for t in teacher_data
            if t['assigned_courses'] > 0 and t['completed_courses'] == t['assigned_courses']
        ),
    }

    return Response(
        {"results": teacher_data, "summary": summary},
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def manager_overdue(request):
    """
    Teachers with overdue course assignments.
    A course is overdue if it has a deadline that has passed and the teacher
    has not completed it.

    Query params:
      - department: filter by department (optional)
    """
    teachers = _get_managed_teachers(request).prefetch_related(
        'assigned_courses', 'teacher_groups__courses',
    )
    teacher_ids = list(teachers.values_list("id", flat=True))
    now = _utcnow()
    today = now.date()

    # Courses with deadlines that have passed
    overdue_courses = Course.objects.filter(
        is_active=True,
        is_published=True,
        deadline__lt=today,
    )
    course_ids = list(overdue_courses.values_list("id", flat=True))

    if not course_ids or not teacher_ids:
        return Response({"results": [], "total_overdue": 0}, status=status.HTTP_200_OK)

    snapshots = build_teacher_course_snapshots(course_ids, teacher_ids)

    results = []
    for teacher in teachers:
        assigned = overdue_courses.filter(
            Q(assigned_to_all=True)
            | Q(assigned_teachers=teacher)
            | Q(assigned_groups__in=teacher.teacher_groups.all())
        ).distinct()

        for course in assigned:
            key = (str(course.id), str(teacher.id))
            snapshot = snapshots.get(key)
            snap_status = snapshot.status if snapshot else 'NOT_STARTED'
            if snap_status != 'COMPLETED':
                days_overdue = (today - course.deadline).days
                results.append({
                    "teacher_id": str(teacher.id),
                    "teacher_name": teacher.get_full_name() or teacher.email,
                    "teacher_email": teacher.email,
                    "department": teacher.department,
                    "course_id": str(course.id),
                    "course_title": course.title,
                    "deadline": str(course.deadline),
                    "days_overdue": days_overdue,
                    "status": snap_status,
                })

    # Sort by days_overdue descending
    results.sort(key=lambda r: -r['days_overdue'])

    return Response(
        {"results": results, "total_overdue": len(results)},
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def manager_compliance(request):
    """
    Certification compliance status across the team.

    Returns:
    - Teachers with all required certifications active
    - Teachers missing or with expired certifications
    - Certifications expiring soon (within 30 days)

    Query params:
      - department: filter by department (optional)
    """
    from apps.progress.certification_models import CertificationType
    from django.utils import timezone as dj_timezone

    teachers = _get_managed_teachers(request)
    now = dj_timezone.now()
    threshold_30d = now + dj_timezone.timedelta(days=30)

    # Get all certification types for this tenant
    cert_types = list(CertificationType.objects.all())

    if not cert_types:
        return Response({
            "results": [],
            "summary": {"total_teachers": teachers.count(), "fully_compliant": 0, "non_compliant": 0},
        }, status=status.HTTP_200_OK)

    # Get all active teacher certifications
    active_certs = TeacherCertification.objects.filter(
        teacher__in=teachers,
        status__in=['active', 'pending_renewal'],
    ).select_related('certification_type', 'teacher')

    # Build a lookup: teacher_id -> set of cert_type_ids they hold (active)
    teacher_cert_map = {}
    for tc in active_certs:
        teacher_cert_map.setdefault(str(tc.teacher_id), set()).add(str(tc.certification_type_id))

    cert_type_ids = {str(ct.id) for ct in cert_types}
    cert_type_names = {str(ct.id): ct.name for ct in cert_types}

    # Expiring soon
    expiring_soon_qs = active_certs.filter(expires_at__lte=threshold_30d, expires_at__gt=now)
    expiring_soon = [
        {
            "teacher_name": tc.teacher.get_full_name() or tc.teacher.email,
            "teacher_email": tc.teacher.email,
            "certification_name": tc.certification_type.name,
            "expires_at": tc.expires_at.isoformat(),
            "days_until_expiry": tc.days_until_expiry,
        }
        for tc in expiring_soon_qs
    ]

    results = []
    fully_compliant = 0

    for teacher in teachers:
        held = teacher_cert_map.get(str(teacher.id), set())
        missing = cert_type_ids - held
        is_compliant = len(missing) == 0

        if is_compliant:
            fully_compliant += 1

        results.append({
            "teacher_id": str(teacher.id),
            "teacher_name": teacher.get_full_name() or teacher.email,
            "teacher_email": teacher.email,
            "department": teacher.department,
            "is_compliant": is_compliant,
            "certifications_held": len(held),
            "certifications_required": len(cert_type_ids),
            "missing_certifications": [
                cert_type_names[ct_id] for ct_id in missing
            ],
        })

    results.sort(key=lambda r: (r['is_compliant'], r['teacher_name']))

    return Response({
        "results": results,
        "expiring_soon": expiring_soon,
        "summary": {
            "total_teachers": len(results),
            "fully_compliant": fully_compliant,
            "non_compliant": len(results) - fully_compliant,
            "expiring_within_30_days": len(expiring_soon),
        },
    }, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def manager_skills_overview(request):
    """
    Team skill levels vs targets.

    Returns aggregated skill data showing:
    - Average current level vs target across the team per skill
    - Number of teachers at/above target, and below target
    - Overall gap summary

    Query params:
      - department: filter by department (optional)
      - category: filter by skill category (optional)
    """
    teachers = _get_managed_teachers(request)
    teacher_ids = set(str(t.id) for t in teachers)

    qs = TeacherSkill.objects.select_related('skill', 'teacher').filter(
        teacher__in=teachers,
    )

    category = request.GET.get("category")
    if category:
        qs = qs.filter(skill__category__iexact=category)

    # Aggregate by skill
    skill_data = {}
    for ts in qs:
        skill_id = str(ts.skill_id)
        if skill_id not in skill_data:
            skill_data[skill_id] = {
                "skill_id": skill_id,
                "skill_name": ts.skill.name,
                "skill_category": ts.skill.category,
                "level_required": ts.skill.level_required,
                "teachers_assessed": 0,
                "total_current_level": 0,
                "total_target_level": 0,
                "at_or_above_target": 0,
                "below_target": 0,
                "teacher_details": [],
            }

        entry = skill_data[skill_id]
        entry["teachers_assessed"] += 1
        entry["total_current_level"] += ts.current_level
        entry["total_target_level"] += ts.target_level

        if ts.current_level >= ts.target_level:
            entry["at_or_above_target"] += 1
        else:
            entry["below_target"] += 1

        entry["teacher_details"].append({
            "teacher_id": str(ts.teacher_id),
            "teacher_name": ts.teacher.get_full_name() or ts.teacher.email,
            "current_level": ts.current_level,
            "target_level": ts.target_level,
            "has_gap": ts.has_gap,
        })

    # Compute averages and finalize
    results = []
    total_gaps = 0
    for skill_id, data in skill_data.items():
        assessed = data["teachers_assessed"]
        data["avg_current_level"] = round(data["total_current_level"] / assessed, 2) if assessed else 0
        data["avg_target_level"] = round(data["total_target_level"] / assessed, 2) if assessed else 0
        total_gaps += data["below_target"]

        # Remove temporary aggregation fields
        del data["total_current_level"]
        del data["total_target_level"]

        results.append(data)

    # Sort by number of gaps descending (most gaps first)
    results.sort(key=lambda r: (-r['below_target'], r['skill_name']))

    summary = {
        "total_skills_tracked": len(results),
        "total_teacher_skill_gaps": total_gaps,
        "total_teachers": len(teacher_ids),
    }

    return Response(
        {"results": results, "summary": summary},
        status=status.HTTP_200_OK,
    )
