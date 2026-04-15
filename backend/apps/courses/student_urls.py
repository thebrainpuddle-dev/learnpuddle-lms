from django.urls import path, include

from . import student_views
from .maic_urls import student_urlpatterns as maic_student_urls
from .chatbot_urls import student_urlpatterns as chatbot_student_urls
from .study_summary_views import (
    student_study_summary_generate,
    student_study_summary_list,
    student_study_summary_detail,
    student_study_summary_delete,
)
from apps.discussions.urls import student_urlpatterns as discussion_student_urls

app_name = "student_courses"

urlpatterns = [
    # Core course views
    path("courses/", student_views.student_course_list, name="student_course_list"),
    path("courses/<uuid:course_id>/", student_views.student_course_detail, name="student_course_detail"),
    path("videos/<uuid:content_id>/transcript/", student_views.student_video_transcript, name="student_video_transcript"),

    # OpenMAIC AI Classroom
    path("maic/", include((maic_student_urls, "maic"))),

    # AI Chatbot
    path("chatbots/", include((chatbot_student_urls, "chatbots"))),

    # Discussions
    path("discussions/", include((discussion_student_urls, "discussions"))),

    # AI Study Summaries
    path("study-summaries/generate/", student_study_summary_generate, name="student_study_summary_generate"),
    path("study-summaries/", student_study_summary_list, name="student_study_summary_list"),
    path("study-summaries/<uuid:summary_id>/", student_study_summary_detail, name="student_study_summary_detail"),
    path("study-summaries/<uuid:summary_id>/delete/", student_study_summary_delete, name="student_study_summary_delete"),
]
