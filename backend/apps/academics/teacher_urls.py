# apps/academics/teacher_urls.py
from django.urls import path
from . import teacher_views
from .attendance_urls import teacher_urlpatterns as attendance_patterns

app_name = "teacher_academics"

urlpatterns = [
    path("my-classes/", teacher_views.my_classes, name="my_classes"),
    path("sections/<uuid:section_id>/dashboard/", teacher_views.section_dashboard, name="section_dashboard"),
] + attendance_patterns
