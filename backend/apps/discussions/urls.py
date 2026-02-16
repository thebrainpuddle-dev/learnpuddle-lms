# apps/discussions/urls.py
from django.urls import path
from . import views

app_name = 'discussions'

urlpatterns = [
    # Threads
    path('threads/', views.thread_list_create, name='thread_list_create'),
    path('threads/<uuid:thread_id>/', views.thread_detail, name='thread_detail'),
    path('threads/<uuid:thread_id>/subscribe/', views.thread_subscribe, name='thread_subscribe'),
    
    # Replies
    path('threads/<uuid:thread_id>/replies/', views.reply_create, name='reply_create'),
    path('threads/<uuid:thread_id>/replies/<uuid:reply_id>/', views.reply_detail, name='reply_detail'),
    path('threads/<uuid:thread_id>/replies/<uuid:reply_id>/like/', views.reply_like, name='reply_like'),
    path('threads/<uuid:thread_id>/replies/<uuid:reply_id>/moderate/', views.reply_moderate, name='reply_moderate'),
]
