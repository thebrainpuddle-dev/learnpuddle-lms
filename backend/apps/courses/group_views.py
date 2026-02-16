from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status

from utils.decorators import admin_only, tenant_required
from .models import TeacherGroup
from .group_serializers import TeacherGroupSerializer


class GroupPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def teacher_group_list_create(request):
    if request.method == "GET":
        qs = TeacherGroup.objects.filter(tenant=request.tenant).order_by("name")
        paginator = GroupPagination()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            return paginator.get_paginated_response(TeacherGroupSerializer(page, many=True).data)
        return Response(TeacherGroupSerializer(qs, many=True).data, status=status.HTTP_200_OK)

    serializer = TeacherGroupSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    group = serializer.save(tenant=request.tenant)
    return Response(TeacherGroupSerializer(group).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def teacher_group_detail(request, group_id):
    group = get_object_or_404(TeacherGroup, id=group_id, tenant=request.tenant)

    if request.method == "GET":
        return Response(TeacherGroupSerializer(group).data, status=status.HTTP_200_OK)

    if request.method == "PATCH":
        serializer = TeacherGroupSerializer(group, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    group.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

