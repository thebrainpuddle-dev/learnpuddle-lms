from django.urls import path

from . import teacher_views

app_name = "teacher_courses"

urlpatterns = [
    path("courses/", teacher_views.teacher_course_list, name="teacher_course_list"),
    path("courses/<uuid:course_id>/", teacher_views.teacher_course_detail, name="teacher_course_detail"),
    path("courses/<uuid:course_id>/certificate/", teacher_views.course_certificate, name="course_certificate"),
    path("videos/<uuid:content_id>/transcript/", teacher_views.teacher_video_transcript, name="teacher_video_transcript"),
]

