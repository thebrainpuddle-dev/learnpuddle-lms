from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    # Teacher notifications
    path('', views.notification_list, name='list'),
    path('unread-count/', views.notification_unread_count, name='unread_count'),
    path('<uuid:notification_id>/read/', views.notification_mark_read, name='mark_read'),
    path('mark-read/', views.notification_bulk_mark_read, name='bulk_mark_read'),
    path('mark-all-read/', views.notification_mark_all_read, name='mark_all_read'),

    # Archival
    path('<uuid:notification_id>/archive/', views.notification_archive, name='archive'),
    path('bulk-archive/', views.notification_bulk_archive, name='bulk_archive'),

    # Admin announcements
    path('announcements/', views.announcement_list_create, name='announcements'),
    path('announcements/<uuid:announcement_id>/', views.announcement_delete, name='announcement_delete'),
]
