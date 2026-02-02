from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("course-progress/", views.course_progress_report, name="course_progress"),
    path("assignment-status/", views.assignment_status_report, name="assignment_status"),
    path("courses/", views.list_courses_for_reports, name="reports_courses"),
    path("assignments/", views.list_assignments_for_reports, name="reports_assignments"),
]

