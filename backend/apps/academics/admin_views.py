# apps/academics/admin_views.py
"""
Admin API endpoints for academic structure management.

Endpoints:
- CRUD for GradeBand, Grade, Section, Subject, TeachingAssignment
- School Overview (aggregated dashboard data)
- Section detail views (students, teachers, courses)
- Contextual CSV student import
- Student transfer between sections
- Course cloning
- Academic year promotion
"""

import csv
import io
import secrets
import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes, throttle_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from django.db import IntegrityError
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q

from utils.decorators import admin_only, tenant_required, teacher_or_admin, check_tenant_limit
from utils.audit import log_audit
from .models import GradeBand, Grade, Section, Subject, TeachingAssignment
from .serializers import (
    GradeBandSerializer, GradeSerializer, SectionSerializer,
    SubjectSerializer, TeachingAssignmentSerializer,
    TeachingAssignmentCreateSerializer,
)

logger = logging.getLogger(__name__)


def _paginate(request, queryset, default_limit=50):
    """Simple offset/limit pagination for list endpoints."""
    try:
        limit = int(request.GET.get('limit', default_limit))
        offset = int(request.GET.get('offset', 0))
    except (ValueError, TypeError):
        limit, offset = default_limit, 0
    limit = min(limit, 200)  # Cap at 200
    total = queryset.count()
    page = queryset[offset:offset + limit]
    return page, {'total': total, 'limit': limit, 'offset': offset}


# ─── GradeBand ────────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def grade_band_list_create(request):
    """List all grade bands or create a new one."""
    if request.method == 'GET':
        bands = GradeBand.objects.filter(tenant=request.tenant).annotate(
            _grade_count=Count('grades'),
        ).order_by('order')
        page, pagination = _paginate(request, bands)
        return Response({
            'data': GradeBandSerializer(page, many=True).data,
            **pagination,
        })

    serializer = GradeBandSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    band = serializer.save(tenant=request.tenant)
    log_audit('CREATE', 'GradeBand', target_id=str(band.id),
              target_repr=str(band), request=request)
    return Response(GradeBandSerializer(band).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def grade_band_detail(request, band_id):
    """Get, update, or delete a grade band."""
    band = get_object_or_404(GradeBand, pk=band_id, tenant=request.tenant)

    if request.method == 'GET':
        return Response(GradeBandSerializer(band).data)

    if request.method == 'DELETE':
        if band.grades.exists():
            return Response(
                {'error': 'Cannot delete grade band that contains grades. Remove grades first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        log_audit('DELETE', 'GradeBand', target_id=str(band_id),
                  target_repr=str(band), request=request)
        band.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # PATCH
    serializer = GradeBandSerializer(band, data=request.data, partial=True,
                                     context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    log_audit('UPDATE', 'GradeBand', target_id=str(band_id),
              target_repr=str(band), request=request)
    return Response(serializer.data)


# ─── Grade ────────────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def grade_list_create(request):
    """List grades (filterable by grade_band) or create a new one."""
    if request.method == 'GET':
        qs = Grade.objects.filter(tenant=request.tenant).select_related('grade_band').annotate(
            _student_count=Count(
                'students',
                filter=Q(students__is_deleted=False, students__is_active=True),
            ),
            _section_count=Count('sections', distinct=True),
        ).order_by('order')

        band_id = request.GET.get('grade_band')
        if band_id:
            qs = qs.filter(grade_band_id=band_id)

        page, pagination = _paginate(request, qs)
        return Response({
            'data': GradeSerializer(page, many=True).data,
            **pagination,
        })

    serializer = GradeSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    grade = serializer.save(tenant=request.tenant)
    log_audit('CREATE', 'Grade', target_id=str(grade.id),
              target_repr=str(grade), request=request)
    return Response(GradeSerializer(grade).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def grade_detail(request, grade_id):
    """Get, update, or delete a grade."""
    grade = get_object_or_404(Grade, pk=grade_id, tenant=request.tenant)

    if request.method == 'GET':
        return Response(GradeSerializer(grade).data)

    if request.method == 'DELETE':
        student_count = grade.students.filter(is_deleted=False).count()
        if student_count > 0:
            return Response(
                {'error': f'Cannot delete grade with {student_count} active students.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        log_audit('DELETE', 'Grade', target_id=str(grade_id),
                  target_repr=str(grade), request=request)
        grade.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = GradeSerializer(grade, data=request.data, partial=True,
                                 context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    log_audit('UPDATE', 'Grade', target_id=str(grade_id),
              target_repr=str(grade), request=request)
    return Response(serializer.data)


# ─── Section ──────────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def section_list_create(request):
    """List sections (filterable by grade, academic_year) or create a new one."""
    if request.method == 'GET':
        qs = Section.objects.filter(tenant=request.tenant).select_related('grade', 'class_teacher').annotate(
            _student_count=Count(
                'students',
                filter=Q(students__is_deleted=False, students__is_active=True),
            ),
        )

        grade_id = request.GET.get('grade')
        if grade_id:
            qs = qs.filter(grade_id=grade_id)

        academic_year = request.GET.get('academic_year')
        if academic_year:
            qs = qs.filter(academic_year=academic_year)
        elif request.tenant.current_academic_year:
            # Default to current academic year
            qs = qs.filter(academic_year=request.tenant.current_academic_year)

        page, pagination = _paginate(request, qs)
        return Response({
            'data': SectionSerializer(page, many=True).data,
            **pagination,
        })

    serializer = SectionSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    section = serializer.save(tenant=request.tenant)
    log_audit('CREATE', 'Section', target_id=str(section.id),
              target_repr=str(section), request=request)
    return Response(SectionSerializer(section).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def section_detail(request, section_id):
    """Get, update, or delete a section."""
    section = get_object_or_404(Section, pk=section_id, tenant=request.tenant)

    if request.method == 'GET':
        return Response(SectionSerializer(section).data)

    if request.method == 'DELETE':
        student_count = section.students.filter(is_deleted=False).count()
        if student_count > 0:
            return Response(
                {'error': f'Cannot delete section with {student_count} active students.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        log_audit('DELETE', 'Section', target_id=str(section_id),
                  target_repr=str(section), request=request)
        section.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = SectionSerializer(section, data=request.data, partial=True,
                                   context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    log_audit('UPDATE', 'Section', target_id=str(section_id),
              target_repr=str(section), request=request)
    return Response(serializer.data)


# ─── Subject ──────────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def subject_list_create(request):
    """List subjects (filterable by department) or create a new one."""
    if request.method == 'GET':
        qs = Subject.objects.filter(tenant=request.tenant).prefetch_related('applicable_grades').order_by('department', 'name')

        dept = request.GET.get('department')
        if dept:
            qs = qs.filter(department__icontains=dept)

        search = request.GET.get('search')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))

        page, pagination = _paginate(request, qs)
        return Response({
            'data': SubjectSerializer(page, many=True, context={'request': request}).data,
            **pagination,
        })

    serializer = SubjectSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    subject = serializer.save(tenant=request.tenant)
    log_audit('CREATE', 'Subject', target_id=str(subject.id),
              target_repr=str(subject), request=request)
    return Response(
        SubjectSerializer(subject, context={'request': request}).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def subject_detail(request, subject_id):
    """Get, update, or delete a subject."""
    subject = get_object_or_404(Subject, pk=subject_id, tenant=request.tenant)

    if request.method == 'GET':
        return Response(SubjectSerializer(subject, context={'request': request}).data)

    if request.method == 'DELETE':
        course_count = subject.courses.filter(is_deleted=False).count()
        if course_count > 0:
            return Response(
                {'error': f'Cannot delete subject linked to {course_count} courses.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        log_audit('DELETE', 'Subject', target_id=str(subject_id),
                  target_repr=str(subject), request=request)
        subject.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = SubjectSerializer(subject, data=request.data, partial=True,
                                   context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    log_audit('UPDATE', 'Subject', target_id=str(subject_id),
              target_repr=str(subject), request=request)
    return Response(serializer.data)


# ─── TeachingAssignment ───────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def teaching_assignment_list_create(request):
    """List teaching assignments (filterable by teacher, academic_year) or create."""
    if request.method == 'GET':
        qs = TeachingAssignment.objects.filter(tenant=request.tenant).select_related(
            'teacher', 'subject',
        ).prefetch_related('sections__grade')

        teacher_id = request.GET.get('teacher')
        if teacher_id:
            qs = qs.filter(teacher_id=teacher_id)

        academic_year = request.GET.get('academic_year')
        if academic_year:
            qs = qs.filter(academic_year=academic_year)
        elif request.tenant.current_academic_year:
            qs = qs.filter(academic_year=request.tenant.current_academic_year)

        subject_id = request.GET.get('subject')
        if subject_id:
            qs = qs.filter(subject_id=subject_id)

        page, pagination = _paginate(request, qs)
        return Response({
            'data': TeachingAssignmentSerializer(
                page, many=True, context={'request': request},
            ).data,
            **pagination,
        })

    serializer = TeachingAssignmentCreateSerializer(
        data=request.data, context={'request': request},
    )
    serializer.is_valid(raise_exception=True)
    ta = serializer.save(tenant=request.tenant)
    log_audit('CREATE', 'TeachingAssignment', target_id=str(ta.id),
              target_repr=str(ta), request=request)
    return Response(
        TeachingAssignmentSerializer(ta, context={'request': request}).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def teaching_assignment_detail(request, assignment_id):
    """Get, update, or delete a teaching assignment."""
    ta = get_object_or_404(TeachingAssignment, pk=assignment_id, tenant=request.tenant)

    if request.method == 'GET':
        return Response(TeachingAssignmentSerializer(ta, context={'request': request}).data)

    if request.method == 'DELETE':
        log_audit('DELETE', 'TeachingAssignment', target_id=str(assignment_id),
                  target_repr=str(ta), request=request)
        ta.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = TeachingAssignmentCreateSerializer(
        ta, data=request.data, partial=True, context={'request': request},
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    log_audit('UPDATE', 'TeachingAssignment', target_id=str(assignment_id),
              target_repr=str(ta), request=request)
    return Response(TeachingAssignmentSerializer(ta, context={'request': request}).data)


# ─── School Overview ──────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def school_overview(request):
    """
    School View Level 1: grade bands with nested grades, student/section counts.
    Returns data suitable for the grade-cards grid UI.
    """
    from django.db.models import Count, Q, Prefetch

    academic_year = request.tenant.current_academic_year

    # Annotate grades with counts in a single query (eliminates N+1)
    section_filter = Q(sections__academic_year=academic_year) if academic_year else Q()
    annotated_grades = Grade.objects.filter(
        tenant=request.tenant,
    ).select_related('grade_band').annotate(
        _student_count=Count(
            'students',
            filter=Q(students__is_deleted=False, students__is_active=True, students__role='STUDENT'),
            distinct=True,
        ),
        _section_count=Count(
            'sections',
            filter=section_filter,
            distinct=True,
        ),
        _course_count=Count(
            'targeted_courses',
            filter=Q(
                targeted_courses__is_deleted=False,
                targeted_courses__is_active=True,
                targeted_courses__course_type='ACADEMIC',
            ),
            distinct=True,
        ),
    ).order_by('order')

    # Group by grade band
    bands = GradeBand.objects.filter(
        tenant=request.tenant,
    ).order_by('order')

    # Build grade lookup by band
    grades_by_band = {}
    for grade in annotated_grades:
        grades_by_band.setdefault(grade.grade_band_id, []).append(grade)

    result = []
    for band in bands:
        band_data = GradeBandSerializer(band).data
        band_data['grades'] = [
            {
                'id': str(g.id),
                'name': g.name,
                'short_code': g.short_code,
                'order': g.order,
                'student_count': g._student_count,
                'section_count': g._section_count,
                'course_count': g._course_count,
            }
            for g in grades_by_band.get(band.id, [])
        ]
        result.append(band_data)

    return Response({
        'academic_year': academic_year,
        'school_name': request.tenant.name,
        'grade_bands': result,
    })


# ─── Section Detail Views ────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def section_students(request, section_id):
    """Students roster for a section with progress data."""
    section = get_object_or_404(Section, pk=section_id, tenant=request.tenant)

    from apps.users.models import User
    from apps.users.serializers import UserSerializer

    students = User.objects.filter(
        section_fk=section, role='STUDENT',
        is_deleted=False,
    ).order_by('last_name', 'first_name')

    search = request.GET.get('search')
    if search:
        students = students.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(email__icontains=search)
            | Q(student_id__icontains=search)
        )

    page, pagination = _paginate(request, students)
    return Response({
        'section': SectionSerializer(section).data,
        'students': UserSerializer(page, many=True).data,
        **pagination,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def section_teachers(request, section_id):
    """Teachers assigned to a section via TeachingAssignment."""
    section = get_object_or_404(Section, pk=section_id, tenant=request.tenant)

    assignments = TeachingAssignment.objects.filter(
        sections=section,
    ).select_related('teacher', 'subject')

    if request.tenant.current_academic_year:
        assignments = assignments.filter(
            academic_year=request.tenant.current_academic_year,
        )

    return Response({
        'section': SectionSerializer(section).data,
        'teachers': TeachingAssignmentSerializer(
            assignments, many=True, context={'request': request},
        ).data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def section_courses(request, section_id):
    """Academic courses targeting a section."""
    section = get_object_or_404(Section, pk=section_id, tenant=request.tenant)

    from apps.courses.models import Course
    courses = Course.objects.filter(
        target_sections=section, course_type='ACADEMIC',
    ).order_by('-created_at')

    from apps.courses.serializers import CourseListSerializer
    page, pagination = _paginate(request, courses)
    return Response({
        'section': SectionSerializer(section).data,
        'courses': CourseListSerializer(
            page, many=True, context={'request': request},
        ).data,
        **pagination,
    })


# ─── CSV Import & Student Management ─────────────────────────────────────────

_CSV_ALLOWED_TYPES = {'text/csv', 'text/plain', 'application/csv', 'application/vnd.ms-excel'}


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
@throttle_classes([ScopedRateThrottle])
@admin_only
@tenant_required
@check_tenant_limit('students')
def section_import_students(request, section_id):
    """
    Import students via CSV into a specific section.
    Grade and section are pre-filled from navigation context.

    CSV format: first_name, last_name, email (required columns)
    Optional columns: parent_email
    """
    request.throttle_scope = 'csv_import'

    section = get_object_or_404(Section, pk=section_id, tenant=request.tenant)

    f = request.FILES.get('file')
    if not f:
        return Response({'error': 'CSV file is required'}, status=status.HTTP_400_BAD_REQUEST)

    # Validate MIME type
    file_type = getattr(f, 'content_type', '')
    file_name = getattr(f, 'name', '')
    if file_type not in _CSV_ALLOWED_TYPES and not file_name.lower().endswith('.csv'):
        return Response(
            {'error': 'Invalid file type. Please upload a CSV file.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    max_size = 2 * 1024 * 1024  # 2MB
    if getattr(f, 'size', 0) > max_size:
        return Response({'error': 'CSV file too large (max 2MB)'}, status=status.HTTP_400_BAD_REQUEST)

    from apps.users.models import User
    from .services import generate_student_id

    try:
        content = f.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        return Response({'error': 'File must be UTF-8 encoded CSV'}, status=status.HTTP_400_BAD_REQUEST)

    reader = csv.DictReader(io.StringIO(content))
    required_cols = {'first_name', 'last_name', 'email'}
    if reader.fieldnames and not required_cols.issubset(set(reader.fieldnames)):
        missing = required_cols - set(reader.fieldnames or [])
        return Response(
            {'error': f'Missing required columns: {", ".join(missing)}'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    results = {'created': 0, 'skipped': 0, 'errors': [], 'total_rows': 0}

    for row_num, row in enumerate(reader, start=2):
        results['total_rows'] += 1

        try:
            email = (row.get('email') or '').strip().lower()
            first_name = (row.get('first_name') or '').strip()
            last_name = (row.get('last_name') or '').strip()

            if not email:
                results['errors'].append({'row': row_num, 'error': 'Email is required'})
                continue

            if not first_name:
                results['errors'].append({'row': row_num, 'error': 'First name is required'})
                continue

            # Check for existing user
            if User.objects.filter(email__iexact=email).exists():
                results['errors'].append({'row': row_num, 'error': f'{email} already exists'})
                results['skipped'] += 1
                continue

            # Generate auto-ID and create student
            password = secrets.token_urlsafe(12)
            student_id = generate_student_id(request.tenant)

            User.objects.create_user(
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                tenant=request.tenant,
                role='STUDENT',
                student_id=student_id,
                grade_fk=section.grade,
                section_fk=section,
                parent_email=(row.get('parent_email') or '').strip(),
                must_change_password=True,
            )
            results['created'] += 1

        except (IntegrityError, ValidationError) as e:
            logger.warning("CSV import validation error at row %d: %s", row_num, e)
            results['errors'].append({'row': row_num, 'error': 'Failed to create student. Check for duplicate email.'})
        except Exception:
            logger.exception("CSV import unexpected error at row %d", row_num)
            results['errors'].append({'row': row_num, 'error': 'Unexpected error processing this row.'})

    log_audit('IMPORT', 'User', target_id=str(section_id),
              target_repr=f"Imported {results['created']} students into {section}",
              changes=results, request=request)

    return Response(results)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
@check_tenant_limit('students')
def section_add_student(request, section_id):
    """Add a single student to a section with auto-generated ID."""
    section = get_object_or_404(Section, pk=section_id, tenant=request.tenant)

    from apps.users.models import User
    from .services import generate_student_id

    email = (request.data.get('email') or '').strip().lower()
    first_name = (request.data.get('first_name') or '').strip()
    last_name = (request.data.get('last_name') or '').strip()

    if not email:
        return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
    if not first_name:
        return Response({'error': 'First name is required'}, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(email__iexact=email).exists():
        return Response(
            {'error': 'A user with this email already exists'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    password = secrets.token_urlsafe(12)
    student_id = generate_student_id(request.tenant)

    student = User.objects.create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        tenant=request.tenant,
        role='STUDENT',
        student_id=student_id,
        grade_fk=section.grade,
        section_fk=section,
        parent_email=(request.data.get('parent_email') or '').strip(),
        must_change_password=True,
    )

    log_audit('CREATE', 'User', target_id=str(student.id),
              target_repr=f"{student} in {section}",
              request=request)

    return Response(
        {
            'id': str(student.id),
            'email': student.email,
            'first_name': student.first_name,
            'last_name': student.last_name,
            'student_id': student.student_id,
            'must_change_password': True,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def transfer_student(request, student_id):
    """Transfer a student to a different section (and optionally grade)."""
    from apps.users.models import User

    student = get_object_or_404(
        User, pk=student_id, tenant=request.tenant, role='STUDENT',
    )

    new_section_id = request.data.get('section_id')
    if not new_section_id:
        return Response({'error': 'section_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    new_section = get_object_or_404(Section, pk=new_section_id, tenant=request.tenant)

    old_section = student.section_fk
    old_grade = student.grade_fk

    student.section_fk = new_section
    student.grade_fk = new_section.grade  # Update grade to match new section
    student.save(update_fields=['section_fk', 'grade_fk'])

    # Re-evaluate course auto-assignments (pass old_section for removal)
    from .services import reassign_student_courses
    reassign_student_courses(student, old_section=old_section)

    log_audit('UPDATE', 'User', target_id=str(student_id),
              target_repr=f"Transfer {student}",
              changes={
                  'section': {'old': str(old_section), 'new': str(new_section)},
                  'grade': {'old': str(old_grade), 'new': str(new_section.grade)},
              },
              request=request)

    from apps.users.serializers import UserSerializer
    return Response(UserSerializer(student).data)


# ─── Course Cloning ───────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def clone_course_view(request, course_id):
    """Deep-clone a course with all modules and contents."""
    from apps.courses.models import Course

    course = get_object_or_404(Course, pk=course_id, tenant=request.tenant)

    from .services import clone_course
    new_title = request.data.get('title')
    new_course = clone_course(
        original_course=course,
        new_title=new_title,
        cloned_by=request.user,
    )

    log_audit('CREATE', 'Course', target_id=str(new_course.id),
              target_repr=f"Cloned from '{course.title}'",
              changes={'source_course_id': str(course.id)},
              request=request)

    from apps.courses.serializers import CourseListSerializer
    return Response(
        CourseListSerializer(new_course, context={'request': request}).data,
        status=status.HTTP_201_CREATED,
    )


# ─── Academic Year Promotion ─────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def promotion_preview(request):
    """Preview the academic year promotion plan."""
    from .services import get_promotion_preview
    preview = get_promotion_preview(request.tenant)

    return Response({
        'current_academic_year': request.tenant.current_academic_year,
        'grades': preview,
        'total_students': sum(g['student_count'] for g in preview),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
@admin_only
@tenant_required
def promotion_execute(request):
    """Execute the academic year promotion."""
    request.throttle_scope = 'promotion'
    new_academic_year = request.data.get('new_academic_year')
    if not new_academic_year:
        return Response(
            {'error': 'new_academic_year is required (e.g. "2027-28")'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    excluded_ids = request.data.get('excluded_student_ids', [])
    graduated_ids = request.data.get('graduated_student_ids', [])

    if not isinstance(excluded_ids, list) or not isinstance(graduated_ids, list):
        return Response(
            {'error': 'excluded_student_ids and graduated_student_ids must be lists'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if len(excluded_ids) > 5000 or len(graduated_ids) > 5000:
        return Response(
            {'error': 'Too many student IDs (max 5000)'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    from .services import execute_promotion
    result = execute_promotion(
        tenant=request.tenant,
        excluded_student_ids=excluded_ids,
        graduated_student_ids=graduated_ids,
        new_academic_year=new_academic_year,
    )

    log_audit('UPDATE', 'Tenant', target_id=str(request.tenant.id),
              target_repr=f"Promotion to {new_academic_year}",
              changes=result, request=request)

    return Response(result)
