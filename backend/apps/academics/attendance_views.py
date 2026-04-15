# apps/academics/attendance_views.py
"""
Attendance API endpoints for all portals.

- Admin: import CSV, school-wide overview
- Teacher: section attendance (read-only, added as tab in section_dashboard)
- Student: own attendance
"""

import csv
import io
import logging
from datetime import date, timedelta

from django.db.models import Count, Q, Case, When, IntegerField
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.decorators import admin_only, teacher_or_admin, tenant_required
from .models import Section
from .attendance_models import Attendance

logger = logging.getLogger(__name__)


# ─── Admin Endpoints ─────────────────────────────────────────────────────────


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
@parser_classes([MultiPartParser, FormParser])
def attendance_import(request):
    """
    Bulk import attendance from CSV.

    CSV format: student_id, date (YYYY-MM-DD), status (PRESENT/ABSENT/LATE/EXCUSED), remarks (optional)
    """
    csv_file = request.FILES.get('file')
    if not csv_file:
        return Response({'error': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

    if not csv_file.name.endswith('.csv'):
        return Response({'error': 'File must be a CSV.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        decoded = csv_file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(decoded))
    except Exception as e:
        return Response({'error': f'Could not read CSV: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

    from apps.users.models import User

    valid_statuses = {'PRESENT', 'ABSENT', 'LATE', 'EXCUSED'}
    created = 0
    updated = 0
    errors = []

    for row_num, row in enumerate(reader, start=2):
        student_id = (row.get('student_id') or '').strip()
        date_str = (row.get('date') or '').strip()
        row_status = (row.get('status') or '').strip().upper()
        remarks = (row.get('remarks') or '').strip()

        if not student_id or not date_str or not row_status:
            errors.append(f"Row {row_num}: missing required fields")
            continue

        if row_status not in valid_statuses:
            errors.append(f"Row {row_num}: invalid status '{row_status}'")
            continue

        try:
            parsed_date = date.fromisoformat(date_str)
        except ValueError:
            errors.append(f"Row {row_num}: invalid date '{date_str}'")
            continue

        try:
            student = User.objects.get(
                student_id=student_id,
                tenant=request.tenant,
                role='STUDENT',
                is_deleted=False,
            )
        except User.DoesNotExist:
            errors.append(f"Row {row_num}: student '{student_id}' not found")
            continue

        if not student.section_fk_id:
            errors.append(f"Row {row_num}: student '{student_id}' has no section assigned")
            continue

        obj, was_created = Attendance.objects.update_or_create(
            tenant=request.tenant,
            section=student.section_fk,
            student=student,
            date=parsed_date,
            defaults={'status': row_status, 'remarks': remarks},
        )
        if was_created:
            created += 1
        else:
            updated += 1

    return Response({
        'created': created,
        'updated': updated,
        'errors': errors[:50],
        'total_errors': len(errors),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def attendance_overview(request):
    """
    School-wide attendance overview for admin dashboard.

    Query params:
    - date: YYYY-MM-DD (default: today)
    - section_id: filter by specific section
    - grade_id: filter by grade
    """
    target_date = request.GET.get('date')
    if target_date:
        try:
            target_date = date.fromisoformat(target_date)
        except ValueError:
            target_date = timezone.localdate()
    else:
        target_date = timezone.localdate()

    filters = Q(tenant=request.tenant, date=target_date)

    section_id = request.GET.get('section_id')
    if section_id:
        filters &= Q(section_id=section_id)

    grade_id = request.GET.get('grade_id')
    if grade_id:
        filters &= Q(section__grade_id=grade_id)

    records = Attendance.objects.filter(filters)
    totals = records.aggregate(
        total=Count('id'),
        present=Count('id', filter=Q(status='PRESENT')),
        absent=Count('id', filter=Q(status='ABSENT')),
        late=Count('id', filter=Q(status='LATE')),
        excused=Count('id', filter=Q(status='EXCUSED')),
    )

    total = totals['total'] or 0
    present = totals['present'] or 0
    late = totals['late'] or 0
    absent = totals['absent'] or 0
    excused = totals['excused'] or 0

    on_time_pct = round((present / total) * 100, 1) if total > 0 else 0
    late_pct = round((late / total) * 100, 1) if total > 0 else 0
    absent_pct = round((absent / total) * 100, 1) if total > 0 else 0
    attendance_rate = round(((present + late) / total) * 100, 1) if total > 0 else 0

    # Per-student breakdown for bar chart (ordered: present first, late, absent)
    students = list(
        records.values('student_id', 'status')
        .order_by(
            Case(
                When(status='PRESENT', then=0),
                When(status='LATE', then=1),
                When(status='EXCUSED', then=2),
                When(status='ABSENT', then=3),
                output_field=IntegerField(),
            ),
            'student__last_name',
        )
    )

    bars = [{'status': s['status']} for s in students]

    # Yesterday comparison for trend badge
    yesterday = target_date - timedelta(days=1)
    yesterday_records = Attendance.objects.filter(
        tenant=request.tenant, date=yesterday,
    )
    if section_id:
        yesterday_records = yesterday_records.filter(section_id=section_id)
    if grade_id:
        yesterday_records = yesterday_records.filter(section__grade_id=grade_id)

    yesterday_total = yesterday_records.count()
    yesterday_present = yesterday_records.filter(status__in=['PRESENT', 'LATE']).count()
    yesterday_rate = round((yesterday_present / yesterday_total) * 100, 1) if yesterday_total > 0 else 0
    trend = round(attendance_rate - yesterday_rate, 1)

    # Section breakdown
    section_stats = list(
        records.values(
            'section_id', 'section__name',
            'section__grade__name', 'section__grade__short_code',
        ).annotate(
            total=Count('id'),
            present=Count('id', filter=Q(status='PRESENT')),
            late=Count('id', filter=Q(status='LATE')),
            absent=Count('id', filter=Q(status='ABSENT')),
        ).order_by('section__grade__order', 'section__name')
    )

    sections = []
    for s in section_stats:
        s_total = s['total']
        s_present = s['present'] + s['late']
        sections.append({
            'section_id': str(s['section_id']),
            'section_name': s['section__name'],
            'grade_name': s['section__grade__name'],
            'grade_short_code': s['section__grade__short_code'],
            'total': s_total,
            'present': s['present'],
            'late': s['late'],
            'absent': s['absent'],
            'rate': round((s_present / s_total) * 100, 1) if s_total > 0 else 0,
        })

    return Response({
        'date': target_date.isoformat(),
        'summary': {
            'total': total,
            'present': present,
            'late': late,
            'absent': absent,
            'excused': excused,
            'attendance_rate': attendance_rate,
            'on_time_pct': on_time_pct,
            'late_pct': late_pct,
            'absent_pct': absent_pct,
            'trend': trend,
        },
        'bars': bars,
        'sections': sections,
    })


# ─── Teacher Endpoint (section attendance) ────────────────────────────────────


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def section_attendance(request, section_id):
    """
    Attendance data for a section. Used as attendance tab in section dashboard.

    Query params:
    - date: YYYY-MM-DD (default: today)
    - from_date / to_date: date range for report view
    """
    from .models import TeachingAssignment

    section = get_object_or_404(
        Section.objects.select_related('grade__grade_band'),
        pk=section_id,
        tenant=request.tenant,
    )

    # Access check
    if request.user.role in ('TEACHER', 'HOD', 'IB_COORDINATOR'):
        has_access = TeachingAssignment.objects.filter(
            tenant=request.tenant,
            teacher=request.user,
            sections=section,
            academic_year=request.tenant.current_academic_year,
        ).exists()
        if not has_access:
            return Response(
                {'error': 'No teaching assignment for this section.'},
                status=status.HTTP_403_FORBIDDEN,
            )

    # Single-date view (default)
    target_date = request.GET.get('date')
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')

    if from_date and to_date:
        # Report view: summary per student for date range
        try:
            from_date = date.fromisoformat(from_date)
            to_date = date.fromisoformat(to_date)
        except ValueError:
            return Response({'error': 'Invalid date format.'}, status=status.HTTP_400_BAD_REQUEST)

        from apps.users.models import User
        students = User.objects.filter(
            section_fk=section, role='STUDENT',
            is_deleted=False, is_active=True,
        ).order_by('last_name', 'first_name')

        student_reports = []
        for student in students:
            records = Attendance.objects.filter(
                tenant=request.tenant, section=section,
                student=student, date__range=(from_date, to_date),
            )
            totals = records.aggregate(
                total=Count('id'),
                present=Count('id', filter=Q(status='PRESENT')),
                late=Count('id', filter=Q(status='LATE')),
                absent=Count('id', filter=Q(status='ABSENT')),
                excused=Count('id', filter=Q(status='EXCUSED')),
            )
            t = totals['total'] or 0
            p = (totals['present'] or 0) + (totals['late'] or 0)
            student_reports.append({
                'id': str(student.id),
                'first_name': student.first_name,
                'last_name': student.last_name,
                'student_id': student.student_id,
                'total_days': t,
                'present': totals['present'] or 0,
                'late': totals['late'] or 0,
                'absent': totals['absent'] or 0,
                'excused': totals['excused'] or 0,
                'rate': round((p / t) * 100, 1) if t > 0 else 0,
            })

        return Response({
            'section_id': str(section.id),
            'from_date': from_date.isoformat(),
            'to_date': to_date.isoformat(),
            'students': student_reports,
        })

    # Single-date view
    if target_date:
        try:
            target_date = date.fromisoformat(target_date)
        except ValueError:
            target_date = timezone.localdate()
    else:
        target_date = timezone.localdate()

    records = Attendance.objects.filter(
        tenant=request.tenant, section=section, date=target_date,
    ).select_related('student').order_by('student__last_name')

    totals = records.aggregate(
        total=Count('id'),
        present=Count('id', filter=Q(status='PRESENT')),
        late=Count('id', filter=Q(status='LATE')),
        absent=Count('id', filter=Q(status='ABSENT')),
        excused=Count('id', filter=Q(status='EXCUSED')),
    )

    total = totals['total'] or 0
    present = totals['present'] or 0
    late = totals['late'] or 0
    on_time_rate = round((present / total) * 100, 1) if total > 0 else 0
    attendance_rate = round(((present + late) / total) * 100, 1) if total > 0 else 0

    student_data = [{
        'id': str(r.student.id),
        'first_name': r.student.first_name,
        'last_name': r.student.last_name,
        'student_id': r.student.student_id,
        'status': r.status,
        'remarks': r.remarks,
    } for r in records]

    bars = [{'status': r.status} for r in records]

    return Response({
        'section_id': str(section.id),
        'date': target_date.isoformat(),
        'summary': {
            'total': total,
            'present': present,
            'late': late,
            'absent': totals['absent'] or 0,
            'excused': totals['excused'] or 0,
            'attendance_rate': attendance_rate,
            'on_time_pct': on_time_rate,
            'late_pct': round((late / total) * 100, 1) if total > 0 else 0,
            'absent_pct': round(((totals['absent'] or 0) / total) * 100, 1) if total > 0 else 0,
        },
        'bars': bars,
        'students': student_data,
    })


# ─── Student Endpoint ─────────────────────────────────────────────────────────


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@tenant_required
def student_my_attendance(request):
    """
    Student's own attendance records.

    Query params:
    - month: YYYY-MM (default: current month)
    """
    if request.user.role != 'STUDENT':
        return Response({'error': 'Students only.'}, status=status.HTTP_403_FORBIDDEN)

    month_str = request.GET.get('month')
    if month_str:
        try:
            year, month = month_str.split('-')
            from_date = date(int(year), int(month), 1)
        except (ValueError, TypeError):
            from_date = timezone.localdate().replace(day=1)
    else:
        from_date = timezone.localdate().replace(day=1)

    # End of month
    if from_date.month == 12:
        to_date = from_date.replace(year=from_date.year + 1, month=1) - timedelta(days=1)
    else:
        to_date = from_date.replace(month=from_date.month + 1) - timedelta(days=1)

    records = Attendance.objects.filter(
        tenant=request.tenant,
        student=request.user,
        date__range=(from_date, to_date),
    ).order_by('date')

    totals = records.aggregate(
        total=Count('id'),
        present=Count('id', filter=Q(status='PRESENT')),
        late=Count('id', filter=Q(status='LATE')),
        absent=Count('id', filter=Q(status='ABSENT')),
        excused=Count('id', filter=Q(status='EXCUSED')),
    )

    total = totals['total'] or 0
    present = (totals['present'] or 0) + (totals['late'] or 0)
    attendance_rate = round((present / total) * 100, 1) if total > 0 else 0

    days = [{
        'date': r.date.isoformat(),
        'status': r.status,
        'remarks': r.remarks,
    } for r in records]

    return Response({
        'month': from_date.strftime('%Y-%m'),
        'summary': {
            'total_days': total,
            'present': totals['present'] or 0,
            'late': totals['late'] or 0,
            'absent': totals['absent'] or 0,
            'excused': totals['excused'] or 0,
            'attendance_rate': attendance_rate,
            'on_time_pct': round(((totals['present'] or 0) / total) * 100, 1) if total > 0 else 0,
            'late_pct': round(((totals['late'] or 0) / total) * 100, 1) if total > 0 else 0,
            'absent_pct': round(((totals['absent'] or 0) / total) * 100, 1) if total > 0 else 0,
        },
        'days': days,
    })


# ─── CSV Export Endpoints ────────────────────────────────────────────────────


def _csv_response(filename, header, rows):
    """Build a CSV HttpResponse."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def attendance_export_admin(request):
    """
    Admin: Export school-wide attendance as CSV.

    Query params:
    - date: single date (YYYY-MM-DD)
    - from_date / to_date: date range
    - section_id: filter by section
    - grade_id: filter by grade
    """
    from_date_str = request.GET.get('from_date')
    to_date_str = request.GET.get('to_date')
    single_date = request.GET.get('date')
    section_id = request.GET.get('section_id')
    grade_id = request.GET.get('grade_id')

    filters = Q(tenant=request.tenant)

    if from_date_str and to_date_str:
        try:
            f = date.fromisoformat(from_date_str)
            t = date.fromisoformat(to_date_str)
            filters &= Q(date__range=(f, t))
            filename = f'attendance_{from_date_str}_to_{to_date_str}.csv'
        except ValueError:
            return Response({'error': 'Invalid date format.'}, status=status.HTTP_400_BAD_REQUEST)
    elif single_date:
        try:
            d = date.fromisoformat(single_date)
            filters &= Q(date=d)
            filename = f'attendance_{single_date}.csv'
        except ValueError:
            return Response({'error': 'Invalid date format.'}, status=status.HTTP_400_BAD_REQUEST)
    else:
        d = timezone.localdate()
        filters &= Q(date=d)
        filename = f'attendance_{d.isoformat()}.csv'

    if section_id:
        filters &= Q(section_id=section_id)
    if grade_id:
        filters &= Q(section__grade_id=grade_id)

    records = (
        Attendance.objects.filter(filters)
        .select_related('student', 'section', 'section__grade')
        .order_by('date', 'section__grade__order', 'section__name', 'student__last_name')
    )

    header = ['Date', 'Grade', 'Section', 'Student ID', 'First Name', 'Last Name', 'Status', 'Remarks']
    rows = []
    for r in records:
        rows.append([
            r.date.isoformat(),
            r.section.grade.name if r.section.grade else '',
            r.section.name,
            r.student.student_id,
            r.student.first_name,
            r.student.last_name,
            r.status,
            r.remarks,
        ])

    return _csv_response(filename, header, rows)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def attendance_export_section(request, section_id):
    """
    Teacher: Export section attendance as CSV.

    Query params:
    - date: single date
    - from_date / to_date: date range
    """
    from .models import TeachingAssignment

    section = get_object_or_404(
        Section.objects.select_related('grade'),
        pk=section_id,
        tenant=request.tenant,
    )

    if request.user.role in ('TEACHER', 'HOD', 'IB_COORDINATOR'):
        has_access = TeachingAssignment.objects.filter(
            tenant=request.tenant,
            teacher=request.user,
            sections=section,
            academic_year=request.tenant.current_academic_year,
        ).exists()
        if not has_access:
            return Response(
                {'error': 'No teaching assignment for this section.'},
                status=status.HTTP_403_FORBIDDEN,
            )

    from_date_str = request.GET.get('from_date')
    to_date_str = request.GET.get('to_date')
    single_date = request.GET.get('date')

    filters = Q(tenant=request.tenant, section=section)

    if from_date_str and to_date_str:
        try:
            f = date.fromisoformat(from_date_str)
            t = date.fromisoformat(to_date_str)
            filters &= Q(date__range=(f, t))
            filename = f'attendance_{section.name}_{from_date_str}_to_{to_date_str}.csv'
        except ValueError:
            return Response({'error': 'Invalid date format.'}, status=status.HTTP_400_BAD_REQUEST)
    elif single_date:
        try:
            d = date.fromisoformat(single_date)
            filters &= Q(date=d)
            filename = f'attendance_{section.name}_{single_date}.csv'
        except ValueError:
            return Response({'error': 'Invalid date format.'}, status=status.HTTP_400_BAD_REQUEST)
    else:
        d = timezone.localdate()
        filters &= Q(date=d)
        filename = f'attendance_{section.name}_{d.isoformat()}.csv'

    records = (
        Attendance.objects.filter(filters)
        .select_related('student')
        .order_by('date', 'student__last_name')
    )

    header = ['Date', 'Student ID', 'First Name', 'Last Name', 'Status', 'Remarks']
    rows = []
    for r in records:
        rows.append([
            r.date.isoformat(),
            r.student.student_id,
            r.student.first_name,
            r.student.last_name,
            r.status,
            r.remarks,
        ])

    return _csv_response(filename, header, rows)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@tenant_required
def attendance_export_student(request):
    """
    Student: Export own attendance as CSV.

    Query params:
    - month: YYYY-MM (default: current month)
    """
    if request.user.role != 'STUDENT':
        return Response({'error': 'Students only.'}, status=status.HTTP_403_FORBIDDEN)

    month_str = request.GET.get('month')
    if month_str:
        try:
            year, month = month_str.split('-')
            from_date = date(int(year), int(month), 1)
        except (ValueError, TypeError):
            from_date = timezone.localdate().replace(day=1)
    else:
        from_date = timezone.localdate().replace(day=1)

    if from_date.month == 12:
        to_date = from_date.replace(year=from_date.year + 1, month=1) - timedelta(days=1)
    else:
        to_date = from_date.replace(month=from_date.month + 1) - timedelta(days=1)

    records = Attendance.objects.filter(
        tenant=request.tenant,
        student=request.user,
        date__range=(from_date, to_date),
    ).order_by('date')

    filename = f'my_attendance_{from_date.strftime("%Y-%m")}.csv'
    header = ['Date', 'Status', 'Remarks']
    rows = []
    for r in records:
        rows.append([r.date.isoformat(), r.status, r.remarks])

    return _csv_response(filename, header, rows)
