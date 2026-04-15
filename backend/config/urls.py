# config/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)
from .views import health_live_view, health_ready_view, health_view
from utils.media_views import protected_media_view, public_media_view
from apps.tenants.webhook_views import cal_webhook
from apps.billing.webhook_views import stripe_webhook

# Versioned API routes — all new clients should use /api/v1/
_api_patterns = [
    path('super-admin/', include('apps.tenants.superadmin_urls')),
    path('tenants/', include('apps.tenants.urls')),
    path('onboarding/', include('apps.tenants.onboarding_urls')),  # Public tenant signup
    path('users/', include('apps.users.urls')),
    path('', include('apps.users.admin_urls')),
    path('courses/', include('apps.courses.urls')),
    path('', include('apps.courses.group_urls')),
    path('teacher/', include('apps.courses.teacher_urls')),
    path('teacher/', include('apps.progress.teacher_urls')),
    path('teacher/', include('apps.tenants.teacher_cert_urls')),
    path('student/', include('apps.courses.student_urls')),
    path('student/', include('apps.progress.student_urls')),
    path('student/', include(('apps.academics.attendance_student_urls', 'student_attendance'))),
    path('students/', include('apps.users.student_admin_urls')),
    path('academics/', include('apps.academics.admin_urls')),
    path('teacher/academics/', include('apps.academics.teacher_urls')),
    path('uploads/', include('apps.uploads.urls')),
    path('media/', include('apps.media.urls')),
    path('reports/', include('apps.reports.urls')),
    path('skills/', include('apps.progress.skills_urls')),
    path('certifications/', include('apps.progress.certification_urls')),
    path('gamification/', include('apps.progress.gamification_urls')),
    path('reminders/', include('apps.reminders.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('webhooks/', include('apps.webhooks.urls')),
    path('discussions/', include('apps.discussions.urls')),
    path('billing/', include('apps.billing.urls')),
    path('ops/', include('apps.ops.public_urls')),
    path('parent/', include('apps.courses.parent_urls')),
]

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('health/live/', health_live_view),
    path('health/ready/', health_ready_view),
    path('health/', health_view),
    
    # Public media (thumbnails, logos, profile pics — no auth needed for <img> tags)
    path('media/course_thumbnails/<path:path>', public_media_view, name='public_media_thumbnails'),
    path('media/profile_pictures/<path:path>', public_media_view, name='public_media_profiles'),
    path('media/learning_path_thumbnails/<path:path>', public_media_view, name='public_media_learning_paths'),
    path('media/tenant_logos/<path:path>', public_media_view, name='public_media_logos'),
    # Protected media files (auth required, tenant-isolated)
    path('media/<path:path>', protected_media_view, name='protected_media'),

    # Public webhook endpoints (no JWT auth, signature-verified)
    path('api/webhooks/cal/', cal_webhook, name='cal_webhook'),
    path('api/webhooks/stripe/', stripe_webhook, name='stripe_webhook'),

    # Versioned API (canonical)
    path('api/v1/', include((_api_patterns, 'api_v1'))),
    # Backward-compatible unversioned API (mirrors v1)
    path('api/', include((_api_patterns, 'api'))),
    
]

# API Documentation (OpenAPI 3.0) - only in DEBUG mode
# In production, disable or protect behind VPN/IP whitelist in nginx
if settings.DEBUG:
    urlpatterns += [
        path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
        path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
        path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    ]

# Prometheus metrics endpoint
# In production, metrics should be accessed via internal network only (nginx blocks it)
if settings.DEBUG:
    urlpatterns += [path('', include('django_prometheus.urls'))]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
