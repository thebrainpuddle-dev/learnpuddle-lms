"""URL routes for SCORM 1.2 import + runtime."""

from django.urls import path

from . import scorm_views

app_name = "scorm"

urlpatterns = [
    # Admin upload
    path("admin/scorm/upload/", scorm_views.scorm_upload, name="scorm_upload"),
    # SCORM 1.2 runtime commit (called by SCORM player from iframe)
    path("scorm/commit/", scorm_views.scorm_commit, name="scorm_commit"),
]
