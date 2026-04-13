# apps/academics/teacher_views.py
"""
Teacher API endpoints for academic section management.

Endpoints:
- my_classes: Teacher's assigned sections grouped by subject
- section_dashboard: 4-tab section detail (students, courses, analytics, assignments)
"""

import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q

from utils.decorators import teacher_or_admin, tenant_required
from .models import TeachingAssignment, Section
from .serializers import SectionSerializer, TeachingAssignmentSerializer

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def my_classes(request):
    """
    Teacher's assigned sections grouped by subject.

    Returns a list of teaching assignments, each with:
    - Subject info
    - List of sections with student count, course count, avg progress

    Used for the "My Classes" overview page.
    """
    from apps.users.models import User
    from apps.courses.models import Course

    academic_year = request.tenant.current_academic_year

    assignments = TeachingAssignment.objects.filter(
        tenant=request.tenant,
        teacher=request.user,
        academic_year=academic_year,
    ).select_related('subject').prefetch_related(
        'sections__grade__grade_band',
    ).order_by('subject__department', 'subject__name')

    result = []
    for ta in assignments:
        sections_data = []
        for section in ta.sections.select_related('grade__grade_band', 'class_teacher').order_by('grade__order', 'name'):
            student_count = User.objects.filter(
                section_fk=section, role='STUDENT',
                is_deleted=False, is_active=True,
            ).count()

            # Count only this teacher's courses for this section
            course_count = Course.objects.filter(
                target_sections=section,
                course_type='ACADEMIC',
                created_by=request.user,
                is_deleted=False,
            ).count()

            sections_data.append({
                'id': str(section.id),
                'name': section.name,
                'grade_name': section.grade.name,
                'grade_short_code': section.grade.short_code,
                'grade_band_name': section.grade.grade_band.name,
                'academic_year': section.academic_year,
                'student_count': student_count,
                'course_count': course_count,
                'class_teacher_name': (
                    section.class_teacher.get_full_name()
                    if section.class_teacher_id else None
                ),
                'is_class_teacher': ta.is_class_teacher,
            })

        result.append({
            'assignment_id': str(ta.id),
            'subject': {
                'id': str(ta.subject.id),
                'name': ta.subject.name,
                'code': ta.subject.code,
                'department': ta.subject.department,
            },
            'academic_year': ta.academic_year,
            'is_class_teacher': ta.is_class_teacher,
            'sections': sections_data,
        })

    return Response({
        'academic_year': academic_year,
        'assignments': result,
        'total_sections': sum(len(a['sections']) for a in result),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def section_dashboard(request, section_id):
    """
    Teacher's section dashboard with 4 tabs.

    Query params:
    - tab: 'students' | 'courses' | 'analytics' | 'assignments' (default: students)

    Access control: teacher must have a TeachingAssignment for this section,
    or be SCHOOL_ADMIN / SUPER_ADMIN.
    """
    section = get_object_or_404(
        Section.objects.select_related('grade__grade_band'),
        pk=section_id,
        tenant=request.tenant,
    )

    # Access check: teacher must have assignment for this section
    if request.user.role in ('TEACHER', 'HOD', 'IB_COORDINATOR'):
        has_access = TeachingAssignment.objects.filter(
            tenant=request.tenant,
            teacher=request.user,
            sections=section,
            academic_year=request.tenant.current_academic_year,
        ).exists()
        if not has_access:
            return Response(
                {'error': 'You do not have a teaching assignment for this section.'},
                status=status.HTTP_403_FORBIDDEN,
            )

    tab = request.GET.get('tab', 'students')
    section_info = {
        'id': str(section.id),
        'name': section.name,
        'grade_name': section.grade.name,
        'grade_short_code': section.grade.short_code,
        'grade_band_name': section.grade.grade_band.name,
        'academic_year': section.academic_year,
    }

    # --- Students Tab ---
    if tab == 'students':
        from apps.users.models import User
        students = User.objects.filter(
            section_fk=section, role='STUDENT',
            is_deleted=False, is_active=True,
        ).order_by('last_name', 'first_name')

        search = request.GET.get('search')
        if search:
            students = students.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
                | Q(student_id__icontains=search)
            )

        # Pagination
        try:
            limit = min(int(request.GET.get('limit', 50)), 200)
            offset = int(request.GET.get('offset', 0))
        except (ValueError, TypeError):
            limit, offset = 50, 0

        total = students.count()
        page = students[offset:offset + limit]

        student_data = []
        for s in page:
            student_data.append({
                'id': str(s.id),
                'first_name': s.first_name,
                'last_name': s.last_name,
                'email': s.email,
                'student_id': s.student_id,
                'is_active': s.is_active,
                'last_login': s.last_login.isoformat() if s.last_login else None,
            })

        return Response({
            'section': section_info,
            'tab': 'students',
            'students': student_data,
            'total': total,
            'limit': limit,
            'offset': offset,
        })

    # --- Courses Tab ---
    elif tab == 'courses':
        from apps.courses.models import Course

        courses = Course.objects.filter(
            target_sections=section,
            course_type='ACADEMIC',
            is_deleted=False,
        )

        # Teachers see only their courses; admins see all
        if request.user.role in ('TEACHER', 'HOD', 'IB_COORDINATOR'):
            courses = courses.filter(created_by=request.user)

        course_data = []
        for c in courses:
            course_data.append({
                'id': str(c.id),
                'title': c.title,
                'slug': c.slug,
                'is_published': c.is_published,
                'is_active': c.is_active,
                'created_at': c.created_at.isoformat(),
                'student_count': c.assigned_students.count(),
            })

        return Response({
            'section': section_info,
            'tab': 'courses',
            'courses': course_data,
            'total': len(course_data),
        })

    # --- Analytics Tab ---
    elif tab == 'analytics':
        from apps.users.models import User

        student_count = User.objects.filter(
            section_fk=section, role='STUDENT',
            is_deleted=False, is_active=True,
        ).count()

        # Active students (logged in within last 7 days)
        from django.utils import timezone
        from datetime import timedelta
        seven_days_ago = timezone.now() - timedelta(days=7)
        active_count = User.objects.filter(
            section_fk=section, role='STUDENT',
            is_deleted=False, is_active=True,
            last_login__gte=seven_days_ago,
        ).count()

        from apps.courses.models import Course
        course_count = Course.objects.filter(
            target_sections=section, course_type='ACADEMIC',
            is_deleted=False,
        ).count()

        return Response({
            'section': section_info,
            'tab': 'analytics',
            'stats': {
                'total_students': student_count,
                'active_students_7d': active_count,
                'inactive_students': student_count - active_count,
                'total_courses': course_count,
            },
        })

    # --- Assignments Tab ---
    elif tab == 'assignments':
        from apps.courses.models import Course

        # Get courses targeting this section
        course_filter = {
            'target_sections': section,
            'course_type': 'ACADEMIC',
            'is_deleted': False,
        }
        if request.user.role in ('TEACHER', 'HOD', 'IB_COORDINATOR'):
            course_filter['created_by'] = request.user

        course_ids = Course.objects.filter(**course_filter).values_list('id', flat=True)

        # Get assignments for those courses
        try:
            from apps.progress.models import Assignment
            assignments = Assignment.objects.filter(
                course_id__in=course_ids, is_active=True,
            ).order_by('-created_at')[:50]

            assignment_data = [{
                'id': str(a.id),
                'title': a.title,
                'course_id': str(a.course_id),
                'due_date': a.due_date.isoformat() if a.due_date else None,
                'max_score': str(a.max_score),
                'is_quiz': a.is_quiz if hasattr(a, 'is_quiz') else False,
            } for a in assignments]
        except (ImportError, LookupError):
            # Assignment model may not exist yet
            assignment_data = []

        return Response({
            'section': section_info,
            'tab': 'assignments',
            'assignments': assignment_data,
            'total': len(assignment_data),
        })

    return Response({'error': f'Invalid tab: {tab}'}, status=status.HTTP_400_BAD_REQUEST)
