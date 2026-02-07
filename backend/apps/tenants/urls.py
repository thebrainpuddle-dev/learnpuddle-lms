from django.urls import path

from . import views

app_name = "tenants"

urlpatterns = [
    path("theme/", views.tenant_theme_view, name="tenant_theme"),
    path("me/", views.tenant_me_view, name="tenant_me"),
    path("config/", views.tenant_config_view, name="tenant_config"),
    path("stats/", views.tenant_stats_view, name="tenant_stats"),
    path("analytics/", views.tenant_analytics_view, name="tenant_analytics"),
    path("settings/", views.tenant_settings_view, name="tenant_settings"),
]

