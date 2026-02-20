# utils/tenant_utils.py

from django.conf import settings
from django.core.exceptions import PermissionDenied

from apps.tenants.models import Tenant


def get_tenant_from_request(request):
    """
    Extract tenant from request based on subdomain or custom domain.
    
    Lookup order:
    1. Platform root (learnpuddle.com) -> None (command center, signup)
    2. Custom domain (e.g., lms.school.edu)
    3. Subdomain (e.g., school.learnpuddle.com)
    4. Development fallback (localhost -> demo)
    
    Examples:
    - learnpuddle.com -> None (platform root)
    - lms.school.edu -> custom_domain='lms.school.edu'
    - school.learnpuddle.com -> subdomain='school'
    - localhost:8000 -> subdomain='demo' (development)
    """
    host = request.get_host().split(':')[0].lower()  # Remove port, lowercase

    # Development mode - use demo tenant
    if host in ['localhost', '127.0.0.1']:
        subdomain = 'demo'
    else:
        # Platform root — no tenant (command center, signup, marketing)
        platform_domain = getattr(settings, 'PLATFORM_DOMAIN', '').lower()
        if platform_domain and host == platform_domain:
            return None

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
