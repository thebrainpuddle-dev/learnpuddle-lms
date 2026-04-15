from django.urls import path, include

from . import teacher_views
from .maic_urls import teacher_urlpatterns as maic_teacher_urls
from .chatbot_urls import teacher_urlpatterns as chatbot_teacher_urls
from .teacher_study_views import (
    teacher_study_summary_generate,
    teacher_study_summary_list,
    teacher_study_summary_detail,
    teacher_study_summary_delete,
    teacher_study_summary_toggle_share,
)
from apps.discussions.urls import teacher_urlpatterns as discussion_teacher_urls

app_name = "teacher_courses"

urlpatterns = [
    path("courses/", teacher_views.teacher_course_list, name="teacher_course_list"),
    path("courses/<uuid:course_id>/", teacher_views.teacher_course_detail, name="teacher_course_detail"),
    path("courses/<uuid:course_id>/certificate/", teacher_views.course_certificate, name="course_certificate"),
    path("videos/<uuid:content_id>/transcript/", teacher_views.teacher_video_transcript, name="teacher_video_transcript"),

    # OpenMAIC AI Classroom
    path("maic/", include((maic_teacher_urls, "maic"))),

    # AI Chatbot Builder
    path("chatbots/", include((chatbot_teacher_urls, "chatbots"))),

    # Discussions (student threads in assigned sections)
    path("discussions/", include((discussion_teacher_urls, "discussions"))),

    # AI Study Summaries (teacher)
    path("study-summaries/generate/", teacher_study_summary_generate, name="teacher_study_summary_generate"),
    path("study-summaries/", teacher_study_summary_list, name="teacher_study_summary_list"),
    path("study-summaries/<uuid:summary_id>/", teacher_study_summary_detail, name="teacher_study_summary_detail"),
    path("study-summaries/<uuid:summary_id>/delete/", teacher_study_summary_delete, name="teacher_study_summary_delete"),
    path("study-summaries/<uuid:summary_id>/share/", teacher_study_summary_toggle_share, name="teacher_study_summary_toggle_share"),
]
