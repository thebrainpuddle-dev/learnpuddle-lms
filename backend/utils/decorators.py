# utils/decorators.py

from functools import wraps
from rest_framework.exceptions import PermissionDenied
from .tenant_middleware import get_current_tenant


def tenant_required(view_func):
    """
    Decorator to ensure a tenant exists in the request.
    Use on API views that require tenant context.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        tenant = get_current_tenant()
        if not tenant:
            raise PermissionDenied("Tenant context required")
        # Also ensure request.tenant is available
        if not hasattr(request, 'tenant') or request.tenant is None:
            request.tenant = tenant
        return view_func(request, *args, **kwargs)
    return wrapper


def admin_only(view_func):
    """
    Decorator to restrict access to school admins only.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required")
        
        if request.user.role not in ['SCHOOL_ADMIN', 'SUPER_ADMIN']:
            raise PermissionDenied("Admin access required")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def super_admin_only(view_func):
    """
    Decorator to restrict access to platform super admins only.
    Used for the command-center / tenant management APIs.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required")
        if request.user.role != 'SUPER_ADMIN':
            raise PermissionDenied("Super admin access required")
        return view_func(request, *args, **kwargs)
    return wrapper


def teacher_or_admin(view_func):
    """
    Decorator for views accessible by teachers and admins.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required")
        
        if request.user.role not in ['TEACHER', 'SCHOOL_ADMIN', 'SUPER_ADMIN', 'HOD', 'IB_COORDINATOR']:
            raise PermissionDenied("Teacher or admin access required")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def check_feature(feature_name):
    """
    Decorator that checks a tenant feature flag before allowing access.
    Usage: @check_feature('feature_video_upload')
    Returns 403 with upgrade_required flag if feature is disabled.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            tenant = getattr(request, 'tenant', None) or get_current_tenant()
            if tenant and not getattr(tenant, feature_name, False):
                from rest_framework.response import Response
                return Response(
                    {"error": "This feature is not available on your plan.", "upgrade_required": True, "feature": feature_name},
                    status=403,
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def check_tenant_limit(resource_name):
    """
    Decorator that checks a tenant resource limit before allowing creation.
    Usage: @check_tenant_limit('teachers')  — checks max_teachers vs actual count.
    Returns 403 with upgrade_required flag if at/over limit.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            tenant = getattr(request, 'tenant', None) or get_current_tenant()
            if tenant:
                from apps.tenants.services import check_limit
                if not check_limit(tenant, resource_name):
                    from rest_framework.response import Response
                    return Response(
                        {"error": f"You have reached the maximum number of {resource_name} on your plan.", "upgrade_required": True, "resource": resource_name},
                        status=403,
                    )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
