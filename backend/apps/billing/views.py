import logging

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

    return_url = request.data.get('return_url', request.build_absolute_uri('/admin/billing'))
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
