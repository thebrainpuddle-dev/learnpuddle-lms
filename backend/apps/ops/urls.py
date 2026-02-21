from django.urls import path

from . import views


urlpatterns = [
    path("overview/", views.ops_overview, name="ops_overview"),
    path("tenants/", views.ops_tenants, name="ops_tenants"),
    path("tenants/<uuid:tenant_id>/timeline/", views.ops_tenant_timeline, name="ops_tenant_timeline"),
    path("incidents/", views.ops_incidents, name="ops_incidents"),
    path("incidents/<uuid:incident_id>/acknowledge/", views.ops_incident_acknowledge, name="ops_incident_acknowledge"),
    path("incidents/<uuid:incident_id>/resolve/", views.ops_incident_resolve, name="ops_incident_resolve"),
    path("harness-events/ingest/", views.ops_harness_ingest, name="ops_harness_ingest"),
    path("reports/weekly.csv", views.ops_weekly_report_csv, name="ops_weekly_report_csv"),
    path("tenants/<uuid:tenant_id>/maintenance/", views.ops_tenant_maintenance, name="ops_tenant_maintenance"),
    path(
        "maintenance/schedule/monthly-weekend/",
        views.ops_maintenance_schedule_monthly_weekend,
        name="ops_maintenance_schedule_monthly_weekend",
    ),
    path("bulk-action/", views.ops_bulk_action, name="ops_bulk_action"),
]
