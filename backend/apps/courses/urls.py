# apps/courses/urls.py

from django.urls import path
from . import views
from . import video_views

app_name = 'courses'

urlpatterns = [
    # Course CRUD
    path('', views.course_list_create, name='course_list_create'),
    path('<uuid:course_id>/', views.course_detail, name='course_detail'),
    path('<uuid:course_id>/publish/', views.course_publish, name='course_publish'),
    path('<uuid:course_id>/duplicate/', views.course_duplicate, name='course_duplicate'),
    
    # Module CRUD
    path('<uuid:course_id>/modules/', views.module_list_create, name='module_list_create'),
    path('<uuid:course_id>/modules/<uuid:module_id>/', views.module_detail, name='module_detail'),
    
    # Content CRUD
    path('<uuid:course_id>/modules/<uuid:module_id>/contents/', views.content_list_create, name='content_list_create'),
    path('<uuid:course_id>/modules/<uuid:module_id>/contents/<uuid:content_id>/', views.content_detail, name='content_detail'),

    # Video upload + processing (admin)
    path(
        "<uuid:course_id>/modules/<uuid:module_id>/contents/video-upload/",
        video_views.upload_video_content,
        name="upload_video_content",
    ),
    path(
        "<uuid:course_id>/modules/<uuid:module_id>/contents/<uuid:content_id>/video-status/",
        video_views.video_status,
        name="video_status",
    ),
    path(
        "<uuid:course_id>/modules/<uuid:module_id>/contents/<uuid:content_id>/video/regenerate-transcript/",
        video_views.regenerate_transcript,
        name="regenerate_transcript",
    ),
    path(
        "<uuid:course_id>/modules/<uuid:module_id>/contents/<uuid:content_id>/video/regenerate-assignments/",
        video_views.regenerate_assignments,
        name="regenerate_assignments",
    ),
]
