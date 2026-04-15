# apps/academics/attendance_student_urls.py
from django.urls import path
from . import attendance_views

urlpatterns = [
    path("attendance/", attendance_views.student_my_attendance, name="my_attendance"),
    path("attendance/export/", attendance_views.attendance_export_student, name="my_attendance_export"),
]
