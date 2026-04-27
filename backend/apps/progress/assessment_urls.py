# apps/progress/assessment_urls.py

from django.urls import path

from . import assessment_views

app_name = "assessment"

urlpatterns = [
    # ------------------------------------------------------------------
    # Admin: Question Banks + Questions
    # ------------------------------------------------------------------
    path(
        "admin/question-banks/",
        assessment_views.question_bank_list_create,
        name="question_bank_list_create",
    ),
    path(
        "admin/question-banks/<uuid:bank_id>/",
        assessment_views.question_bank_detail,
        name="question_bank_detail",
    ),
    path(
        "admin/question-banks/<uuid:bank_id>/questions/",
        assessment_views.question_bank_questions,
        name="question_bank_questions",
    ),
    path(
        "admin/questions/<uuid:question_id>/",
        assessment_views.question_detail,
        name="question_detail",
    ),

    # ------------------------------------------------------------------
    # Admin: Quiz Config per Content
    # ------------------------------------------------------------------
    path(
        "admin/contents/<uuid:content_id>/quiz-config/",
        assessment_views.quiz_config_for_content,
        name="quiz_config_for_content",
    ),

    # ------------------------------------------------------------------
    # Teacher: Attempts
    # ------------------------------------------------------------------
    path(
        "teacher/quizzes/<uuid:content_id>/start/",
        assessment_views.quiz_attempt_start,
        name="quiz_attempt_start",
    ),
    path(
        "teacher/quiz-attempts/<uuid:attempt_id>/submit/",
        assessment_views.quiz_attempt_submit,
        name="quiz_attempt_submit",
    ),
    path(
        "teacher/quiz-attempts/",
        assessment_views.my_quiz_attempts,
        name="my_quiz_attempts",
    ),

    # ------------------------------------------------------------------
    # Admin: Gradebook
    # ------------------------------------------------------------------
    path(
        "admin/gradebook/courses/<uuid:course_id>/",
        assessment_views.course_gradebook,
        name="course_gradebook",
    ),
]
