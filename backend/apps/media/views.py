# apps/media/views.py

import logging

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

logger = logging.getLogger(__name__)


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

    Security invariants (tenant isolation + path-traversal):

    1. Reject any path containing ``..``, NUL bytes, CR/LF, or backslash —
       these are non-portable and the only legitimate sources of them
       in this endpoint are attempted traversal / header injection.
    2. After ``posixpath.normpath`` the path must not be absolute and
       must not escape upward (no ``..`` segments).
    3. Non-SUPER_ADMIN users may only fetch files whose path begins with
       ``tenant/<their-tenant-id>/``.  Files outside that prefix are
       considered cross-tenant or platform-internal and are denied.
       Previously, paths that did not contain a ``tenant/`` segment at
       all silently bypassed the tenant check.
    4. For local storage the resolved real path must stay strictly
       beneath ``MEDIA_ROOT`` — symlinks pointing outside the tree are
       rejected via ``os.path.realpath``.
    5. The X-Accel-Redirect header is built from the *normalized* path
       only (raw input never reaches the response).

    For S3 storage: Generates a signed URL and redirects.
    For local storage: Serves via X-Accel-Redirect (prod) or directly (dev).
    """
    import os
    import posixpath

    # ── Step 1: Reject obviously-malicious characters BEFORE normalize.
    # ``\``, NUL, CR, LF can survive posixpath.normpath but break header
    # safety (X-Accel-Redirect) and storage backends in surprising ways.
    if (
        not path
        or '\x00' in path
        or '\r' in path
        or '\n' in path
        or '\\' in path
    ):
        raise Http404("Invalid path")

    # ── Step 2: Normalize and re-validate. After this point we use
    # ``normalized`` everywhere — never raw ``path``.
    normalized = posixpath.normpath(path)
    if (
        normalized.startswith('/')
        or normalized == '..'
        or normalized.startswith('../')
        or '/../' in normalized
        or normalized.endswith('/..')
    ):
        raise Http404("Invalid path")

    # ── Step 3: Tenant prefix enforcement (defense in depth).
    # SUPER_ADMIN can fetch anything; everyone else must be inside
    # their own tenant subtree.  Refusing paths that lack the
    # ``tenant/<id>/`` prefix closes the previous gap where a request
    # for ``videos/<id>/segment.ts`` (no tenant segment) bypassed the
    # cross-tenant check entirely.
    parts = normalized.split('/')
    path_tenant_id = None
    if len(parts) >= 2 and parts[0] == 'tenant':
        path_tenant_id = parts[1]

    if request.user.role != 'SUPER_ADMIN':
        user_tenant_id = (
            str(request.user.tenant_id) if request.user.tenant_id else None
        )
        # NOTE: ``user_tenant_id`` may be None for unbound users (e.g. a
        # mis-provisioned non-SUPER_ADMIN with tenant_id=NULL). The
        # falsy compare below MUST remain a strict inequality — do NOT
        # "simplify" to ``if user_tenant_id and user_tenant_id != ...``
        # which would *bypass* the check on None and let an unbound
        # user fetch any file. Both ``not path_tenant_id`` and
        # ``None != "..."`` are intentionally truthy denial paths.
        if not path_tenant_id or user_tenant_id != path_tenant_id:
            # Treat as 404 (not 403) so we don't leak existence of
            # cross-tenant or platform-internal files.
            raise Http404("File not found")

    # ── Step 4: Existence check uses the normalized path.
    if not default_storage.exists(normalized):
        raise Http404("File not found")

    # ── Step 5: S3 signed URL.
    storage_backend = getattr(settings, 'STORAGE_BACKEND', 'local').lower()
    if storage_backend == 's3':
        try:
            storage = default_storage
            signed_url = storage.url(
                normalized,
                parameters={'ResponseContentDisposition': 'inline'},
            )

            if not getattr(settings, 'AWS_QUERYSTRING_AUTH', False):
                client = storage.connection.meta.client
                bucket_name = storage.bucket_name
                signed_url = client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': bucket_name, 'Key': normalized},
                    ExpiresIn=3600,  # 1 hour
                )

            return HttpResponseRedirect(signed_url)
        except Exception as exc:
            # Log S3 signed-URL failures so ops can detect misconfiguration;
            # fall through to local-serve path as a best-effort fallback.
            logger.warning(
                "media: S3 signed-URL generation failed for path=%s — falling back to direct serve: %s",
                normalized, exc,
            )

    # ── Step 6: Local storage. X-Accel-Redirect path comes from the
    # normalized value so CR/LF or .. cannot reach nginx.
    use_x_accel = getattr(settings, 'USE_X_ACCEL_REDIRECT', not settings.DEBUG)

    if use_x_accel:
        response = HttpResponse()
        response['Content-Type'] = ''  # Let nginx determine
        response['X-Accel-Redirect'] = f'/protected-media/{normalized}'
        return response

    # ── Step 7: Development direct-serve. Resolve realpath and require
    # it to stay beneath MEDIA_ROOT — defeats symlink escapes.
    import mimetypes
    media_root = os.path.realpath(settings.MEDIA_ROOT)
    candidate = os.path.realpath(os.path.join(settings.MEDIA_ROOT, normalized))

    # Use os.path.commonpath rather than .startswith to avoid the
    # classic ``/var/www/media-evil`` vs ``/var/www/media`` prefix bug.
    try:
        if os.path.commonpath([candidate, media_root]) != media_root:
            raise Http404("Invalid path")
    except ValueError:
        # commonpath raises on different drives (Windows) or empty input.
        raise Http404("Invalid path")

    if not os.path.exists(candidate) or not os.path.isfile(candidate):
        raise Http404("File not found")

    content_type, _ = mimetypes.guess_type(candidate)
    return FileResponse(
        open(candidate, 'rb'),
        content_type=content_type or 'application/octet-stream',
    )
