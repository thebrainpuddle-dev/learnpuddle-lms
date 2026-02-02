from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .serializers import TenantThemeSerializer
from utils.tenant_utils import get_tenant_from_request
from utils.decorators import admin_only, tenant_required
from .services import TenantService
from .serializers_admin import TenantSettingsSerializer


@api_view(["GET"])
@permission_classes([AllowAny])
def tenant_theme_view(request):
    """
    Public endpoint to bootstrap tenant branding/theme.
    Tenant is derived from request host/subdomain.
    """
    tenant = get_tenant_from_request(request)
    serializer = TenantThemeSerializer(tenant, context={"request": request})
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def tenant_me_view(request):
    """
    Authenticated endpoint to fetch current tenant details.
    """
    tenant = getattr(request, "tenant", None) or get_tenant_from_request(request)
    serializer = TenantThemeSerializer(tenant, context={"request": request})
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def tenant_stats_view(request):
    """
    Tenant-scoped stats for admin dashboard.
    """
    tenant = getattr(request, "tenant", None) or get_tenant_from_request(request)
    return Response(TenantService.get_tenant_stats(tenant), status=status.HTTP_200_OK)


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def tenant_settings_view(request):
    """
    Admin endpoint to fetch/update tenant branding settings.
    Supports multipart PATCH for logo.
    """
    tenant = request.tenant

    if request.method == "GET":
        serializer = TenantSettingsSerializer(tenant, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    serializer = TenantSettingsSerializer(
        tenant, data=request.data, partial=True, context={"request": request}
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_200_OK)
