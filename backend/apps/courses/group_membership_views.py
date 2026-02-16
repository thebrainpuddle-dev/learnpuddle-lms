from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status

from utils.decorators import admin_only, tenant_required
from apps.users.models import User
from apps.users.serializers import UserSerializer
from .models import TeacherGroup


class MemberPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


def _get_group(request, group_id):
    return get_object_or_404(TeacherGroup, id=group_id, tenant=request.tenant)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def teacher_group_members(request, group_id):
    """
    GET: List members (teachers) in a group.
    POST: Add members via { teacher_ids: [uuid,...] } or { teacher_id: uuid }.
    """
    group = _get_group(request, group_id)

    if request.method == "GET":
        members = group.members.filter(tenant=request.tenant).order_by("last_name", "first_name")
        paginator = MemberPagination()
        page = paginator.paginate_queryset(members, request)
        if page is not None:
            return paginator.get_paginated_response(UserSerializer(page, many=True).data)
        return Response(UserSerializer(members, many=True).data, status=status.HTTP_200_OK)

    teacher_ids = request.data.get("teacher_ids")
    teacher_id = request.data.get("teacher_id")

    if teacher_ids is None and teacher_id is None:
        return Response(
            {"error": "Provide teacher_ids (list) or teacher_id"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if teacher_ids is None:
        teacher_ids = [teacher_id]

    # Only allow adding teachers within this tenant and non-admin roles
    teachers = User.objects.filter(
        tenant=request.tenant,
        id__in=teacher_ids,
        role__in=["TEACHER", "HOD", "IB_COORDINATOR"],
    )

    group.members.add(*teachers)
    members = group.members.filter(tenant=request.tenant).order_by("last_name", "first_name")
    return Response(UserSerializer(members, many=True).data, status=status.HTTP_200_OK)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def teacher_group_member_remove(request, group_id, teacher_id):
    """
    DELETE: Remove a teacher from a group.
    """
    group = _get_group(request, group_id)
    teacher = get_object_or_404(User, id=teacher_id, tenant=request.tenant)
    group.members.remove(teacher)
    return Response(status=status.HTTP_204_NO_CONTENT)

