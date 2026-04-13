# apps/progress/certification_views.py

import logging
from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.courses.models import Course
from apps.users.models import User
from dateutil.relativedelta import relativedelta
from utils.decorators import admin_only, teacher_or_admin, tenant_required
from utils.helpers import make_pagination_class
from utils.responses import error_response

from .certification_models import CertificationType, TeacherCertification
from .certification_serializers import (
    CertificationTypeCreateSerializer,
    CertificationTypeSerializer,
    IssueCertificationSerializer,
    TeacherCertificationSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CertificationType CRUD (admin only)
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def certification_type_list(request):
    """List all certification types for the tenant."""
    qs = CertificationType.objects.prefetch_related('required_courses').all()

    paginator = make_pagination_class(25, 100)()
    page = paginator.paginate_queryset(qs, request)
    if page is not None:
        serializer = CertificationTypeSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    serializer = CertificationTypeSerializer(qs, many=True)
    return Response({"results": serializer.data}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def certification_type_create(request):
    """Create a new certification type."""
    serializer = CertificationTypeCreateSerializer(
        data=request.data, context={"request": request}
    )
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    required_course_ids = data.pop('required_course_ids', [])

    cert_type = CertificationType(tenant=request.tenant, **data)
    cert_type.save()

    if required_course_ids:
        courses = Course.objects.filter(
            id__in=required_course_ids, tenant=request.tenant,
        )
        cert_type.required_courses.set(courses)

    return Response(
        CertificationTypeSerializer(cert_type).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def certification_type_detail(request, cert_type_id):
    """Retrieve a single certification type."""
    cert_type = get_object_or_404(
        CertificationType.objects.prefetch_related('required_courses'),
        id=cert_type_id, tenant=request.tenant,
    )
    return Response(
        CertificationTypeSerializer(cert_type).data,
        status=status.HTTP_200_OK,
    )


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def certification_type_update(request, cert_type_id):
    """Update a certification type."""
    cert_type = get_object_or_404(
        CertificationType, id=cert_type_id, tenant=request.tenant,
    )
    serializer = CertificationTypeCreateSerializer(
        cert_type, data=request.data, partial=True, context={"request": request},
    )
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    required_course_ids = data.pop('required_course_ids', None)

    for attr, value in data.items():
        setattr(cert_type, attr, value)
    cert_type.save()

    if required_course_ids is not None:
        courses = Course.objects.filter(
            id__in=required_course_ids, tenant=request.tenant,
        )
        cert_type.required_courses.set(courses)

    return Response(
        CertificationTypeSerializer(cert_type).data,
        status=status.HTTP_200_OK,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def certification_type_delete(request, cert_type_id):
    """Delete a certification type."""
    cert_type = get_object_or_404(
        CertificationType, id=cert_type_id, tenant=request.tenant,
    )
    cert_type.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# TeacherCertification management
# ---------------------------------------------------------------------------

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def certification_issue(request):
    """
    Issue a certification to a teacher.

    Body:
    {
      "teacher_id": "uuid",
      "certification_type_id": "uuid",
      "expires_at": "2027-03-26T00:00:00Z"  // optional, defaults to now + validity_months
    }
    """
    serializer = IssueCertificationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    teacher = get_object_or_404(
        User, id=data['teacher_id'], tenant=request.tenant, is_active=True,
    )
    cert_type = get_object_or_404(
        CertificationType, id=data['certification_type_id'], tenant=request.tenant,
    )

    # Check if teacher already has an active certification of this type
    existing = TeacherCertification.objects.filter(
        teacher=teacher,
        certification_type=cert_type,
        status='active',
    ).first()
    if existing:
        return error_response(
            "Teacher already has an active certification of this type.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    expires_at = data.get('expires_at')
    if not expires_at:
        expires_at = timezone.now() + relativedelta(months=cert_type.validity_months)

    tc = TeacherCertification.objects.create(
        teacher=teacher,
        certification_type=cert_type,
        tenant=request.tenant,
        expires_at=expires_at,
        status='active',
        issued_by=request.user,
    )

    logger.info(
        "Certification issued: teacher=%s cert_type=%s expires=%s by=%s",
        teacher.email, cert_type.name, expires_at, request.user.email,
    )

    return Response(
        TeacherCertificationSerializer(tc).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def certification_list(request):
    """
    List teacher certifications.
    - Admins: see all. Supports ?teacher_id= and ?status= filters.
    - Teachers: see only their own.
    """
    user = request.user
    is_admin = user.role in ('SCHOOL_ADMIN', 'SUPER_ADMIN')

    qs = TeacherCertification.objects.select_related(
        'certification_type', 'teacher', 'issued_by',
    ).all()

    if is_admin:
        teacher_id = request.GET.get("teacher_id")
        if teacher_id:
            qs = qs.filter(teacher_id=teacher_id)
    else:
        qs = qs.filter(teacher=user)

    status_filter = request.GET.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter)

    cert_type_id = request.GET.get("certification_type_id")
    if cert_type_id:
        qs = qs.filter(certification_type_id=cert_type_id)

    paginator = make_pagination_class(25, 100)()
    page = paginator.paginate_queryset(qs, request)
    if page is not None:
        serializer = TeacherCertificationSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    serializer = TeacherCertificationSerializer(qs, many=True)
    return Response({"results": serializer.data}, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def certification_detail(request, cert_id):
    """Retrieve a single teacher certification."""
    user = request.user
    is_admin = user.role in ('SCHOOL_ADMIN', 'SUPER_ADMIN')

    tc = get_object_or_404(TeacherCertification, id=cert_id, tenant=request.tenant)
    if not is_admin and tc.teacher_id != user.id:
        return error_response("Access denied.", status_code=status.HTTP_403_FORBIDDEN)

    return Response(
        TeacherCertificationSerializer(tc).data,
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def certification_revoke(request, cert_id):
    """
    Revoke a teacher certification.
    Body: { "reason": "..." }
    """
    tc = get_object_or_404(TeacherCertification, id=cert_id, tenant=request.tenant)
    if tc.status == 'revoked':
        return error_response("Certification is already revoked.", status_code=status.HTTP_400_BAD_REQUEST)

    tc.status = 'revoked'
    tc.revoked_reason = request.data.get('reason', '')
    tc.save(update_fields=['status', 'revoked_reason', 'updated_at'])

    logger.info(
        "Certification revoked: cert=%s teacher=%s by=%s reason=%s",
        cert_id, tc.teacher.email, request.user.email, tc.revoked_reason,
    )

    return Response(
        TeacherCertificationSerializer(tc).data,
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def certification_renew(request, cert_id):
    """
    Manually renew a certification. Extends expiry by validity_months from now.
    """
    tc = get_object_or_404(TeacherCertification, id=cert_id, tenant=request.tenant)
    if tc.status == 'revoked':
        return error_response(
            "Cannot renew a revoked certification.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    validity_months = tc.certification_type.validity_months
    tc.expires_at = timezone.now() + relativedelta(months=validity_months)
    tc.status = 'active'
    tc.renewal_count += 1
    tc.save(update_fields=['expires_at', 'status', 'renewal_count', 'updated_at'])

    logger.info(
        "Certification renewed: cert=%s teacher=%s new_expiry=%s by=%s",
        cert_id, tc.teacher.email, tc.expires_at, request.user.email,
    )

    return Response(
        TeacherCertificationSerializer(tc).data,
        status=status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# Expiry check
# ---------------------------------------------------------------------------

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def certification_expiry_check(request):
    """
    Check certification expiry status.
    Returns certifications expiring within the next 30 days (configurable via ?days=).
    Also returns already-expired certifications that are still marked as 'active'.
    """
    try:
        days = int(request.data.get("days", request.GET.get("days", 30)))
    except (ValueError, TypeError):
        return error_response(
            "Invalid 'days' parameter. Must be an integer between 1 and 365.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if days < 1 or days > 365:
        return error_response(
            "Invalid 'days' parameter. Must be an integer between 1 and 365.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    now = timezone.now()
    threshold = now + timedelta(days=days)

    # Expiring soon (still active, expires within threshold)
    expiring_soon = TeacherCertification.objects.select_related(
        'certification_type', 'teacher',
    ).filter(
        status='active',
        expires_at__gt=now,
        expires_at__lte=threshold,
    ).order_by('expires_at')

    expiring_data = []
    for tc in expiring_soon:
        expiring_data.append({
            "id": str(tc.id),
            "teacher_name": tc.teacher.get_full_name() or tc.teacher.email,
            "teacher_email": tc.teacher.email,
            "certification_name": tc.certification_type.name,
            "expires_at": tc.expires_at.isoformat(),
            "days_until_expiry": tc.days_until_expiry,
        })

    # Already expired but status hasn't been updated yet
    already_expired = TeacherCertification.objects.select_related(
        'certification_type', 'teacher',
    ).filter(
        status='active',
        expires_at__lte=now,
    ).order_by('expires_at')

    expired_data = []
    for tc in already_expired:
        # Update status while we're at it
        tc.status = 'expired'
        tc.save(update_fields=['status', 'updated_at'])
        expired_data.append({
            "id": str(tc.id),
            "teacher_name": tc.teacher.get_full_name() or tc.teacher.email,
            "teacher_email": tc.teacher.email,
            "certification_name": tc.certification_type.name,
            "expires_at": tc.expires_at.isoformat(),
            "days_since_expiry": abs(tc.days_until_expiry),
        })

    return Response(
        {
            "expiring_soon": expiring_data,
            "already_expired": expired_data,
            "threshold_days": days,
        },
        status=status.HTTP_200_OK,
    )
