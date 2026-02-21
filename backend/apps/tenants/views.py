from django.conf import settings
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .serializers import TenantThemeSerializer
from utils.tenant_utils import get_tenant_from_request
from utils.decorators import admin_only, tenant_required
from utils.audit import log_audit
from .services import TenantService
from .serializers_admin import TenantSettingsSerializer


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def tenant_theme_view(request):
    """
    Public endpoint to bootstrap tenant branding/theme.
    Tenant is derived from request host/subdomain (set by middleware).
    
    Returns tenant_found=true with full theme data for active tenants.
    Returns tenant_found=false with reason when tenant is missing/inactive,
    so the frontend can display an appropriate error message.
    """
    from apps.tenants.models import Tenant
    
    tenant = getattr(request, "tenant", None)
    
    if tenant is None:
        host = request.get_host().split(':')[0].lower()
        platform_domain = getattr(settings, 'PLATFORM_DOMAIN', '').lower()

        # Platform root (learnpuddle.com) or localhost — no tenant expected; return default theme
        # so super-admin, signup, and marketing pages can render
        is_platform_root = (
            (platform_domain and host == platform_domain) or
            host in ('localhost', '127.0.0.1')
        )
        if is_platform_root:
            return Response({
                "tenant_found": True,
                "name": "LearnPuddle",
                "subdomain": "",
                "logo_url": None,
                "primary_color": "#1F4788",
                "secondary_color": "#2E5C8A",
                "font_family": "Inter",
                "is_active": True,
            }, status=status.HTTP_200_OK)

        # Subdomain or other host — check if tenant exists but is inactive
        subdomain = None
        reason = "not_found"
        inactive_tenant = None

        if host not in ['localhost', '127.0.0.1']:
            parts = host.split('.')
            if len(parts) >= 2:
                subdomain = parts[0]

        # Check if an inactive tenant exists with this subdomain
        if subdomain:
            inactive_tenant = Tenant.objects.filter(subdomain=subdomain, is_active=False).first()
            if inactive_tenant:
                reason = "trial_expired" if inactive_tenant.is_trial else "deactivated"
        
        return Response({
            "tenant_found": False,
            "reason": reason,
            "subdomain": subdomain,
            "name": "School Not Found" if reason == "not_found" else inactive_tenant.name if inactive_tenant else "School",
            "logo_url": None,
            "primary_color": "#1F4788",
            "secondary_color": "#2E5C8A",
            "font_family": "Inter",
            "is_active": False,
            "is_trial": inactive_tenant.is_trial if inactive_tenant else False,
            "trial_end_date": str(inactive_tenant.trial_end_date) if inactive_tenant and inactive_tenant.trial_end_date else None,
            "message": _get_tenant_error_message(reason, inactive_tenant),
        }, status=status.HTTP_200_OK)
    
    data = TenantThemeSerializer(tenant, context={"request": request}).data
    data["tenant_found"] = True
    return Response(data, status=status.HTTP_200_OK)


def _get_tenant_error_message(reason, tenant):
    """Return user-friendly error message based on tenant status."""
    if reason == "trial_expired":
        return "Your school's trial period has expired. Please contact support to reactivate your account or upgrade your plan."
    elif reason == "deactivated":
        return "This school's account has been deactivated. Please contact your administrator or support for assistance."
    else:
        return "School not found. Please check the URL or contact support if you believe this is an error."


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
            "teacher_authoring": tenant.feature_teacher_authoring,
        },
    }
    if is_admin:
        config["limits"] = {
            "max_teachers": tenant.max_teachers,
            "max_courses": tenant.max_courses,
            "max_storage_mb": tenant.max_storage_mb,
            "max_video_duration_minutes": tenant.max_video_duration_minutes,
        }
        try:
            config["usage"] = get_tenant_usage(tenant)
            config["degraded"] = False
        except Exception:
            # Usage should never hard-fail tenant app bootstrap.
            config["usage"] = {
                "teachers": {"used": 0, "limit": tenant.max_teachers},
                "courses": {"used": 0, "limit": tenant.max_courses},
                "storage_mb": {"used": 0, "limit": tenant.max_storage_mb},
            }
            config["degraded"] = True
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
    log_audit('SETTINGS_CHANGE', 'Tenant', target_id=str(tenant.id), target_repr=tenant.name, request=request)
    return Response(serializer.data, status=status.HTTP_200_OK)
