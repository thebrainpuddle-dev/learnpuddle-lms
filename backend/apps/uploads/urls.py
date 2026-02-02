from django.urls import path

from . import views

app_name = "uploads"

urlpatterns = [
    path("tenant-logo/", views.upload_tenant_logo, name="upload_tenant_logo"),
    path("course-thumbnail/", views.upload_course_thumbnail, name="upload_course_thumbnail"),
    path("content-file/", views.upload_content_file, name="upload_content_file"),
]

