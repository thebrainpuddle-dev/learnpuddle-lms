# apps/tenants/superadmin_views.py
"""
Command-center API endpoints for SUPER_ADMIN users.
Allows onboarding schools, listing tenants, impersonation, and platform stats.
"""

import logging

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.throttling import ScopedRateThrottle

from utils.decorators import super_admin_only


from utils.audit import log_audit
from apps.tenants.models import Tenant
from apps.tenants.services import TenantService
from apps.users.models import User
from apps.users.tokens import get_tokens_for_user

from .superadmin_serializers import (
    TenantListSerializer,
    TenantDetailSerializer,
    OnboardTenantSerializer,
    TenantUpdateSerializer,
)

logger = logging.getLogger(__name__)


class ImpersonateThrottle(ScopedRateThrottle):
    scope = 'impersonate'


class TenantPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


# ── Platform-wide stats ────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@super_admin_only
def platform_stats(request):
    """Dashboard stats for the command center."""
    from apps.tenants.services import get_tenant_usage
    from django.db.models import Count

    total_tenants = Tenant.objects.count()
    active_tenants = Tenant.objects.filter(is_active=True).count()
    trial_tenants = Tenant.objects.filter(is_trial=True, is_active=True).count()
    total_users = User.objects.exclude(role="SUPER_ADMIN").count()
    total_teachers = User.objects.filter(role="TEACHER", is_active=True).count()

    # Plan distribution
    plan_dist_qs = Tenant.objects.values("plan").annotate(count=Count("id"))
    plan_distribution = {row["plan"]: row["count"] for row in plan_dist_qs}

    # Recent onboards (last 5)
    recent_onboards = list(
        Tenant.objects.order_by("-created_at")[:5].values("id", "name", "subdomain", "created_at")
    )

    # Schools near limits (>80% of any resource)
    schools_near_limits = []
    usage_errors = 0
    for t in Tenant.objects.filter(is_active=True):
        try:
            usage = get_tenant_usage(t)
        except Exception:
            usage_errors += 1
            logger.exception("platform_stats: usage calculation failed for tenant_id=%s", t.id)
            continue
        for resource, bucket in usage.items():
            if bucket["limit"] > 0 and bucket["used"] / bucket["limit"] > 0.8:
                schools_near_limits.append({
                    "id": str(t.id), "name": t.name, "resource": resource,
                    "used": bucket["used"], "limit": bucket["limit"],
                })

    return Response({
        "total_tenants": total_tenants,
        "active_tenants": active_tenants,
        "trial_tenants": trial_tenants,
        "total_users": total_users,
        "total_teachers": total_teachers,
        "plan_distribution": plan_distribution,
        "recent_onboards": recent_onboards,
        "schools_near_limits": schools_near_limits,
        "degraded": usage_errors > 0,
        "usage_errors": usage_errors,
    })


# ── Tenant list + create ───────────────────────────────────────────────────


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@super_admin_only
def tenant_list_create(request):
    if request.method == "GET":
        qs = Tenant.objects.all().order_by("-created_at")

        # Filters
        is_active = request.GET.get("is_active")
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == "true")
        is_trial = request.GET.get("is_trial")
        if is_trial is not None:
            qs = qs.filter(is_trial=is_trial.lower() == "true")
        search = request.GET.get("search")
        if search:
            qs = qs.filter(name__icontains=search)

        paginator = TenantPagination()
        page = paginator.paginate_queryset(qs, request)
        try:
            serializer = TenantListSerializer(page, many=True, context={"request": request})
            return paginator.get_paginated_response(serializer.data)
        except Exception:
            logger.exception("tenant_list_create: serializer failure, returning degraded payload")
            fallback_rows = []
            for tenant in page:
                try:
                    teacher_count = User.objects.filter(tenant=tenant, role="TEACHER", is_active=True).count()
                    admin_count = User.objects.filter(tenant=tenant, role="SCHOOL_ADMIN", is_active=True).count()
                    from apps.courses.models import Course
                    course_count = Course.objects.filter(tenant=tenant).count()
                except Exception:
                    teacher_count = 0
                    admin_count = 0
                    course_count = 0
                fallback_rows.append({
                    "id": str(tenant.id),
                    "name": tenant.name,
                    "slug": tenant.slug,
                    "subdomain": tenant.subdomain,
                    "email": tenant.email,
                    "is_active": tenant.is_active,
                    "is_trial": tenant.is_trial,
                    "trial_end_date": tenant.trial_end_date,
                    "plan": tenant.plan,
                    "plan_started_at": tenant.plan_started_at,
                    "plan_expires_at": tenant.plan_expires_at,
                    "max_teachers": tenant.max_teachers,
                    "max_courses": tenant.max_courses,
                    "max_storage_mb": tenant.max_storage_mb,
                    "primary_color": tenant.primary_color,
                    "logo": None,
                    "teacher_count": teacher_count,
                    "admin_count": admin_count,
                    "course_count": course_count,
                    "created_at": tenant.created_at,
                    "updated_at": tenant.updated_at,
                })
            response = paginator.get_paginated_response(fallback_rows)
            response.data["degraded"] = True
            return response

    # POST — onboard a new school
    serializer = OnboardTenantSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    d = serializer.validated_data

    result = TenantService.create_tenant_with_admin(
        name=d["school_name"],
        email=d["admin_email"],
        admin_first_name=d["admin_first_name"],
        admin_last_name=d["admin_last_name"],
        admin_password=d["admin_password"],
    )

    # If caller supplied a custom subdomain, override the auto-generated one.
    if d.get("subdomain"):
        tenant = result["tenant"]
        tenant.subdomain = d["subdomain"]
        tenant.save(update_fields=["subdomain"])

    # Send welcome email (best-effort -- logged, never blocks onboarding)
    try:
        from apps.tenants.emails import send_onboard_welcome_email
        send_onboard_welcome_email(result)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Onboarding email failed for tenant=%s err=%s", result["tenant"].id, exc,
        )

    log_audit('CREATE', 'Tenant', target_id=str(result["tenant"].id), target_repr=result["tenant"].name, request=request)

    detail = TenantDetailSerializer(result["tenant"], context={"request": request})
    return Response({
        "tenant": detail.data,
        "admin_email": result["admin"].email,
        "subdomain": result["tenant"].subdomain,
    }, status=status.HTTP_201_CREATED)


# ── Tenant detail / update ─────────────────────────────────────────────────


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
@super_admin_only
def tenant_detail(request, tenant_id):
    tenant = get_object_or_404(Tenant, id=tenant_id)

    if request.method == "GET":
        serializer = TenantDetailSerializer(tenant, context={"request": request})
        return Response(serializer.data)

    serializer = TenantUpdateSerializer(tenant, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    log_audit('UPDATE', 'Tenant', target_id=str(tenant.id), target_repr=tenant.name, changes=dict(serializer.validated_data), request=request)
    return Response(TenantDetailSerializer(tenant, context={"request": request}).data)


# ── Impersonate (generate admin token for a school) ────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([ImpersonateThrottle])
@super_admin_only
def tenant_impersonate(request, tenant_id):
    """Generate a short-lived admin JWT for the given tenant's SCHOOL_ADMIN."""
    tenant = get_object_or_404(Tenant, id=tenant_id)
    admin_user = User.objects.filter(tenant=tenant, role="SCHOOL_ADMIN", is_active=True).first()
    if not admin_user:
        return Response({"error": "No active admin found for this tenant"}, status=404)

    # Generate short-lived access token (15 min) with NO refresh token
    from datetime import timedelta
    from rest_framework_simplejwt.tokens import AccessToken
    access = AccessToken.for_user(admin_user)
    access.set_exp(lifetime=timedelta(minutes=15))
    access['email'] = admin_user.email
    access['role'] = admin_user.role
    access['tenant_id'] = str(admin_user.tenant_id) if admin_user.tenant_id else None
    access['is_impersonation'] = True

    log_audit('LOGIN', 'Tenant', target_id=str(tenant.id), target_repr=f"Impersonate {tenant.name} as {admin_user.email}", request=request)

    return Response({
        "tokens": {"access": str(access)},
        "user_email": admin_user.email,
        "tenant_subdomain": tenant.subdomain,
        "expires_in_minutes": 15,
    })


# ── Tenant usage ───────────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@super_admin_only
def tenant_usage(request, tenant_id):
    """Return current resource usage vs limits for a tenant."""
    from apps.tenants.services import get_tenant_usage
    tenant = get_object_or_404(Tenant, id=tenant_id)
    try:
        usage = get_tenant_usage(tenant)
        usage["degraded"] = False
    except Exception:
        logger.exception("tenant_usage: usage calculation failed for tenant_id=%s", tenant.id)
        usage = {
            "teachers": {"used": 0, "limit": tenant.max_teachers},
            "courses": {"used": 0, "limit": tenant.max_courses},
            "storage_mb": {"used": 0, "limit": tenant.max_storage_mb},
            "degraded": True,
        }
    return Response(usage)


# ── Apply plan preset ──────────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@super_admin_only
def tenant_apply_plan(request, tenant_id):
    """Apply a plan preset to a tenant. Optionally override individual fields."""
    from apps.tenants.services import apply_plan_preset, PLAN_PRESETS
    tenant = get_object_or_404(Tenant, id=tenant_id)
    plan = request.data.get("plan")
    if not plan or plan not in PLAN_PRESETS:
        return Response({"error": f"Invalid plan. Choose from: {list(PLAN_PRESETS.keys())}"}, status=400)

    apply_plan_preset(tenant, plan, save=True)

    # Apply any extra overrides — only safe, plan-related fields
    ALLOWED_PLAN_OVERRIDES = {
        "max_teachers", "max_courses", "max_storage_mb", "max_video_duration_minutes",
        "feature_video_upload", "feature_auto_quiz", "feature_transcripts",
        "feature_reminders", "feature_custom_branding", "feature_reports_export",
        "feature_groups", "feature_certificates", "feature_teacher_authoring",
        "is_trial", "trial_end_date", "plan_expires_at",
    }
    overrides = {k: v for k, v in request.data.items() if k != "plan" and k in ALLOWED_PLAN_OVERRIDES}
    if overrides:
        for k, v in overrides.items():
            setattr(tenant, k, v)
        tenant.save()

    log_audit('SETTINGS_CHANGE', 'Tenant', target_id=str(tenant.id), target_repr=tenant.name, changes={"plan": plan, **overrides}, request=request)

    return Response(TenantDetailSerializer(tenant, context={"request": request}).data)


# ── Reset admin password ──────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@super_admin_only
def tenant_reset_admin_password(request, tenant_id):
    """Reset the school admin's password and send a reset link email."""
    tenant = get_object_or_404(Tenant, id=tenant_id)
    admin_user = User.objects.filter(tenant=tenant, role="SCHOOL_ADMIN", is_active=True).first()
    if not admin_user:
        return Response({"error": "No active admin found"}, status=404)

    # Generate a token-based reset link instead of sending plaintext password
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.http import urlsafe_base64_encode
    from django.utils.encoding import force_bytes
    from django.core.mail import send_mail

    # If caller provided a new password, set it directly
    new_password = request.data.get("new_password")
    if new_password:
        admin_user.set_password(new_password)
        admin_user.save()

    # Generate reset link for email (regardless of whether password was set)
    uid = urlsafe_base64_encode(force_bytes(admin_user.pk))
    token = default_token_generator.make_token(admin_user)
    domain = getattr(settings, 'PLATFORM_DOMAIN', 'lms.com')
    reset_link = f"https://{tenant.subdomain}.{domain}/reset-password?uid={uid}&token={token}"

    # Send reset link email -- logged, never blocks the reset action
    try:
        send_mail(
            subject=f"Password reset — {getattr(settings, 'PLATFORM_NAME', 'LearnPuddle')}",
            message=(
                f"Hi {admin_user.first_name},\n\n"
                f"Your password has been reset by the platform admin.\n\n"
                f"Click the link below to set a new password:\n\n"
                f"  {reset_link}\n\n"
                f"This link expires in 24 hours.\n\n"
                f"If you didn't expect this, please contact your administrator."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[admin_user.email],
            fail_silently=getattr(settings, "EMAIL_FAIL_SILENTLY", False),
        )
        import logging
        logging.getLogger(__name__).info(
            "Password reset email sent tenant=%s to=%s", tenant_id, admin_user.email,
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Password reset email failed tenant=%s to=%s err=%s", tenant_id, admin_user.email, exc,
        )

    log_audit('PASSWORD_RESET', 'User', target_id=str(admin_user.id), target_repr=str(admin_user), request=request, tenant=tenant)

    return Response({"message": "Password reset successfully", "email": admin_user.email})


# ── Send custom email to a tenant ──────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@super_admin_only
def tenant_send_email(request, tenant_id):
    """
    Send a custom email to a tenant's admin or any specified address.
    POST body: { "to": "optional@email.com", "subject": "...", "body": "..." }
    If `to` is omitted, sends to the tenant's active school admin.
    """
    from django.core.mail import send_mail as _send_mail

    tenant = get_object_or_404(Tenant, id=tenant_id)

    to_email = (request.data.get("to") or "").strip()
    subject = (request.data.get("subject") or "").strip()
    body = (request.data.get("body") or "").strip()

    if not subject:
        return Response({"error": "Subject is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not body:
        return Response({"error": "Body is required."}, status=status.HTTP_400_BAD_REQUEST)

    if not to_email:
        admin_user = User.objects.filter(tenant=tenant, role="SCHOOL_ADMIN", is_active=True).first()
        if not admin_user:
            return Response({"error": "No active admin found for this tenant."}, status=status.HTTP_404_NOT_FOUND)
        to_email = admin_user.email

    platform_name = getattr(settings, "PLATFORM_NAME", "LearnPuddle")

    try:
        _send_mail(
            subject=f"[{platform_name}] {subject}",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            fail_silently=False,
        )
    except Exception as exc:
        logger.error("Custom email failed tenant=%s to=%s err=%s", tenant_id, to_email, exc)
        return Response({"error": f"Email delivery failed: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)

    logger.info("Custom email sent tenant=%s to=%s subject=%s by=%s", tenant_id, to_email, subject, request.user.email)
    log_audit(
        "SEND_EMAIL", "Tenant",
        target_id=str(tenant_id),
        target_repr=f'"{subject}" to {to_email}',
        request=request,
        tenant=tenant,
    )

    return Response({"sent": True, "to": to_email, "subject": subject})
