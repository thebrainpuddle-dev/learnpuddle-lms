import logging
from urllib.parse import urlparse

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from utils.decorators import admin_only, tenant_required
from utils.helpers import make_pagination_class
from utils.responses import error_response

from .models import SubscriptionPlan, TenantSubscription, PaymentHistory
from .serializers import (
    CheckoutSessionSerializer,
    PaymentHistorySerializer,
    PlanChangePreviewSerializer,
    SubscriptionPlanSerializer,
    TenantSubscriptionSerializer,
)

logger = logging.getLogger(__name__)


def _is_tenant_redirect_url_allowed(url: str, tenant) -> bool:
    """Validate that a user-supplied redirect URL belongs to this tenant.

    Prevents open-redirect attacks via Stripe Checkout / Customer Portal:
    an attacker with tenant-admin access could otherwise supply an arbitrary
    return_url, obtain a signed Stripe URL, and phish other admins who
    authenticate on Stripe and are then bounced to the attacker's domain.

    Accepts only:
      - https://<tenant.subdomain>.<PLATFORM_DOMAIN>[/...]
      - https://<tenant.custom_domain>[/...]  (when verified)
      - localhost variants in DEBUG mode
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    scheme = (parsed.scheme or '').lower()
    host = (parsed.hostname or '').lower()
    if not host:
        return False

    # Enforce https in production; allow http only when DEBUG=True (local dev).
    if settings.DEBUG:
        if scheme not in ('http', 'https'):
            return False
    else:
        if scheme != 'https':
            return False

    platform_domain = (getattr(settings, 'PLATFORM_DOMAIN', '') or '').lower()
    allowed = set()
    if platform_domain and getattr(tenant, 'subdomain', None):
        allowed.add(f"{tenant.subdomain}.{platform_domain}".lower())
    if (
        getattr(tenant, 'custom_domain', '')
        and getattr(tenant, 'custom_domain_verified', False)
    ):
        allowed.add(tenant.custom_domain.lower())

    if settings.DEBUG:
        allowed.update({
            'localhost',
            '127.0.0.1',
            f"{tenant.subdomain}.localhost" if getattr(tenant, 'subdomain', None) else 'localhost',
        })

    return host in allowed


@api_view(["GET"])
@permission_classes([AllowAny])
def plan_list(request):
    """List all active subscription plans."""
    plans = SubscriptionPlan.objects.filter(is_active=True).order_by('sort_order')
    serializer = SubscriptionPlanSerializer(plans, many=True)
    return Response({"results": serializer.data})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def subscription_detail(request):
    """Get current tenant subscription."""
    try:
        sub = TenantSubscription.objects.select_related('plan').get(tenant=request.tenant)
        return Response(TenantSubscriptionSerializer(sub).data)
    except TenantSubscription.DoesNotExist:
        return Response({"detail": "No subscription found."}, status=404)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def create_checkout(request):
    """Create a Stripe Checkout Session for subscription."""
    serializer = CheckoutSessionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    plan = get_object_or_404(SubscriptionPlan, id=data['plan_id'], is_active=True)
    if plan.is_custom_pricing:
        return error_response("Enterprise plans require contacting sales.", status_code=400)

    # Prevent open redirect via Stripe: success_url / cancel_url must belong
    # to this tenant's domain (subdomain or verified custom domain).
    if not _is_tenant_redirect_url_allowed(data['success_url'], request.tenant):
        return error_response("success_url must point to this tenant's domain.", status_code=400)
    if not _is_tenant_redirect_url_allowed(data['cancel_url'], request.tenant):
        return error_response("cancel_url must point to this tenant's domain.", status_code=400)

    from .stripe_service import create_checkout_session
    try:
        url = create_checkout_session(
            tenant=request.tenant,
            plan=plan,
            interval=data['interval'],
            success_url=data['success_url'],
            cancel_url=data['cancel_url'],
        )
        return Response({"checkout_url": url}, status=201)
    except Exception as e:
        logger.exception("Failed to create checkout session")
        return error_response(str(e), status_code=400)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def create_portal(request):
    """Create a Stripe Customer Portal session."""
    from .stripe_service import create_portal_session

    # Default to a safe, server-generated URL on the current tenant host.
    default_return_url = request.build_absolute_uri('/admin/billing')
    return_url = request.data.get('return_url', default_return_url)

    # Prevent open redirect via Stripe Customer Portal.
    if not _is_tenant_redirect_url_allowed(return_url, request.tenant):
        return error_response("return_url must point to this tenant's domain.", status_code=400)

    try:
        url = create_portal_session(request.tenant, return_url)
        return Response({"portal_url": url})
    except Exception as e:
        logger.exception("Failed to create portal session")
        return error_response(str(e), status_code=400)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def payment_history(request):
    """List payment history for the tenant."""
    qs = PaymentHistory.objects.filter(tenant=request.tenant).order_by('-created_at')

    paginator = make_pagination_class(25, 100)()
    page = paginator.paginate_queryset(qs, request)
    if page is not None:
        serializer = PaymentHistorySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    serializer = PaymentHistorySerializer(qs, many=True)
    return Response({"results": serializer.data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def preview_plan_change(request):
    """Preview proration for upgrading/downgrading."""
    serializer = PlanChangePreviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    plan = get_object_or_404(SubscriptionPlan, id=data['plan_id'], is_active=True)

    from .stripe_service import preview_plan_change as stripe_preview
    try:
        result = stripe_preview(request.tenant, plan, data['interval'])
        result['new_plan'] = SubscriptionPlanSerializer(plan).data
        return Response(result)
    except Exception as e:
        logger.exception("Failed to preview plan change")
        return error_response(str(e), status_code=400)
