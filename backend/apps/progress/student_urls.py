from django.urls import path

from . import student_views

app_name = "student_progress"

urlpatterns = [
    path("dashboard/", student_views.student_dashboard, name="student_dashboard"),
    path("gamification/summary/", student_views.student_gamification_summary, name="student_gamification_summary"),
    path("progress/content/<uuid:content_id>/start/", student_views.student_progress_start, name="student_progress_start"),
    path("progress/content/<uuid:content_id>/", student_views.student_progress_update, name="student_progress_update"),
    path("progress/content/<uuid:content_id>/complete/", student_views.student_progress_complete, name="student_progress_complete"),
    path("assignments/", student_views.student_assignment_list, name="student_assignment_list"),
    path("assignments/<uuid:assignment_id>/submit/", student_views.student_assignment_submit, name="student_assignment_submit"),
    path(
        "assignments/<uuid:assignment_id>/submission/",
        student_views.student_assignment_submission_detail,
        name="student_assignment_submission_detail",
    ),
    path("quizzes/<uuid:assignment_id>/", student_views.student_quiz_detail, name="student_quiz_detail"),
    path("quizzes/<uuid:assignment_id>/submit/", student_views.student_quiz_submit, name="student_quiz_submit"),
    path("search/", student_views.student_search, name="student_search"),
]
