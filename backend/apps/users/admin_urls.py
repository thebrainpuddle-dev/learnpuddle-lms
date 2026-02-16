from django.urls import path

from . import admin_views

app_name = "admin_users"

urlpatterns = [
    path("teachers/", admin_views.teachers_list_view, name="teachers_list"),
    path("teachers/deleted/", admin_views.deleted_teachers_list_view, name="deleted_teachers_list"),
    path("teachers/bulk-import/", admin_views.teachers_bulk_import_view, name="teachers_bulk_import"),
    path("teachers/bulk-action/", admin_views.teachers_bulk_action, name="teachers_bulk_action"),
    path("teachers/<uuid:teacher_id>/", admin_views.teacher_detail_view, name="teacher_detail"),
    path("teachers/<uuid:teacher_id>/restore/", admin_views.restore_teacher_view, name="restore_teacher"),
]

