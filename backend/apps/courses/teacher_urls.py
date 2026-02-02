from django.urls import path

from . import teacher_views

app_name = "teacher_courses"

urlpatterns = [
    path("courses/", teacher_views.teacher_course_list, name="teacher_course_list"),
    path("courses/<uuid:course_id>/", teacher_views.teacher_course_detail, name="teacher_course_detail"),
]

