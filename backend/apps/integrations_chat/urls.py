"""
URL configuration for the integrations_chat app.

Mounted at: /api/v1/admin/chat-integrations/
"""

from django.urls import path

from . import views

urlpatterns = [
    # Integration collection
    path(
        "",
        views.chat_integration_list_create,
        name="chat-integration-list",
    ),
    # Integration item
    path(
        "<uuid:pk>/",
        views.chat_integration_detail,
        name="chat-integration-detail",
    ),
    # Test endpoint
    path(
        "<uuid:pk>/test/",
        views.chat_integration_test,
        name="chat-integration-test",
    ),
    # Routing rules
    path(
        "<uuid:pk>/rules/",
        views.chat_routing_rule_list_create,
        name="chat-routing-rule-list",
    ),
    path(
        "<uuid:pk>/rules/<uuid:rule_pk>/",
        views.chat_routing_rule_detail,
        name="chat-routing-rule-detail",
    ),
    # Delivery history
    path(
        "<uuid:pk>/deliveries/",
        views.chat_delivery_list,
        name="chat-delivery-list",
    ),
]
