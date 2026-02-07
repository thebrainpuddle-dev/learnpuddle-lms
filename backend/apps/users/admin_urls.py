from django.urls import path

from . import admin_views

app_name = "admin_users"

urlpatterns = [
    path("teachers/", admin_views.teachers_list_view, name="teachers_list"),
    path("teachers/<uuid:teacher_id>/", admin_views.teacher_detail_view, name="teacher_detail"),
    path("teachers/bulk-import/", admin_views.teachers_bulk_import_view, name="teachers_bulk_import"),
]

