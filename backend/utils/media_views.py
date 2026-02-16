# utils/media_views.py
"""
Secure media file serving with authentication and tenant isolation.

In production, Django validates access and uses X-Accel-Redirect to have
nginx serve the file efficiently. In development, Django serves directly.
"""

import posixpath
from django.conf import settings
from django.http import HttpResponse, Http404, FileResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated


def _path_is_safe(path: str) -> bool:
    """Check that path doesn't escape the media directory."""
    # Normalize path and check for traversal attempts
    normalized = posixpath.normpath(path)
    if normalized.startswith('/') or normalized.startswith('..'):
        return False
    if '..' in normalized.split('/'):
        return False
    return True


def _get_tenant_from_path(path: str) -> str | None:
    """Extract tenant ID from path like 'tenant/{tenant_id}/uploads/...'"""
    parts = path.split('/')
    if len(parts) >= 2 and parts[0] == 'tenant':
        return parts[1]
    return None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def protected_media_view(request, path):
    """
    Serve media files with authentication and tenant isolation.
    
    Files are stored as: tenant/{tenant_id}/uploads/{type}/{filename}
    Users can only access files belonging to their tenant.
    
    In production (USE_X_ACCEL_REDIRECT=True), returns X-Accel-Redirect header
    for nginx to serve the file efficiently.
    
    In development, serves the file directly via Django.
    """
    # Validate path safety
    if not _path_is_safe(path):
        raise Http404("Invalid path")
    
    # Extract and verify tenant ownership
    path_tenant_id = _get_tenant_from_path(path)
    if path_tenant_id:
        user_tenant_id = str(request.user.tenant_id) if request.user.tenant_id else None
        
        # Super admins can access any tenant's files
        if request.user.role != 'SUPER_ADMIN':
            if user_tenant_id != path_tenant_id:
                raise Http404("File not found")
    
    # Production: Use X-Accel-Redirect for nginx to serve
    use_x_accel = getattr(settings, 'USE_X_ACCEL_REDIRECT', not settings.DEBUG)
    
    if use_x_accel:
        response = HttpResponse()
        response['Content-Type'] = ''  # Let nginx determine
        response['X-Accel-Redirect'] = f'/protected-media/{path}'
        return response
    
    # Development: Serve directly
    import os
    full_path = os.path.join(settings.MEDIA_ROOT, path)
    
    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        raise Http404("File not found")
    
    # Serve with proper content type
    import mimetypes
    content_type, _ = mimetypes.guess_type(full_path)
    
    return FileResponse(
        open(full_path, 'rb'),
        content_type=content_type or 'application/octet-stream'
    )
