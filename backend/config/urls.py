# config/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from .views import health_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health_view),
    
    # API endpoints
    path('api/super-admin/', include('apps.tenants.superadmin_urls')),
    path('api/tenants/', include('apps.tenants.urls')),
    path('api/users/', include('apps.users.urls')),
    path('api/', include('apps.users.admin_urls')),
    path('api/courses/', include('apps.courses.urls')),
    path('api/', include('apps.courses.group_urls')),
    path('api/teacher/', include('apps.courses.teacher_urls')),
    path('api/teacher/', include('apps.progress.teacher_urls')),
    path('api/uploads/', include('apps.uploads.urls')),
    path('api/reports/', include('apps.reports.urls')),
    path('api/reminders/', include('apps.reminders.urls')),
    path('api/notifications/', include('apps.notifications.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
