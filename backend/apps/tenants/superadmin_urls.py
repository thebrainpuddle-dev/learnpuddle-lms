from django.urls import include, path
from . import superadmin_views

app_name = "superadmin"

urlpatterns = [
    path("stats/", superadmin_views.platform_stats, name="platform_stats"),
    path("ops/", include("apps.ops.urls")),
    path("tenants/", superadmin_views.tenant_list_create, name="tenant_list_create"),
    path("tenants/<uuid:tenant_id>/", superadmin_views.tenant_detail, name="tenant_detail"),
    path("tenants/<uuid:tenant_id>/impersonate/", superadmin_views.tenant_impersonate, name="tenant_impersonate"),
    path("tenants/<uuid:tenant_id>/usage/", superadmin_views.tenant_usage, name="tenant_usage"),
    path("tenants/<uuid:tenant_id>/apply-plan/", superadmin_views.tenant_apply_plan, name="tenant_apply_plan"),
    path("tenants/<uuid:tenant_id>/reset-admin-password/", superadmin_views.tenant_reset_admin_password, name="tenant_reset_admin_password"),
    path("tenants/<uuid:tenant_id>/send-email/", superadmin_views.tenant_send_email, name="tenant_send_email"),

    # Bulk email
    path("bulk-email/", superadmin_views.bulk_send_email, name="bulk_send_email"),

    # Demo bookings
    path("demo-bookings/", superadmin_views.demo_booking_list_create, name="demo_booking_list_create"),
    path("demo-bookings/<uuid:booking_id>/", superadmin_views.demo_booking_detail, name="demo_booking_detail"),
    path("demo-bookings/<uuid:booking_id>/send-email/", superadmin_views.demo_booking_send_email, name="demo_booking_send_email"),
]
