# apps/media/urls.py

from django.urls import path
from . import views

app_name = 'media'

urlpatterns = [
    path('', views.media_list_create, name='media_list_create'),
    path('stats/', views.media_stats, name='media_stats'),
    path('file/<path:path>', views.serve_media_file, name='serve_media_file'),
    path('<uuid:asset_id>/', views.media_detail, name='media_detail'),
]
