from django.urls import path

from . import views


urlpatterns = [
    path("overview/", views.ops_overview, name="ops_overview"),
    path("tenants/", views.ops_tenants, name="ops_tenants"),
    path("tenants/<uuid:tenant_id>/timeline/", views.ops_tenant_timeline, name="ops_tenant_timeline"),
    path("incidents/", views.ops_incidents, name="ops_incidents"),
    path("incidents/<uuid:incident_id>/acknowledge/", views.ops_incident_acknowledge, name="ops_incident_acknowledge"),
    path("incidents/<uuid:incident_id>/resolve/", views.ops_incident_resolve, name="ops_incident_resolve"),
    path("replay-cases/", views.ops_replay_cases, name="ops_replay_cases"),
    path("replay-runs/", views.ops_replay_runs_create, name="ops_replay_runs_create"),
    path("replay-runs/<uuid:run_id>/", views.ops_replay_run_detail, name="ops_replay_run_detail"),
    path("replay-runs/<uuid:run_id>/steps/", views.ops_replay_run_steps, name="ops_replay_run_steps"),
    path("replay-runs/<uuid:run_id>/cancel/", views.ops_replay_run_cancel, name="ops_replay_run_cancel"),
    path("errors/", views.ops_errors, name="ops_errors"),
    path("errors/<uuid:error_group_id>/", views.ops_error_detail, name="ops_error_detail"),
    path("errors/<uuid:error_group_id>/lock/", views.ops_error_lock, name="ops_error_lock"),
    path("actions/catalog/", views.ops_actions_catalog, name="ops_actions_catalog"),
    path("actions/execute/", views.ops_actions_execute, name="ops_actions_execute"),
    path("actions/<uuid:action_id>/approve/", views.ops_action_approve, name="ops_action_approve"),
    path("proxy-errors/ingest/", views.ops_proxy_errors_ingest, name="ops_proxy_errors_ingest"),
    path("harness-events/ingest/", views.ops_harness_ingest, name="ops_harness_ingest"),
    path("reports/weekly.csv", views.ops_weekly_report_csv, name="ops_weekly_report_csv"),
    path("tenants/<uuid:tenant_id>/maintenance/", views.ops_tenant_maintenance, name="ops_tenant_maintenance"),
    path(
        "maintenance/schedule/monthly-weekend/",
        views.ops_maintenance_schedule_monthly_weekend,
        name="ops_maintenance_schedule_monthly_weekend",
    ),
    path("bulk-action/", views.ops_bulk_action, name="ops_bulk_action"),
    path("client-errors/ingest/", views.ops_client_error_ingest, name="ops_client_error_ingest"),
]
