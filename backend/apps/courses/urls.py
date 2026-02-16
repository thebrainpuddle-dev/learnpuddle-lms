# apps/courses/urls.py

from django.urls import path
from . import views
from . import video_views
from . import learning_path_views

app_name = 'courses'

urlpatterns = [
    # Global search
    path('search/', views.global_search, name='global_search'),
    
    # Course CRUD
    path('', views.course_list_create, name='course_list_create'),
    path('bulk-action/', views.courses_bulk_action, name='courses_bulk_action'),
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
    
    # Learning Paths - Admin
    path('learning-paths/', learning_path_views.learning_path_list_create, name='learning_path_list_create'),
    path('learning-paths/<uuid:path_id>/', learning_path_views.learning_path_detail, name='learning_path_detail'),
    path('learning-paths/<uuid:path_id>/courses/', learning_path_views.learning_path_add_course, name='learning_path_add_course'),
    path('learning-paths/<uuid:path_id>/courses/<uuid:path_course_id>/', learning_path_views.learning_path_course_detail, name='learning_path_course_detail'),
    path('learning-paths/<uuid:path_id>/reorder/', learning_path_views.learning_path_reorder, name='learning_path_reorder'),
    
    # Learning Paths - Teacher
    path('my-learning-paths/', learning_path_views.teacher_learning_paths, name='teacher_learning_paths'),
    path('my-learning-paths/<uuid:path_id>/', learning_path_views.teacher_learning_path_detail, name='teacher_learning_path_detail'),
    path('my-learning-paths/<uuid:path_id>/start/', learning_path_views.teacher_start_learning_path, name='teacher_start_learning_path'),
]
