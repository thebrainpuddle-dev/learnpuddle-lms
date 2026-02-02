from django.urls import path

from . import admin_views

app_name = "admin_users"

urlpatterns = [
    path("teachers/", admin_views.teachers_list_view, name="teachers_list"),
]

