import csv
import io

from django.db import models
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from utils.decorators import admin_only, tenant_required, check_tenant_limit
from .models import User
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
    DELETE: Soft-deactivate a teacher.
    """
    teacher = get_object_or_404(User, id=teacher_id, tenant=request.tenant)
    if teacher.role in ("SCHOOL_ADMIN", "SUPER_ADMIN"):
        return Response({"error": "Cannot modify admin users via this endpoint"}, status=403)

    if request.method == "GET":
        return Response(UserSerializer(teacher).data)

    if request.method == "DELETE":
        teacher.is_active = False
        teacher.save(update_fields=["is_active"])
        return Response({"message": "Teacher deactivated"}, status=status.HTTP_200_OK)

    # PATCH
    SAFE_ROLES = {"TEACHER", "HOD", "IB_COORDINATOR"}
    allowed = {"first_name", "last_name", "department", "employee_id", "subjects", "grades", "role", "is_active"}
    for key, value in request.data.items():
        if key in allowed:
            if key == "role" and value not in SAFE_ROLES:
                return Response({"error": f"Invalid role. Allowed: {', '.join(sorted(SAFE_ROLES))}"}, status=status.HTTP_400_BAD_REQUEST)
            setattr(teacher, key, value)
    teacher.save()
    return Response(UserSerializer(teacher).data)


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

    try:
        content = f.read().decode("utf-8-sig")
    except Exception:
        return Response({"error": "Could not read file as UTF-8"}, status=400)

    reader = csv.DictReader(io.StringIO(content))
    results = []
    created_count = 0

    # Calculate remaining teacher slots so the loop can't exceed the plan limit.
    # Count all teacher-type roles (TEACHER, HOD, IB_COORDINATOR) against the limit.
    tenant = request.tenant
    current_teachers = User.objects.filter(tenant=tenant, role__in=("TEACHER", "HOD", "IB_COORDINATOR"), is_active=True).count()
    remaining_slots = max(0, tenant.max_teachers - current_teachers)

    for i, row in enumerate(reader, start=1):
        email = (row.get("email") or "").strip()
        first_name = (row.get("first_name") or "").strip()
        last_name = (row.get("last_name") or "").strip()
        password = (row.get("password") or "").strip() or "changeme123"

        if not email or not first_name:
            results.append({"row": i, "email": email, "status": "error", "message": "Missing email or first_name"})
            continue

        if User.objects.filter(email=email).exists():
            results.append({"row": i, "email": email, "status": "error", "message": "Email already exists"})
            continue

        if created_count >= remaining_slots:
            results.append({"row": i, "email": email, "status": "error", "message": f"Teacher limit reached ({tenant.max_teachers}). Upgrade your plan to add more."})
            continue

        try:
            User.objects.create_user(
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                department=row.get("department", "").strip(),
                employee_id=row.get("employee_id", "").strip(),
                tenant=tenant,
                role="TEACHER",
                is_active=True,
            )
            created_count += 1
            results.append({"row": i, "email": email, "status": "success"})
        except Exception as e:
            results.append({"row": i, "email": email, "status": "error", "message": str(e)[:200]})

    return Response({"created": created_count, "total_rows": len(results), "results": results}, status=status.HTTP_201_CREATED)

