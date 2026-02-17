# apps/media/views.py

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from django.db.models import Count, Q

from utils.decorators import admin_only, tenant_required

from .models import MediaAsset
from .serializers import MediaAssetSerializer, MediaAssetCreateSerializer


class MediaPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
@parser_classes([JSONParser, MultiPartParser, FormParser])
def media_list_create(request):
    """
    GET: List media assets for tenant (paginated, filterable)
    POST: Create new media asset (file upload or link)
    """
    if request.method == 'GET':
        # TenantManager already filters by request.tenant via thread-local;
        # adding tenant= again can cause an empty intersection if they diverge.
        qs = MediaAsset.objects.filter(is_active=True)

        media_type = request.GET.get('media_type')
        if media_type:
            qs = qs.filter(media_type=media_type)

        search = request.GET.get('search')
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(file_name__icontains=search))

        qs = qs.order_by('-created_at')

        paginator = MediaPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = MediaAssetSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    # POST
    serializer = MediaAssetCreateSerializer(
        data=request.data,
        context={'request': request},
    )
    serializer.is_valid(raise_exception=True)
    asset = serializer.save()
    return Response(
        MediaAssetSerializer(asset).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def media_detail(request, asset_id):
    """GET/PATCH/DELETE a single media asset."""
    asset = MediaAsset.objects.filter(id=asset_id).first()
    if not asset:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(MediaAssetSerializer(asset).data)

    if request.method == 'PATCH':
        serializer = MediaAssetSerializer(asset, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        # Only allow updating title, tags
        for field in ['title', 'tags']:
            if field in serializer.validated_data:
                setattr(asset, field, serializer.validated_data[field])
        asset.save()
        return Response(MediaAssetSerializer(asset).data)

    # DELETE (soft: set is_active=False to preserve references)
    asset.is_active = False
    asset.save(update_fields=['is_active', 'updated_at'])
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def media_stats(request):
    """Return counts by media_type for the tenant."""
    stats = MediaAsset.objects.filter(
        is_active=True,
    ).values('media_type').annotate(count=Count('id'))

    result = {'total': 0}
    for row in stats:
        result[row['media_type']] = row['count']
        result['total'] += row['count']

    return Response(result)
