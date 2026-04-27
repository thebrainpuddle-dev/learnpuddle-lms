"""URL patterns for Course Templates library (TASK-049).

Mounted twice from config/urls.py:
    * ``/api/v1/super-admin/course-templates/...``  (platform CRUD)
    * ``/api/v1/admin/course-templates/...``        (tenant list / preview / clone)
"""

from django.urls import path

from . import template_views


super_admin_urlpatterns = [
    path(
        "course-templates/",
        template_views.super_admin_template_list_create,
        name="super_admin_course_template_list_create",
    ),
    path(
        "course-templates/<uuid:template_id>/",
        template_views.super_admin_template_detail,
        name="super_admin_course_template_detail",
    ),
]


tenant_admin_urlpatterns = [
    path(
        "course-templates/",
        template_views.tenant_admin_template_list,
        name="tenant_admin_course_template_list",
    ),
    path(
        "course-templates/<uuid:template_id>/",
        template_views.tenant_admin_template_detail,
        name="tenant_admin_course_template_detail",
    ),
    path(
        "course-templates/<uuid:template_id>/clone/",
        template_views.tenant_admin_template_clone,
        name="tenant_admin_course_template_clone",
    ),
]
