from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .serializers import TenantThemeSerializer
from utils.tenant_utils import get_tenant_from_request
from utils.decorators import admin_only, tenant_required
from .services import TenantService
from .serializers_admin import TenantSettingsSerializer


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def tenant_theme_view(request):
    """
    Public endpoint to bootstrap tenant branding/theme.
    Tenant is derived from request host/subdomain.

    NOTE: @authentication_classes([]) prevents DRF's JWTAuthentication from
    rejecting stale/expired tokens with 401 before AllowAny is evaluated.
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
@tenant_required
def tenant_config_view(request):
    """
    Return feature flags, plan info, and usage for the current tenant.
    Available to any authenticated user (teachers see features, admins see limits too).
    """
    from apps.tenants.services import get_tenant_usage
    tenant = request.tenant
    is_admin = request.user.role in ("SCHOOL_ADMIN", "SUPER_ADMIN")

    config = {
        "plan": tenant.plan,
        "features": {
            "video_upload": tenant.feature_video_upload,
            "auto_quiz": tenant.feature_auto_quiz,
            "transcripts": tenant.feature_transcripts,
            "reminders": tenant.feature_reminders,
            "custom_branding": tenant.feature_custom_branding,
            "reports_export": tenant.feature_reports_export,
            "groups": tenant.feature_groups,
            "certificates": tenant.feature_certificates,
        },
    }
    if is_admin:
        config["limits"] = {
            "max_teachers": tenant.max_teachers,
            "max_courses": tenant.max_courses,
            "max_storage_mb": tenant.max_storage_mb,
            "max_video_duration_minutes": tenant.max_video_duration_minutes,
        }
        config["usage"] = get_tenant_usage(tenant)
    return Response(config, status=status.HTTP_200_OK)


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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def tenant_analytics_view(request):
    """
    Tenant-scoped analytics data for charts/graphs.
    Query params: course_id (filter by course), months (6–12, default 6).
    """
    tenant = request.tenant
    course_id = request.GET.get("course_id")
    try:
        months = min(12, max(6, int(request.GET.get("months", 6))))
    except (ValueError, TypeError):
        months = 6
    return Response(
        TenantService.get_tenant_analytics(tenant, course_id=course_id, months=months),
        status=status.HTTP_200_OK,
    )


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
