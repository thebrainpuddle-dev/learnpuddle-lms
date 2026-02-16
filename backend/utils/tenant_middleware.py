# utils/tenant_middleware.py

import re
import threading
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from .tenant_utils import get_tenant_from_request


# Thread-local storage for current tenant
_thread_locals = threading.local()


def get_current_tenant():
    """Get tenant from thread-local storage."""
    return getattr(_thread_locals, 'tenant', None)


def set_current_tenant(tenant):
    """Set tenant in thread-local storage."""
    _thread_locals.tenant = tenant


def clear_current_tenant():
    """Clear tenant from thread-local storage."""
    if hasattr(_thread_locals, 'tenant'):
        delattr(_thread_locals, 'tenant')


class TenantMiddleware:
    """
    Middleware to identify and set current tenant for each request.
    Must be placed AFTER AuthenticationMiddleware.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Clear any previous tenant
        clear_current_tenant()
        
        # Public endpoints: do not enforce tenant-membership check
        # (but we still want tenant resolution for tenant-scoped responses like theme)
        public_paths = [
            '/admin/',
            '/api/auth/register/',  # Tenant registration (future)
            '/api/onboarding/',  # Tenant signup (root domain)
            '/api/users/auth/login/',
            '/api/users/auth/refresh/',
            '/api/users/auth/request-password-reset/',
            '/api/users/auth/confirm-password-reset/',
            '/api/users/auth/verify-email/',
            '/api/tenants/theme/',
            '/api/super-admin/',  # Super admin endpoints (no tenant context needed)
            '/health/',
        ]
        
        try:
            # Always attempt to resolve tenant for API requests, unless explicitly excluded.
            # This keeps behavior consistent for multi-tenant theming and tenant-scoped APIs.
            tenant = None
            try:
                tenant = get_tenant_from_request(request)
                set_current_tenant(tenant)
                request.tenant = tenant
            except Exception:
                # For truly public/non-tenant routes, proceed without tenant.
                tenant = None
            
            # If user is authenticated, verify they belong to this tenant
            if hasattr(request, 'user') and request.user.is_authenticated:
                # Normalize path: /api/v1/... → /api/... for public path matching
                norm_path = re.sub(r'^/api/v\d+/', '/api/', request.path)
                # Skip membership enforcement for public endpoints
                if not any(norm_path.startswith(path) or request.path.startswith(path) for path in public_paths):
                    if request.user.role != 'SUPER_ADMIN':  # Super admins can access any tenant
                        if tenant is None:
                            return JsonResponse({'error': 'Tenant required'}, status=400)
                        if request.user.tenant_id != tenant.id:
                            return JsonResponse(
                                {'error': 'Access denied: User does not belong to this tenant'},
                                status=403
                            )
            
            # Process request
            response = self.get_response(request)
            
            # Clear tenant after response
            clear_current_tenant()
            
            return response
            
        except PermissionDenied as e:
            return JsonResponse(
                {'error': str(e)},
                status=403
            )
        except Exception as e:
            clear_current_tenant()
            return JsonResponse(
                {'error': 'Internal server error'},
                status=500
            )
