# utils/tenant_utils.py

from django.conf import settings
from django.core.exceptions import PermissionDenied

from apps.tenants.models import Tenant


def _normalize_host(request) -> str:
    host = request.get_host().split(":")[0].strip().lower()
    return host.rstrip(".")


def _extract_platform_subdomain(host: str, platform_domain: str) -> str | None:
    suffix = f".{platform_domain}"
    if not host.endswith(suffix):
        return None
    subdomain = host[: -len(suffix)]
    if not subdomain or "." in subdomain or subdomain == "www":
        return None
    return subdomain


def get_tenant_from_request(request):
    """
    Resolve tenant only from known-safe host shapes.

    Allowed host patterns:
    1. Platform root (learnpuddle.com / www.learnpuddle.com) -> None
    2. localhost/127.0.0.1 -> demo tenant (dev fallback)
    3. Verified custom domain (exact match)
    4. Single-label subdomain under PLATFORM_DOMAIN (school.learnpuddle.com)
    """
    host = _normalize_host(request)
    if not host:
        raise PermissionDenied("Invalid host header")

    if host in {"localhost", "127.0.0.1"}:
        subdomain = "demo"
        try:
            return Tenant.objects.get(subdomain=subdomain, is_active=True)
        except Tenant.DoesNotExist:
            raise PermissionDenied(f"Tenant '{subdomain}' not found or inactive")

    platform_domain = getattr(settings, "PLATFORM_DOMAIN", "").strip().lower().rstrip(".")
    if platform_domain and host in {platform_domain, f"www.{platform_domain}"}:
        return None

    tenant = Tenant.objects.filter(
        custom_domain=host,
        custom_domain_verified=True,
        is_active=True,
    ).first()
    if tenant:
        return tenant

    if platform_domain:
        subdomain = _extract_platform_subdomain(host, platform_domain)
        if subdomain:
            try:
                return Tenant.objects.get(subdomain=subdomain, is_active=True)
            except Tenant.DoesNotExist:
                raise PermissionDenied(f"Tenant '{subdomain}' not found or inactive")
        if host.endswith(f".{platform_domain}"):
            raise PermissionDenied("Invalid platform host")

    raise PermissionDenied("Unknown host")


def get_current_tenant():
    """
    Get current tenant from thread local storage.
    Used in models and business logic.
    """
    from .tenant_middleware import get_current_tenant as _get_current_tenant
    return _get_current_tenant()
