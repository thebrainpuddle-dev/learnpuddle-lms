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
