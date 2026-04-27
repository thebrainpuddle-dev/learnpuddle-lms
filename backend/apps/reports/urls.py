from django.urls import path

from . import views
from . import manager_views
from . import engagement_views
from . import analytics_views

app_name = "reports"

urlpatterns = [
    # Analytics chart endpoints (FE-034)
    path("analytics/deadline-adherence/", analytics_views.deadline_adherence, name="analytics_deadline_adherence"),
    path("analytics/approval-trends/", analytics_views.approval_trends, name="analytics_approval_trends"),
    path("analytics/course-effectiveness/", analytics_views.course_effectiveness, name="analytics_course_effectiveness"),

    path("engagement/heatmap/", engagement_views.engagement_heatmap, name="engagement_heatmap"),
    path("course-progress/", views.course_progress_report, name="course_progress"),
    path("course-progress/export/", views.course_progress_export, name="course_progress_export"),
    path("assignment-status/", views.assignment_status_report, name="assignment_status"),
    path("assignment-status/export/", views.assignment_status_export, name="assignment_status_export"),
    path("courses/", views.list_courses_for_reports, name="reports_courses"),
    path("assignments/", views.list_assignments_for_reports, name="reports_assignments"),

    # Manager Dashboard
    path("manager/team-progress/", manager_views.manager_team_progress, name="manager_team_progress"),
    path("manager/overdue/", manager_views.manager_overdue, name="manager_overdue"),
    path("manager/compliance/", manager_views.manager_compliance, name="manager_compliance"),
    path("manager/skills-overview/", manager_views.manager_skills_overview, name="manager_skills_overview"),
]

