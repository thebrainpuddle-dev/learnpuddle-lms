"""URL patterns for content versioning (TASK-048).

Mounted under `/api/v1/admin/` in config/urls.py so final paths are:
    /api/v1/admin/courses/{id}/revisions/
    /api/v1/admin/courses/{id}/revisions/{rev}/
    /api/v1/admin/courses/{id}/revisions/{rev}/restore/
    /api/v1/admin/modules/{id}/revisions/...
    /api/v1/admin/contents/{id}/revisions/...
"""

from django.urls import path

from . import versioning_views as v

app_name = "courses_versioning"

urlpatterns = [
    # Course revisions
    path(
        "courses/<uuid:course_id>/revisions/",
        v.course_revisions_list,
        name="course_revisions_list",
    ),
    path(
        "courses/<uuid:course_id>/revisions/<int:revision_number>/",
        v.course_revision_detail,
        name="course_revision_detail",
    ),
    path(
        "courses/<uuid:course_id>/revisions/<int:revision_number>/restore/",
        v.course_revision_restore,
        name="course_revision_restore",
    ),

    # Module revisions
    path(
        "modules/<uuid:module_id>/revisions/",
        v.module_revisions_list,
        name="module_revisions_list",
    ),
    path(
        "modules/<uuid:module_id>/revisions/<int:revision_number>/",
        v.module_revision_detail,
        name="module_revision_detail",
    ),
    path(
        "modules/<uuid:module_id>/revisions/<int:revision_number>/restore/",
        v.module_revision_restore,
        name="module_revision_restore",
    ),

    # Content revisions
    path(
        "contents/<uuid:content_id>/revisions/",
        v.content_revisions_list,
        name="content_revisions_list",
    ),
    path(
        "contents/<uuid:content_id>/revisions/<int:revision_number>/",
        v.content_revision_detail,
        name="content_revision_detail",
    ),
    path(
        "contents/<uuid:content_id>/revisions/<int:revision_number>/restore/",
        v.content_revision_restore,
        name="content_revision_restore",
    ),
]
