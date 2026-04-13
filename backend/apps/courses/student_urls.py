from django.urls import path, include

from . import student_views
from .maic_urls import student_urlpatterns as maic_student_urls
from .chatbot_urls import student_urlpatterns as chatbot_student_urls

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
]
