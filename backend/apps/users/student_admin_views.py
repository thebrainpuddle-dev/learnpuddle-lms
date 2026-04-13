# apps/users/student_admin_views.py
"""
Admin endpoints for managing student accounts.

    GET    /api/v1/students/                     - List students
    GET    /api/v1/students/deleted/             - List deleted students
    POST   /api/v1/students/bulk-import/         - CSV bulk import
    POST   /api/v1/students/bulk-action/         - Bulk activate/deactivate/delete
    GET    /api/v1/students/<id>/                - Get student detail
    PATCH  /api/v1/students/<id>/                - Update student
    DELETE /api/v1/students/<id>/                - Soft-delete student
    POST   /api/v1/students/<id>/restore/        - Restore deleted student
    GET/POST /api/v1/students/invitations/       - List/create invitations
    POST   /api/v1/students/bulk-invite/         - Bulk invite via CSV
"""

import csv
import io
import secrets

from django.db import models
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from utils.decorators import admin_only, tenant_required, check_feature, check_tenant_limit
from utils.audit import log_audit
from .models import User, TeacherInvitation
from .student_serializers import StudentSerializer, RegisterStudentSerializer


class StudentPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


# ══════════════════════════════════════════════════════════════════════════
# Student List & Detail
# ══════════════════════════════════════════════════════════════════════════

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
@check_feature("feature_students")
def students_list_view(request):
    """List students within the current tenant."""
    qs = User.objects.filter(tenant=request.tenant, role="STUDENT")

    is_active = request.GET.get("is_active")
    if is_active is not None:
        qs = qs.filter(is_active=is_active.lower() == "true")

    grade_level = request.GET.get("grade_level")
    if grade_level:
        qs = qs.filter(grade_level__iexact=grade_level)

    section = request.GET.get("section")
    if section:
        qs = qs.filter(section__iexact=section)

    search = request.GET.get("search")
    if search:
        qs = qs.filter(
            models.Q(email__icontains=search)
            | models.Q(first_name__icontains=search)
            | models.Q(last_name__icontains=search)
            | models.Q(student_id__icontains=search)
        )

    qs = qs.order_by("last_name", "first_name")

    paginator = StudentPagination()
    page = paginator.paginate_queryset(qs, request)
    if page is not None:
        return paginator.get_paginated_response(
            StudentSerializer(page, many=True, context={"request": request}).data
        )
    return Response(
        StudentSerializer(qs, many=True, context={"request": request}).data,
        status=status.HTTP_200_OK,
    )


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
@check_feature("feature_students")
def student_detail_view(request, student_id):
    """
    GET: Fetch a student.
    PATCH: Update student fields.
    DELETE: Soft-delete a student.
    """
    student = get_object_or_404(User, id=student_id, tenant=request.tenant, role="STUDENT")

    if request.method == "GET":
        return Response(StudentSerializer(student, context={"request": request}).data)

    if request.method == "DELETE":
        student.delete(deleted_by=request.user)
        log_audit('DELETE', 'User', target_id=str(student.id), target_repr=str(student), request=request)
        return Response({"message": "Student deleted"}, status=status.HTTP_200_OK)

    # PATCH
    allowed = {
        "first_name", "last_name", "student_id", "grade_level",
        "section", "parent_email", "enrollment_date", "is_active",
    }
    changes = {}
    for key, value in request.data.items():
        if key in allowed:
            changes[key] = {"old": getattr(student, key), "new": value}
            setattr(student, key, value)
    student.save()
    log_audit('UPDATE', 'User', target_id=str(student.id), target_repr=str(student), changes=changes, request=request)
    return Response(StudentSerializer(student, context={"request": request}).data)


# ══════════════════════════════════════════════════════════════════════════
# Deleted Students & Restore
# ══════════════════════════════════════════════════════════════════════════

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
@check_feature("feature_students")
def deleted_students_list_view(request):
    """List soft-deleted students for potential recovery."""
    qs = User.all_objects.filter(tenant=request.tenant, is_deleted=True, role="STUDENT")

    search = request.GET.get("search")
    if search:
        qs = qs.filter(
            models.Q(email__icontains=search)
            | models.Q(first_name__icontains=search)
            | models.Q(last_name__icontains=search)
        )

    qs = qs.order_by("-deleted_at")

    paginator = StudentPagination()
    page = paginator.paginate_queryset(qs, request)

    data = []
    for student in (page or qs):
        student_data = StudentSerializer(student, context={"request": request}).data
        student_data["deleted_at"] = student.deleted_at
        student_data["deleted_by"] = str(student.deleted_by_id) if student.deleted_by_id else None
        data.append(student_data)

    if page is not None:
        return paginator.get_paginated_response(data)
    return Response(data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
@check_feature("feature_students")
def restore_student_view(request, student_id):
    """Restore a soft-deleted student."""
    try:
        student = User.all_objects.get(id=student_id, tenant=request.tenant, is_deleted=True, role="STUDENT")
    except User.DoesNotExist:
        return Response({"error": "Deleted student not found"}, status=status.HTTP_404_NOT_FOUND)

    student.restore()
    log_audit('RESTORE', 'User', target_id=str(student.id), target_repr=str(student), request=request)

    return Response({
        "message": "Student restored successfully",
        "student": StudentSerializer(student, context={"request": request}).data,
    }, status=status.HTTP_200_OK)


# ══════════════════════════════════════════════════════════════════════════
# Bulk Import & Bulk Actions
# ══════════════════════════════════════════════════════════════════════════

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
@check_feature("feature_students")
@check_tenant_limit("students")
@parser_classes([MultiPartParser, FormParser])
def students_bulk_import_view(request):
    """
    Bulk import students via CSV upload.
    CSV columns: email, first_name, last_name, password
    Optional: student_id, grade_level, section, parent_email
    """
    f = request.FILES.get("file")
    if not f:
        return Response({"error": "CSV file is required"}, status=400)

    # Limit CSV file size to 2 MB
    max_csv_bytes = 2 * 1024 * 1024
    file_size = getattr(f, "size", 0) or 0
    if file_size > max_csv_bytes:
        return Response({"error": f"CSV file too large ({file_size // 1024}KB). Maximum is 2 MB."}, status=400)

    try:
        content = f.read().decode("utf-8-sig")
    except Exception:
        return Response({"error": "Could not read file as UTF-8"}, status=400)

    # Cap row count to prevent abuse
    max_rows = 500
    reader = csv.DictReader(io.StringIO(content))
    results = []
    created_count = 0

    # Calculate remaining student slots so the loop can't exceed the plan limit.
    tenant = request.tenant
    current_students = User.objects.filter(tenant=tenant, role="STUDENT", is_active=True).count()
    remaining_slots = max(0, tenant.max_students - current_students)

    def _sanitize_csv_value(val: str) -> str:
        """Strip leading formula-injection characters from CSV cell values."""
        if val and val[0] in ('=', '+', '-', '@', '\t', '\r'):
            return val.lstrip('=+\\-@\t\r')
        return val

    for i, row in enumerate(reader, start=1):
        if i > max_rows:
            results.append({"row": i, "email": "", "status": "error", "message": f"Row limit exceeded ({max_rows}). Remaining rows skipped."})
            break

        email = _sanitize_csv_value((row.get("email") or "").strip())
        first_name = _sanitize_csv_value((row.get("first_name") or "").strip())
        last_name = _sanitize_csv_value((row.get("last_name") or "").strip())
        csv_password = (row.get("password") or "").strip()
        password = csv_password or secrets.token_urlsafe(12)
        force_password_change = not csv_password  # Force change if auto-generated

        if not email or not first_name:
            results.append({"row": i, "email": email, "status": "error", "message": "Missing email or first_name"})
            continue

        # Check for existing user (case-insensitive)
        existing_user = User.objects.filter(email__iexact=email).first()
        if existing_user:
            if existing_user.is_deleted:
                results.append({
                    "row": i, "email": email, "status": "error",
                    "message": "Email was previously used. Contact support to restore or use different email."
                })
            elif existing_user.tenant_id == tenant.id:
                results.append({"row": i, "email": email, "status": "error", "message": "Student already exists in this school"})
            else:
                results.append({
                    "row": i, "email": email, "status": "error",
                    "message": "Email is registered with another organization"
                })
            continue

        if created_count >= remaining_slots:
            results.append({"row": i, "email": email, "status": "error", "message": f"Student limit reached ({tenant.max_students}). Upgrade your plan to add more."})
            continue

        try:
            User.objects.create_user(
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                student_id=_sanitize_csv_value(row.get("student_id", "").strip()),
                grade_level=_sanitize_csv_value(row.get("grade_level", "").strip()),
                section=_sanitize_csv_value(row.get("section", "").strip()),
                parent_email=_sanitize_csv_value(row.get("parent_email", "").strip()),
                tenant=tenant,
                role="STUDENT",
                is_active=True,
                must_change_password=force_password_change,
            )
            created_count += 1
            results.append({"row": i, "email": email, "status": "success"})
        except Exception:
            results.append({"row": i, "email": email, "status": "error", "message": "Failed to create user"})

    if created_count:
        log_audit('IMPORT', 'User', target_repr=f"Bulk import: {created_count} students", changes={"created": created_count}, request=request)

    return Response({"created": created_count, "total_rows": len(results), "results": results}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
@check_feature("feature_students")
def students_bulk_action(request):
    """
    Bulk actions on students.

    POST body:
    {
        "action": "activate" | "deactivate" | "delete",
        "student_ids": ["uuid", ...]
    }
    """
    action = (request.data.get('action') or '').lower()
    student_ids = request.data.get('student_ids', [])

    valid_actions = ['activate', 'deactivate', 'delete']
    if action not in valid_actions:
        return Response(
            {'error': f'Invalid action. Must be one of: {", ".join(valid_actions)}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not student_ids or not isinstance(student_ids, list):
        return Response(
            {'error': 'student_ids must be a non-empty list'},
            status=status.HTTP_400_BAD_REQUEST
        )

    MAX_BULK_IDS = 100
    if len(student_ids) > MAX_BULK_IDS:
        return Response(
            {'error': f'Too many IDs. Maximum {MAX_BULK_IDS} per request.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    students = User.objects.filter(id__in=student_ids, tenant=request.tenant, role="STUDENT")

    found_count = students.count()
    if found_count == 0:
        return Response(
            {'error': 'No valid students found with the provided IDs'},
            status=status.HTTP_404_NOT_FOUND
        )

    affected_count = 0

    if action == 'activate':
        affected_count = students.filter(is_active=False).update(is_active=True)
        action_display = 'activated'
    elif action == 'deactivate':
        affected_count = students.filter(is_active=True).update(is_active=False)
        action_display = 'deactivated'
    elif action == 'delete':
        affected_count = students.filter(is_deleted=False).update(
            is_deleted=True,
            deleted_at=timezone.now(),
            deleted_by=request.user,
            is_active=False,
        )
        action_display = 'deleted'

    log_audit(
        'BULK_ACTION',
        'User',
        target_repr=f"Bulk {action}: {affected_count} students",
        changes={'action': action, 'student_ids': student_ids, 'affected': affected_count},
        request=request,
    )

    return Response({
        'message': f'Successfully {action_display} {affected_count} student(s)',
        'affected_count': affected_count,
        'requested_count': len(student_ids),
    }, status=status.HTTP_200_OK)


# ══════════════════════════════════════════════════════════════════════════
# Register Single Student
# ══════════════════════════════════════════════════════════════════════════

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
@check_feature("feature_students")
@check_tenant_limit("students")
def register_student_view(request):
    """Admin endpoint to create a single student account."""
    serializer = RegisterStudentSerializer(
        data=request.data,
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)

    validated = serializer.validated_data
    password = validated.pop("password")
    validated.pop("password_confirm", None)

    user = User.objects.create_user(
        email=validated["email"].lower().strip(),
        password=password,
        tenant=request.tenant,
        role="STUDENT",
        first_name=validated.get("first_name", ""),
        last_name=validated.get("last_name", ""),
        student_id=validated.get("student_id", ""),
        grade_level=validated.get("grade_level", ""),
        section=validated.get("section", ""),
        parent_email=validated.get("parent_email", ""),
        enrollment_date=validated.get("enrollment_date"),
        must_change_password=True,
    )

    log_audit(
        "CREATE", "User",
        target_id=str(user.id),
        target_repr=str(user),
        changes={
            "email": user.email,
            "role": "STUDENT",
            "student_id": user.student_id,
            "grade_level": user.grade_level,
            "section": user.section,
        },
        request=request,
    )

    return Response(
        StudentSerializer(user, context={"request": request}).data,
        status=status.HTTP_201_CREATED,
    )


# ══════════════════════════════════════════════════════════════════════════
# Student Invitations
# ══════════════════════════════════════════════════════════════════════════

def _serialize_invitation(inv):
    return {
        "id": str(inv.id),
        "email": inv.email,
        "first_name": inv.first_name,
        "last_name": inv.last_name,
        "status": inv.status,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
        "accepted_at": inv.accepted_at.isoformat() if inv.accepted_at else None,
        "invited_by": inv.invited_by.get_full_name() if inv.invited_by else None,
    }


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
@check_feature("feature_students")
def student_invitations_view(request):
    """
    GET: List student invitations.
    POST: Create and send a student invitation.
    """
    tenant = request.tenant

    if request.method == "GET":
        qs = TeacherInvitation.objects.filter(tenant=tenant).order_by("-created_at")
        status_filter = request.GET.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        data = [_serialize_invitation(inv) for inv in qs[:200]]
        return Response(data)

    # POST
    email = (request.data.get("email") or "").strip().lower()
    first_name = (request.data.get("first_name") or "").strip()
    last_name = (request.data.get("last_name") or "").strip()

    if not email or not first_name:
        return Response({"error": "email and first_name are required."}, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(email__iexact=email).exists():
        return Response({"error": "A user with this email already exists."}, status=status.HTTP_400_BAD_REQUEST)

    existing = TeacherInvitation.objects.filter(tenant=tenant, email__iexact=email, status="pending").first()
    if existing and not existing.is_expired:
        return Response({"error": "A pending invitation already exists for this email."}, status=status.HTTP_400_BAD_REQUEST)

    invitation = TeacherInvitation.objects.create(
        tenant=tenant,
        email=email,
        first_name=first_name,
        last_name=last_name,
        invited_by=request.user,
        expires_at=timezone.now() + timezone.timedelta(days=7),
    )

    log_audit("CREATE", "StudentInvitation", target_id=str(invitation.id), target_repr=email, request=request)
    return Response(_serialize_invitation(invitation), status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
@check_feature("feature_students")
@parser_classes([MultiPartParser, FormParser])
def student_bulk_invite_view(request):
    """Bulk invite students via CSV. Columns: email, first_name, last_name (optional)."""
    f = request.FILES.get("file")
    if not f:
        return Response({"error": "CSV file is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        content = f.read().decode("utf-8-sig")
    except Exception:
        return Response({"error": "Could not read file as UTF-8"}, status=status.HTTP_400_BAD_REQUEST)

    reader = csv.DictReader(io.StringIO(content))
    tenant = request.tenant
    results = []
    created_count = 0

    for i, row in enumerate(reader, start=1):
        if i > 500:
            results.append({"row": i, "email": "", "status": "error", "message": "Row limit exceeded (500)"})
            break

        email = (row.get("email") or "").strip().lower()
        first_name = (row.get("first_name") or "").strip()
        last_name = (row.get("last_name") or "").strip()

        if not email or not first_name:
            results.append({"row": i, "email": email, "status": "error", "message": "Missing email or first_name"})
            continue

        if User.objects.filter(email__iexact=email).exists():
            results.append({"row": i, "email": email, "status": "error", "message": "User already exists"})
            continue

        existing = TeacherInvitation.objects.filter(tenant=tenant, email__iexact=email, status="pending").first()
        if existing and not existing.is_expired:
            results.append({"row": i, "email": email, "status": "error", "message": "Pending invitation exists"})
            continue

        try:
            TeacherInvitation.objects.create(
                tenant=tenant,
                email=email,
                first_name=first_name,
                last_name=last_name,
                invited_by=request.user,
                expires_at=timezone.now() + timezone.timedelta(days=7),
            )
            created_count += 1
            results.append({"row": i, "email": email, "status": "success"})
        except Exception:
            results.append({"row": i, "email": email, "status": "error", "message": "Failed to create invitation"})

    if created_count:
        log_audit("IMPORT", "StudentInvitation", target_repr=f"Bulk invite: {created_count} students", changes={"created": created_count}, request=request)

    return Response({"created": created_count, "total_rows": len(results), "results": results}, status=status.HTTP_201_CREATED)
