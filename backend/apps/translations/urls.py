"""URL routes for TASK-058 — Auto-Translation Service.

Admin routes are mounted at ``/api/v1/admin/translations/``.
The single teacher read endpoint is mounted at
``/api/v1/teacher/content/<uuid:content_id>/translation/``.

TASK-064b additions (per-field review + publish)
-------------------------------------------------
  PUT  content/<uuid>/fields/<field>/approve/?lang=xx
  PUT  content/<uuid>/fields/<field>/reject/?lang=xx
  PUT  content/<uuid>/fields/<field>/edit/?lang=xx
  POST content/<uuid>/publish/?lang=xx
"""

from __future__ import annotations

from django.urls import path

from . import views

# Admin URL patterns — mounted under /admin/translations/
admin_urlpatterns = [
    path(
        "courses/<uuid:course_id>/",
        views.translate_course_view,
        name="translate-course",
    ),
    path(
        "content/<uuid:content_id>/",
        views.translations_content_view,
        name="translate-content",
    ),
    path(
        "jobs/<uuid:job_id>/",
        views.translation_job_detail,
        name="translation-job-detail",
    ),
    # TASK-064b per-field review endpoints.
    path(
        "content/<uuid:content_id>/fields/<str:field>/approve/",
        views.approve_translation_field,
        name="translation-field-approve",
    ),
    path(
        "content/<uuid:content_id>/fields/<str:field>/reject/",
        views.reject_translation_field,
        name="translation-field-reject",
    ),
    path(
        "content/<uuid:content_id>/fields/<str:field>/edit/",
        views.edit_translation_field,
        name="translation-field-edit",
    ),
    path(
        "content/<uuid:content_id>/publish/",
        views.publish_content_translation,
        name="translation-content-publish",
    ),
]

# Teacher URL pattern — mounted under /teacher/
teacher_urlpatterns = [
    path(
        "content/<uuid:content_id>/translation/",
        views.teacher_content_translation,
        name="teacher-content-translation",
    ),
]
