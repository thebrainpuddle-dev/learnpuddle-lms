"""
Admin views for the integrations_chat app.

All views require @admin_only + @tenant_required.
"""

from __future__ import annotations

import logging
import time

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle


class _ChatIntegrationTestThrottle(ScopedRateThrottle):
    """Concrete ScopedRateThrottle for the chat /test/ endpoint.

    DRF's ScopedRateThrottle reads ``request.throttle_scope`` from the
    *view* object. With @api_view FBVs there is no view class attribute, so
    we use a dedicated subclass whose ``scope`` attribute is fixed. This is
    the idiomatic DRF pattern for function-based views that need a named
    throttle scope.
    """
    scope = "chat_integration_test"

from utils.audit import log_audit
from utils.decorators import admin_only, tenant_required

from .models import ChatDelivery, ChatIntegration, ChatRoutingRule
from .serializers import (
    ChatDeliverySerializer,
    ChatIntegrationSerializer,
    ChatRoutingRuleSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper: get integration scoped to tenant
# ---------------------------------------------------------------------------


def _get_integration(integration_id: str, tenant) -> ChatIntegration | None:
    try:
        return ChatIntegration.objects.all_tenants().get(id=integration_id, tenant=tenant)
    except ChatIntegration.DoesNotExist:
        return None


# ---------------------------------------------------------------------------
# Integrations list + create
# ---------------------------------------------------------------------------


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def chat_integration_list_create(request):
    """
    GET  /api/v1/admin/chat-integrations/  — list all for current tenant
    POST /api/v1/admin/chat-integrations/  — create new integration
    """
    tenant = request.tenant

    if request.method == "GET":
        qs = ChatIntegration.objects.all_tenants().filter(tenant=tenant).order_by("-created_at")
        return Response(ChatIntegrationSerializer(qs, many=True).data)

    # POST
    serializer = ChatIntegrationSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    integration = serializer.save(tenant=tenant, created_by=request.user)

    log_audit(
        request=request,
        action="CHAT_INTEGRATION_CREATED",
        target_type="ChatIntegration",
        target_id=str(integration.pk),
        target_repr=str(integration),
        changes={"provider": integration.provider, "display_name": integration.display_name},
    )

    return Response(ChatIntegrationSerializer(integration).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Integration detail: retrieve, update, soft-delete
# ---------------------------------------------------------------------------


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def chat_integration_detail(request, pk: str):
    """
    GET    /api/v1/admin/chat-integrations/{pk}/  — retrieve
    PATCH  /api/v1/admin/chat-integrations/{pk}/  — update
    DELETE /api/v1/admin/chat-integrations/{pk}/  — soft-delete (is_active=False)
    """
    tenant = request.tenant
    integration = _get_integration(pk, tenant)
    if integration is None:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(ChatIntegrationSerializer(integration).data)

    if request.method == "PATCH":
        serializer = ChatIntegrationSerializer(integration, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        integration = serializer.save()
        return Response(ChatIntegrationSerializer(integration).data)

    # DELETE — soft-delete
    integration.is_active = False
    integration.save(update_fields=["is_active"])
    log_audit(
        request=request,
        action="CHAT_INTEGRATION_DELETED",
        target_type="ChatIntegration",
        target_id=str(integration.pk),
        target_repr=str(integration),
        changes={"is_active": False},
    )
    return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Test endpoint
# ---------------------------------------------------------------------------


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([_ChatIntegrationTestThrottle])
@admin_only
@tenant_required
def chat_integration_test(request, pk: str):
    """
    POST /api/v1/admin/chat-integrations/{pk}/test/

    Fires a canned "Hello from LearnPuddle" message to the integration.
    Rate-limited to 5/hour per user via DRF ScopedRateThrottle
    (scope: "chat_integration_test", configured in settings.DEFAULT_THROTTLE_RATES).
    """
    tenant = request.tenant
    integration = _get_integration(pk, tenant)
    if integration is None:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    from apps.integrations_common.crypto import decrypt_secret
    from .ssrf_guard import safe_post, SSRFError
    from .builders.slack import build_slack_message
    from .builders.teams import build_teams_message

    webhook_url = decrypt_secret(integration.webhook_url_encrypted)
    if not webhook_url:
        return Response({"error": "Webhook URL could not be decrypted."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    payload = {
        "title": "Hello from LearnPuddle!",
        "message": (
            f"This is a test message from the {integration.get_provider_display()} integration "
            f"configured as '{integration.display_name}'."
        ),
        "school_name": tenant.name,
    }

    if integration.provider == ChatIntegration.PROVIDER_SLACK:
        body = build_slack_message("SYSTEM", payload)
    else:
        body = build_teams_message("SYSTEM", payload)

    start = time.monotonic()
    try:
        resp = safe_post(webhook_url, json=body)
        latency_ms = int((time.monotonic() - start) * 1000)
        resp.raise_for_status()
    except SSRFError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        return Response(
            {"error": str(exc), "latency_ms": latency_ms},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response(
        {
            "status_code": resp.status_code,
            "latency_ms": latency_ms,
            "ok": True,
        }
    )


# ---------------------------------------------------------------------------
# Routing rules CRUD
# ---------------------------------------------------------------------------


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def chat_routing_rule_list_create(request, pk: str):
    """
    GET  /api/v1/admin/chat-integrations/{pk}/rules/
    POST /api/v1/admin/chat-integrations/{pk}/rules/
    """
    tenant = request.tenant
    integration = _get_integration(pk, tenant)
    if integration is None:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        rules = ChatRoutingRule.objects.filter(integration=integration)
        return Response(ChatRoutingRuleSerializer(rules, many=True).data)

    data = dict(request.data)
    data["integration"] = str(integration.pk)
    serializer = ChatRoutingRuleSerializer(data=data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    rule = serializer.save()
    return Response(ChatRoutingRuleSerializer(rule).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def chat_routing_rule_detail(request, pk: str, rule_pk: str):
    """
    GET    /api/v1/admin/chat-integrations/{pk}/rules/{rule_pk}/
    PATCH  /api/v1/admin/chat-integrations/{pk}/rules/{rule_pk}/
    DELETE /api/v1/admin/chat-integrations/{pk}/rules/{rule_pk}/
    """
    tenant = request.tenant
    integration = _get_integration(pk, tenant)
    if integration is None:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    try:
        rule = ChatRoutingRule.objects.get(id=rule_pk, integration=integration)
    except ChatRoutingRule.DoesNotExist:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(ChatRoutingRuleSerializer(rule).data)

    if request.method == "PATCH":
        serializer = ChatRoutingRuleSerializer(rule, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        rule = serializer.save()
        return Response(ChatRoutingRuleSerializer(rule).data)

    # DELETE
    rule.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Delivery history
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def chat_delivery_list(request, pk: str):
    """
    GET /api/v1/admin/chat-integrations/{pk}/deliveries/

    Query params:
      - status: pending|sent|failed|dlq
      - limit:  number (default 50, max 200)
    """
    tenant = request.tenant
    integration = _get_integration(pk, tenant)
    if integration is None:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    qs = ChatDelivery.objects.filter(integration=integration).order_by("-created_at")

    status_filter = request.GET.get("status", "").lower()
    valid_statuses = {s[0] for s in ChatDelivery.STATUS_CHOICES}
    if status_filter in valid_statuses:
        qs = qs.filter(status=status_filter)

    try:
        limit = min(200, max(1, int(request.GET.get("limit", 50))))
    except (ValueError, TypeError):
        limit = 50

    qs = qs[:limit]
    return Response(ChatDeliverySerializer(qs, many=True).data)
