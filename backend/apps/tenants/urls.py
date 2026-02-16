from django.urls import path

from . import views, domain_views, gdpr_views

app_name = "tenants"

urlpatterns = [
    path("theme/", views.tenant_theme_view, name="tenant_theme"),
    path("me/", views.tenant_me_view, name="tenant_me"),
    path("config/", views.tenant_config_view, name="tenant_config"),
    path("stats/", views.tenant_stats_view, name="tenant_stats"),
    path("analytics/", views.tenant_analytics_view, name="tenant_analytics"),
    path("settings/", views.tenant_settings_view, name="tenant_settings"),
    
    # Custom domain management
    path("domain/", domain_views.domain_status, name="domain_status"),
    path("domain/configure/", domain_views.domain_configure, name="domain_configure"),
    path("domain/verify/", domain_views.domain_verify, name="domain_verify"),
    path("domain/remove/", domain_views.domain_remove, name="domain_remove"),
    
    # GDPR / Data export
    path("export/", gdpr_views.tenant_data_export, name="tenant_data_export"),
    path("export/user/", gdpr_views.user_data_export, name="user_data_export"),
    path("gdpr/delete-user/", gdpr_views.user_data_delete, name="user_data_delete"),
    path("gdpr/request-deletion/", gdpr_views.request_account_deletion, name="request_account_deletion"),
]

