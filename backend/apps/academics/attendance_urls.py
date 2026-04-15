# apps/academics/attendance_urls.py
from django.urls import path
from . import attendance_views

app_name = "attendance"

# Admin endpoints — included under /api/v1/admin/attendance/
admin_urlpatterns = [
    path("import/", attendance_views.attendance_import, name="import"),
    path("overview/", attendance_views.attendance_overview, name="overview"),
    path("export/", attendance_views.attendance_export_admin, name="export"),
]

# Teacher endpoint — included under /api/v1/teacher/academics/
teacher_urlpatterns = [
    path(
        "sections/<uuid:section_id>/attendance/",
        attendance_views.section_attendance,
        name="section_attendance",
    ),
    path(
        "sections/<uuid:section_id>/attendance/export/",
        attendance_views.attendance_export_section,
        name="section_attendance_export",
    ),
]

# Student endpoint — included under /api/v1/student/
student_urlpatterns = [
    path("attendance/", attendance_views.student_my_attendance, name="my_attendance"),
    path("attendance/export/", attendance_views.attendance_export_student, name="my_attendance_export"),
]
