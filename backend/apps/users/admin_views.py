import csv
import io
import secrets

from django.db import models
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status

from utils.decorators import admin_only, tenant_required, check_tenant_limit
from utils.audit import log_audit
from .models import User, TeacherInvitation
from .serializers import UserSerializer


class TeacherPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def teachers_list_view(request):
    """
    Admin endpoint to list teachers within the current tenant.
    """
    qs = User.objects.filter(tenant=request.tenant).exclude(role="SCHOOL_ADMIN").exclude(role="SUPER_ADMIN")

    role = request.GET.get("role")
    if role:
        qs = qs.filter(role=role)

    is_active = request.GET.get("is_active")
    if is_active is not None:
        qs = qs.filter(is_active=is_active.lower() == "true")

    search = request.GET.get("search")
    if search:
        qs = qs.filter(
            models.Q(email__icontains=search)
            | models.Q(first_name__icontains=search)
            | models.Q(last_name__icontains=search)
            | models.Q(employee_id__icontains=search)
            | models.Q(department__icontains=search)
        )

    qs = qs.order_by("last_name", "first_name")

    paginator = TeacherPagination()
    page = paginator.paginate_queryset(qs, request)
    if page is not None:
        return paginator.get_paginated_response(UserSerializer(page, many=True).data)
    return Response(UserSerializer(qs, many=True).data, status=status.HTTP_200_OK)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def teacher_detail_view(request, teacher_id):
    """
    GET: Fetch a single teacher.
    PATCH: Update teacher fields (name, department, subjects, grades, role, is_active).
    DELETE: Soft-delete a teacher (preserves data for audit/recovery).
    """
    teacher = get_object_or_404(User, id=teacher_id, tenant=request.tenant)
    if teacher.role in ("SCHOOL_ADMIN", "SUPER_ADMIN"):
        return Response({"error": "Cannot modify admin users via this endpoint"}, status=403)

    if request.method == "GET":
        return Response(UserSerializer(teacher).data)

    if request.method == "DELETE":
        # Use soft delete - preserves user data for audit/recovery
        teacher.delete(deleted_by=request.user)
        log_audit('DELETE', 'User', target_id=str(teacher.id), target_repr=str(teacher), request=request)
        return Response({"message": "Teacher deleted"}, status=status.HTTP_200_OK)

    # PATCH
    SAFE_ROLES = {"TEACHER", "HOD", "IB_COORDINATOR"}
    allowed = {"first_name", "last_name", "department", "employee_id", "subjects", "grades", "role", "is_active"}
    changes = {}
    for key, value in request.data.items():
        if key in allowed:
            if key == "role" and value not in SAFE_ROLES:
                return Response({"error": f"Invalid role. Allowed: {', '.join(sorted(SAFE_ROLES))}"}, status=status.HTTP_400_BAD_REQUEST)
            changes[key] = {"old": getattr(teacher, key), "new": value}
            setattr(teacher, key, value)
    teacher.save()
    log_audit('UPDATE', 'User', target_id=str(teacher.id), target_repr=str(teacher), changes=changes, request=request)
    return Response(UserSerializer(teacher).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def deleted_teachers_list_view(request):
    """
    Admin endpoint to list soft-deleted teachers for potential recovery.
    Returns teachers that have been deleted but not permanently removed.
    """
    # Use all_objects manager to include soft-deleted users
    qs = User.all_objects.filter(
        tenant=request.tenant,
        is_deleted=True
    ).exclude(role__in=["SCHOOL_ADMIN", "SUPER_ADMIN"])

    search = request.GET.get("search")
    if search:
        qs = qs.filter(
            models.Q(email__icontains=search)
            | models.Q(first_name__icontains=search)
            | models.Q(last_name__icontains=search)
        )

    qs = qs.order_by("-deleted_at")

    paginator = TeacherPagination()
    page = paginator.paginate_queryset(qs, request)
    
    # Include deletion metadata in response
    data = []
    for teacher in (page or qs):
        teacher_data = UserSerializer(teacher).data
        teacher_data["deleted_at"] = teacher.deleted_at
        teacher_data["deleted_by"] = str(teacher.deleted_by_id) if teacher.deleted_by_id else None
        data.append(teacher_data)
    
    if page is not None:
        return paginator.get_paginated_response(data)
    return Response(data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def restore_teacher_view(request, teacher_id):
    """
    Restore a soft-deleted teacher.
    The teacher will be reactivated and can log in again.
    """
    # Use all_objects to find deleted teachers
    try:
        teacher = User.all_objects.get(id=teacher_id, tenant=request.tenant, is_deleted=True)
    except User.DoesNotExist:
        return Response({"error": "Deleted teacher not found"}, status=status.HTTP_404_NOT_FOUND)

    if teacher.role in ("SCHOOL_ADMIN", "SUPER_ADMIN"):
        return Response({"error": "Cannot restore admin users via this endpoint"}, status=403)

    teacher.restore()
    log_audit('RESTORE', 'User', target_id=str(teacher.id), target_repr=str(teacher), request=request)
    
    return Response({
        "message": "Teacher restored successfully",
        "teacher": UserSerializer(teacher).data
    }, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
@check_tenant_limit("teachers")
@parser_classes([MultiPartParser, FormParser])
def teachers_bulk_import_view(request):
    """
    Bulk import teachers via CSV upload.
    CSV columns: email, first_name, last_name, password (optional: department, employee_id)
    Returns per-row results with success/error.
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

    # Calculate remaining teacher slots so the loop can't exceed the plan limit.
    # Count all teacher-type roles (TEACHER, HOD, IB_COORDINATOR) against the limit.
    tenant = request.tenant
    current_teachers = User.objects.filter(tenant=tenant, role__in=("TEACHER", "HOD", "IB_COORDINATOR"), is_active=True).count()
    remaining_slots = max(0, tenant.max_teachers - current_teachers)

    def _sanitize_csv_value(val: str) -> str:
        """Strip leading formula-injection characters from CSV cell values."""
        if val and val[0] in ('=', '+', '-', '@', '\t', '\r'):
            return val.lstrip('=+\-@\t\r')
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
                results.append({"row": i, "email": email, "status": "error", "message": "Teacher already exists in this school"})
            else:
                results.append({
                    "row": i, "email": email, "status": "error",
                    "message": "Email is registered with another organization"
                })
            continue

        if created_count >= remaining_slots:
            results.append({"row": i, "email": email, "status": "error", "message": f"Teacher limit reached ({tenant.max_teachers}). Upgrade your plan to add more."})
            continue

        try:
            new_teacher = User.objects.create_user(
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                department=_sanitize_csv_value(row.get("department", "").strip()),
                employee_id=_sanitize_csv_value(row.get("employee_id", "").strip()),
                tenant=tenant,
                role="TEACHER",
                is_active=True,
                must_change_password=force_password_change,
            )
            created_count += 1
            results.append({"row": i, "email": email, "status": "success"})

            try:
                from apps.notifications.tasks import send_teacher_welcome_email
                send_teacher_welcome_email.delay(str(new_teacher.id), password if force_password_change else None)
            except Exception:
                pass  # email is best-effort
        except Exception:
            results.append({"row": i, "email": email, "status": "error", "message": "Failed to create user"})

    if created_count:
        log_audit('IMPORT', 'User', target_repr=f"Bulk import: {created_count} teachers", changes={"created": created_count}, request=request)

    return Response({"created": created_count, "total_rows": len(results), "results": results}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def teachers_bulk_action(request):
    """
    Perform bulk actions on teachers.
    
    POST body:
    {
        "action": "activate" | "deactivate" | "delete",
        "teacher_ids": ["uuid", ...]
    }
    """
    action = (request.data.get('action') or '').lower()
    teacher_ids = request.data.get('teacher_ids', [])
    
    valid_actions = ['activate', 'deactivate', 'delete']
    if action not in valid_actions:
        return Response(
            {'error': f'Invalid action. Must be one of: {", ".join(valid_actions)}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if not teacher_ids or not isinstance(teacher_ids, list):
        return Response(
            {'error': 'teacher_ids must be a non-empty list'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    MAX_BULK_IDS = 100
    if len(teacher_ids) > MAX_BULK_IDS:
        return Response(
            {'error': f'Too many IDs. Maximum {MAX_BULK_IDS} per request.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get teachers within tenant (excluding admins)
    teachers = User.objects.filter(
        id__in=teacher_ids,
        tenant=request.tenant,
    ).exclude(role__in=['SCHOOL_ADMIN', 'SUPER_ADMIN'])
    
    found_count = teachers.count()
    if found_count == 0:
        return Response(
            {'error': 'No valid teachers found with the provided IDs'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    affected_count = 0
    
    if action == 'activate':
        affected_count = teachers.filter(is_active=False).update(is_active=True)
        action_display = 'activated'
    elif action == 'deactivate':
        affected_count = teachers.filter(is_active=True).update(is_active=False)
        action_display = 'deactivated'
    elif action == 'delete':
        # Soft delete - mark as deleted and deactivate
        from django.utils import timezone
        affected_count = teachers.filter(is_deleted=False).update(
            is_deleted=True,
            deleted_at=timezone.now(),
            deleted_by=request.user,
            is_active=False,
        )
        action_display = 'deleted'
    
    log_audit(
        'BULK_ACTION',
        'User',
        target_repr=f"Bulk {action}: {affected_count} teachers",
        changes={'action': action, 'teacher_ids': teacher_ids, 'affected': affected_count},
        request=request
    )
    
    return Response({
        'message': f'Successfully {action_display} {affected_count} teacher(s)',
        'affected_count': affected_count,
        'requested_count': len(teacher_ids),
    }, status=status.HTTP_200_OK)


# ── Teacher Invitation Endpoints ───────────────────────────────────────────


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
def teacher_invitations_view(request):
    """
    GET: List all invitations for this tenant.
    POST: Create and send a single teacher invitation.
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

    existing = TeacherInvitation.objects.filter(
        tenant=tenant, email__iexact=email, status="pending"
    ).first()
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

    from apps.notifications.tasks import send_teacher_invitation_email
    send_teacher_invitation_email.delay(str(invitation.id))

    log_audit("CREATE", "TeacherInvitation", target_id=str(invitation.id), target_repr=email, request=request)
    return Response(_serialize_invitation(invitation), status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
@parser_classes([MultiPartParser, FormParser])
def teacher_bulk_invite_view(request):
    """
    Bulk invite teachers via CSV upload.
    CSV columns: email, first_name, last_name (optional)
    """
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

        existing = TeacherInvitation.objects.filter(
            tenant=tenant, email__iexact=email, status="pending"
        ).first()
        if existing and not existing.is_expired:
            results.append({"row": i, "email": email, "status": "error", "message": "Pending invitation exists"})
            continue

        try:
            invitation = TeacherInvitation.objects.create(
                tenant=tenant,
                email=email,
                first_name=first_name,
                last_name=last_name,
                invited_by=request.user,
                expires_at=timezone.now() + timezone.timedelta(days=7),
            )
            from apps.notifications.tasks import send_teacher_invitation_email
            send_teacher_invitation_email.delay(str(invitation.id))
            created_count += 1
            results.append({"row": i, "email": email, "status": "success"})
        except Exception:
            results.append({"row": i, "email": email, "status": "error", "message": "Failed to create invitation"})

    if created_count:
        log_audit("IMPORT", "TeacherInvitation", target_repr=f"Bulk invite: {created_count} teachers", changes={"created": created_count}, request=request)

    return Response({"created": created_count, "total_rows": len(results), "results": results}, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([AllowAny])
def invitation_validate_view(request, token):
    """Public endpoint: validate an invitation token and return its details."""
    try:
        invitation = TeacherInvitation.objects.select_related("tenant").get(token=token)
    except TeacherInvitation.DoesNotExist:
        return Response({"error": "Invalid invitation link."}, status=status.HTTP_404_NOT_FOUND)

    if invitation.status == "accepted":
        return Response({"error": "This invitation has already been used."}, status=status.HTTP_400_BAD_REQUEST)

    if invitation.is_expired:
        if invitation.status != "expired":
            invitation.status = "expired"
            invitation.save(update_fields=["status"])
        return Response({"error": "This invitation has expired."}, status=status.HTTP_400_BAD_REQUEST)

    return Response({
        "email": invitation.email,
        "first_name": invitation.first_name,
        "last_name": invitation.last_name,
        "school_name": invitation.tenant.name if invitation.tenant else "",
        "expires_at": invitation.expires_at.isoformat(),
    })


@api_view(["POST"])
@permission_classes([AllowAny])
def invitation_accept_view(request, token):
    """Public endpoint: accept an invitation and create the teacher account."""
    try:
        invitation = TeacherInvitation.objects.select_related("tenant").get(token=token)
    except TeacherInvitation.DoesNotExist:
        return Response({"error": "Invalid invitation link."}, status=status.HTTP_404_NOT_FOUND)

    if invitation.status == "accepted":
        return Response({"error": "This invitation has already been used."}, status=status.HTTP_400_BAD_REQUEST)

    if invitation.is_expired:
        if invitation.status != "expired":
            invitation.status = "expired"
            invitation.save(update_fields=["status"])
        return Response({"error": "This invitation has expired."}, status=status.HTTP_400_BAD_REQUEST)

    password = (request.data.get("password") or "").strip()
    if not password or len(password) < 8:
        return Response({"error": "Password must be at least 8 characters."}, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(email__iexact=invitation.email).exists():
        return Response({"error": "An account with this email already exists."}, status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.create_user(
        email=invitation.email,
        password=password,
        first_name=invitation.first_name,
        last_name=invitation.last_name,
        tenant=invitation.tenant,
        role="TEACHER",
        is_active=True,
        email_verified=True,
    )

    invitation.status = "accepted"
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["status", "accepted_at"])

    return Response({
        "message": "Account created successfully. You can now log in.",
        "email": user.email,
    }, status=status.HTTP_201_CREATED)

