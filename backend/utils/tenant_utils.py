# utils/tenant_utils.py

from apps.tenants.models import Tenant
from django.core.exceptions import PermissionDenied


def get_tenant_from_request(request):
    """
    Extract tenant from request based on subdomain.
    Examples:
    - abc.lms.com -> subdomain='abc'
    - localhost:8000 -> subdomain='demo' (development)
    """
    host = request.get_host().split(':')[0]  # Remove port
    
    # Development mode - use demo tenant
    if host in ['localhost', '127.0.0.1']:
        subdomain = 'demo'
    else:
        # Extract subdomain from host
        parts = host.split('.')
        if len(parts) < 2:
            raise PermissionDenied("Invalid domain")
        subdomain = parts[0]
    
    try:
        tenant = Tenant.objects.get(subdomain=subdomain, is_active=True)
        return tenant
    except Tenant.DoesNotExist:
        raise PermissionDenied(f"Tenant '{subdomain}' not found or inactive")


def get_current_tenant():
    """
    Get current tenant from thread local storage.
    Used in models and business logic.
    """
    from .tenant_middleware import get_current_tenant as _get_current_tenant
    return _get_current_tenant()
