# apps/media/views.py

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, FileResponse, HttpResponseRedirect

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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@tenant_required
def serve_media_file(request, path):
    """
    Serve media files with authentication and tenant isolation.
    
    For S3 storage: Generates a signed URL and redirects.
    For local storage: Serves via X-Accel-Redirect (prod) or directly (dev).
    """
    import posixpath
    
    # Validate path safety
    normalized = posixpath.normpath(path)
    if normalized.startswith('/') or normalized.startswith('..') or '..' in normalized.split('/'):
        raise Http404("Invalid path")
    
    # Extract tenant from path and verify access
    parts = path.split('/')
    path_tenant_id = None
    for i, part in enumerate(parts):
        if part == 'tenant' and i + 1 < len(parts):
            path_tenant_id = parts[i + 1]
            break
    
    if path_tenant_id:
        user_tenant_id = str(request.user.tenant_id) if request.user.tenant_id else None
        # Super admins can access any tenant's files
        if request.user.role != 'SUPER_ADMIN' and user_tenant_id != path_tenant_id:
            raise Http404("File not found")
    
    # Check if file exists in storage
    if not default_storage.exists(path):
        raise Http404("File not found")
    
    # For S3 storage, generate signed URL and redirect
    storage_backend = getattr(settings, 'STORAGE_BACKEND', 'local').lower()
    if storage_backend == 's3':
        # Generate a time-limited signed URL
        try:
            from botocore.config import Config
            from storages.backends.s3boto3 import S3Boto3Storage
            
            storage = default_storage
            # Generate signed URL (expires in 1 hour)
            signed_url = storage.url(path, parameters={'ResponseContentDisposition': 'inline'})
            
            # If querystring_auth is disabled, we need to generate a signed URL manually
            if not getattr(settings, 'AWS_QUERYSTRING_AUTH', False):
                # Access the underlying boto3 client
                client = storage.connection.meta.client
                bucket_name = storage.bucket_name
                
                signed_url = client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': bucket_name, 'Key': path},
                    ExpiresIn=3600  # 1 hour
                )
            
            return HttpResponseRedirect(signed_url)
        except Exception:
            # Fallback: try to serve directly if signed URL fails
            pass
    
    # Local storage: serve via X-Accel-Redirect (prod) or directly (dev)
    use_x_accel = getattr(settings, 'USE_X_ACCEL_REDIRECT', not settings.DEBUG)
    
    if use_x_accel:
        response = HttpResponse()
        response['Content-Type'] = ''  # Let nginx determine
        response['X-Accel-Redirect'] = f'/protected-media/{path}'
        return response
    
    # Development: Serve directly
    import os
    import mimetypes
    full_path = os.path.join(settings.MEDIA_ROOT, path)
    
    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        raise Http404("File not found")
    
    content_type, _ = mimetypes.guess_type(full_path)
    return FileResponse(
        open(full_path, 'rb'),
        content_type=content_type or 'application/octet-stream'
    )
