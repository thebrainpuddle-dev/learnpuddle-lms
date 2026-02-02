from django.urls import path

from . import teacher_views

app_name = "teacher_progress"

urlpatterns = [
    path("dashboard/", teacher_views.teacher_dashboard, name="teacher_dashboard"),
    path("progress/content/<uuid:content_id>/start/", teacher_views.progress_start, name="progress_start"),
    path("progress/content/<uuid:content_id>/", teacher_views.progress_update, name="progress_update"),
    path("progress/content/<uuid:content_id>/complete/", teacher_views.progress_complete, name="progress_complete"),
    path("assignments/", teacher_views.assignment_list, name="assignment_list"),
    path("assignments/<uuid:assignment_id>/submit/", teacher_views.assignment_submit, name="assignment_submit"),
    path(
        "assignments/<uuid:assignment_id>/submission/",
        teacher_views.assignment_submission_detail,
        name="assignment_submission_detail",
    ),
]

