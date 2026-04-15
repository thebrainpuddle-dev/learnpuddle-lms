# apps/discussions/urls.py
from django.urls import path
from . import views

app_name = 'discussions'

# Student discussion endpoints — mounted under /api/v1/student/discussions/
student_urlpatterns = [
    path('threads/', views.student_thread_list, name='student_thread_list'),
    path('threads/create/', views.student_thread_create, name='student_thread_create'),
    path('threads/<uuid:thread_id>/', views.student_thread_detail, name='student_thread_detail'),
    path('threads/<uuid:thread_id>/replies/', views.student_reply_create, name='student_reply_create'),
    path('threads/<uuid:thread_id>/replies/<uuid:reply_id>/', views.student_reply_detail, name='student_reply_detail'),
    path('threads/<uuid:thread_id>/replies/<uuid:reply_id>/like/', views.student_reply_like, name='student_reply_like'),
    path('threads/<uuid:thread_id>/subscribe/', views.student_thread_subscribe, name='student_thread_subscribe'),
]

# Teacher discussion endpoints — mounted under /api/v1/teacher/discussions/
teacher_urlpatterns = [
    path('threads/', views.teacher_thread_list, name='teacher_thread_list'),
    path('threads/<uuid:thread_id>/', views.teacher_thread_detail, name='teacher_thread_detail'),
    path('threads/<uuid:thread_id>/replies/', views.teacher_reply_create, name='teacher_reply_create'),
    path('threads/<uuid:thread_id>/moderate/', views.teacher_thread_moderate, name='teacher_thread_moderate'),
    path('threads/<uuid:thread_id>/replies/<uuid:reply_id>/moderate/', views.teacher_reply_moderate, name='teacher_reply_moderate'),
    path('threads/<uuid:thread_id>/replies/<uuid:reply_id>/like/', views.teacher_reply_like, name='teacher_reply_like'),
    path('threads/<uuid:thread_id>/subscribe/', views.teacher_thread_subscribe, name='teacher_thread_subscribe'),
    path('sections/', views.teacher_sections_list, name='teacher_sections_list'),
]

# Legacy flat pattern (kept for backward compat — will be removed)
urlpatterns = []
