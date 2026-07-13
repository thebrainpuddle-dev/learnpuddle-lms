from django.urls import path

from . import views

app_name = "ai_classroom"

urlpatterns = [
    path("launch/", views.launch_openmaic, name="launch"),
    path("providers/", views.provider_credentials, name="providers"),
    path(
        "providers/<uuid:credential_id>/", views.provider_credential_detail, name="provider_detail"
    ),
    path("usage/summary/", views.usage_summary, name="usage_summary"),
]

internal_urlpatterns = [
    path("sessions/exchange/", views.internal_exchange_session, name="internal_session_exchange"),
    path(
        "sessions/introspect/",
        views.internal_introspect_session,
        name="internal_session_introspect",
    ),
    path("runtime-context/", views.internal_runtime_context, name="internal_runtime_context"),
    path("classrooms/", views.internal_create_classroom, name="internal_classroom_create"),
    path(
        "classrooms/list/",
        views.internal_list_classrooms,
        name="internal_classroom_list",
    ),
    path(
        "classrooms/<uuid:classroom_id>/metadata/",
        views.internal_classroom_metadata,
        name="internal_classroom_metadata",
    ),
    path("jobs/", views.internal_create_job, name="internal_job_create"),
    path(
        "generations/",
        views.internal_create_generation,
        name="internal_generation_create",
    ),
    path("jobs/<uuid:job_id>/", views.internal_update_job, name="internal_job_update"),
    path(
        "jobs/<uuid:job_id>/runtime-context/",
        views.internal_job_runtime_context,
        name="internal_job_runtime_context",
    ),
    path(
        "classrooms/<uuid:classroom_id>/artifact/",
        views.internal_classroom_artifact,
        name="internal_classroom_artifact",
    ),
    path(
        "classrooms/<uuid:classroom_id>/media/presign/",
        views.internal_media_presign,
        name="internal_media_presign",
    ),
    path(
        "classrooms/<uuid:classroom_id>/media/<uuid:asset_id>/confirm/",
        views.internal_media_confirm,
        name="internal_media_confirm",
    ),
    path(
        "media/<uuid:asset_id>/read/",
        views.internal_media_read,
        name="internal_media_read",
    ),
    path("usage/events/", views.internal_usage_events, name="internal_usage_events"),
]
