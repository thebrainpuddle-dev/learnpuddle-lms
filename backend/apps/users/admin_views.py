from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from utils.decorators import admin_only, tenant_required
from .models import User
from .serializers import UserSerializer
from django.db import models


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def teachers_list_view(request):
    """
    Admin endpoint to list teachers within the current tenant.
    Query params:
      - search: substring match on name/email
      - role: TEACHER|HOD|IB_COORDINATOR
      - is_active: true|false
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
    return Response(UserSerializer(qs, many=True).data, status=status.HTTP_200_OK)

