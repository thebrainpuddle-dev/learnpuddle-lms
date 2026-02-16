# utils/tenant_utils.py

from apps.tenants.models import Tenant
from django.core.exceptions import PermissionDenied


def get_tenant_from_request(request):
    """
    Extract tenant from request based on subdomain or custom domain.
    
    Lookup order:
    1. Custom domain (e.g., lms.school.edu)
    2. Subdomain (e.g., school.lms.com)
    3. Development fallback (localhost -> demo)
    
    Examples:
    - lms.school.edu -> custom_domain='lms.school.edu'
    - abc.lms.com -> subdomain='abc'
    - localhost:8000 -> subdomain='demo' (development)
    """
    host = request.get_host().split(':')[0].lower()  # Remove port, lowercase
    
    # Development mode - use demo tenant
    if host in ['localhost', '127.0.0.1']:
        subdomain = 'demo'
    else:
        # First, try to match a custom domain
        try:
            tenant = Tenant.objects.get(
                custom_domain=host,
                custom_domain_verified=True,
                is_active=True
            )
            return tenant
        except Tenant.DoesNotExist:
            pass
        
        # Fall back to subdomain matching
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
