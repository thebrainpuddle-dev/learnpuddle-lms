"""URL routes for SCORM 1.2 export (TASK-052).

Mounted under /api/v1/admin/ in config/urls.py so final paths are:
  POST /api/v1/admin/courses/{id}/scorm-export/
  POST /api/v1/admin/contents/{id}/scorm-export/
"""

from django.urls import path

from . import scorm_export_views as v

app_name = "scorm_export"

urlpatterns = [
    path(
        "courses/<uuid:course_id>/scorm-export/",
        v.course_scorm_export,
        name="course_scorm_export",
    ),
    path(
        "contents/<uuid:content_id>/scorm-export/",
        v.content_scorm_export,
        name="content_scorm_export",
    ),
]
