"""
apps/reports_builder/urls.py
-----------------------------
URL routing for the Custom Report Builder (TASK-053).

Mounted under: /api/v1/admin/reports/
"""

from django.urls import path

from . import views

urlpatterns = [
    # Data-source schema (field / op / aggregate whitelists)
    path(
        "schema/",
        views.data_source_schema,
        name="report-data-source-schema",
    ),
    # ReportDefinition CRUD
    path(
        "definitions/",
        views.definition_list_create,
        name="report-definition-list",
    ),
    path(
        "definitions/<uuid:definition_id>/",
        views.definition_detail,
        name="report-definition-detail",
    ),
    # Run (sync JSON) + Export (async CSV)
    path(
        "definitions/<uuid:definition_id>/run/",
        views.definition_run,
        name="report-definition-run",
    ),
    path(
        "definitions/<uuid:definition_id>/export/",
        views.definition_export,
        name="report-definition-export",
    ),
    # Schedule CRUD
    path(
        "definitions/<uuid:definition_id>/schedules/",
        views.schedule_list_create,
        name="report-schedule-list",
    ),
    path(
        "definitions/<uuid:definition_id>/schedules/<uuid:schedule_id>/",
        views.schedule_detail,
        name="report-schedule-detail",
    ),
    # Run history + download
    path(
        "runs/",
        views.run_list,
        name="report-run-list",
    ),
    path(
        "runs/<uuid:run_id>/download/",
        views.run_download,
        name="report-run-download",
    ),
    path(
        "runs/<uuid:run_id>/artifact/",
        views.run_artifact,
        name="report-run-artifact",
    ),
]
