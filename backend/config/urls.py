# config/urls.py

from django.contrib import admin
from django.urls import path, include, re_path
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

# Course Templates library (TASK-049): one URL module, mounted under two roots.
from apps.courses.template_urls import (
    super_admin_urlpatterns as course_template_super_admin_urls,
    tenant_admin_urlpatterns as course_template_tenant_admin_urls,
)

# Auto-translation service (TASK-058): one URL module, two mount points.
from apps.translations.urls import (
    admin_urlpatterns as translations_admin_urls,
    teacher_urlpatterns as translations_teacher_urls,
)

# Versioned API routes — all new clients should use /api/v1/
_api_patterns = [
    # Course templates — platform CRUD (SUPER_ADMIN) + tenant list/preview/clone.
    path(
        'super-admin/',
        include((course_template_super_admin_urls, 'course_templates_super_admin')),
    ),
    path(
        'admin/',
        include((course_template_tenant_admin_urls, 'course_templates_tenant_admin')),
    ),
    path('super-admin/', include('apps.tenants.superadmin_urls')),
    path('tenants/', include('apps.tenants.urls')),
    path('onboarding/', include('apps.tenants.onboarding_urls')),  # Public tenant signup
    path('users/', include('apps.users.urls')),
    path('', include('apps.users.admin_urls')),
    path('courses/', include('apps.courses.urls')),
    path('', include('apps.courses.group_urls')),
    # MAIC v2 sessions endpoint (Phase 1 MAIC-301).  WS routes are
    # mounted separately in config/asgi.py via apps.maic.routing.
    path('maic/v2/', include('apps.maic.urls', namespace='maic_v2')),
    # PBL subsystem (Phase 7 MAIC-704). HTTP at /api/maic/v2/pbl/projects/;
    # WS at /ws/maic/pbl/<session_id>/ (mounted in config/asgi.py).
    path('maic/v2/pbl/', include('apps.maic_pbl.urls', namespace='maic_pbl')),
    # Media generation (Phase 9 MAIC-914) — POST /api/maic/v2/media/
    # generate-{image,video}/. Provider adapters auto-register on import
    # (apps/maic/media/adapters/__init__.py).
    path('maic/v2/media/', include('apps.maic.media.urls', namespace='maic_media')),
    # Content versioning (TASK-048) — admin-only revisions/restore endpoints.
    path('admin/', include('apps.courses.versioning_urls')),
    # SCORM 1.2 export (TASK-052) — admin-only export endpoints.
    path('admin/', include('apps.courses.scorm_export_urls')),
    # SCORM 1.2 + xAPI (TASK-047)
    path('', include('apps.courses.scorm_urls')),
    path('', include('apps.courses.xapi_urls')),
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
    path('admin/reports/', include('apps.reports_builder.urls')),  # Custom Report Builder (TASK-053)
    path('skills/', include('apps.progress.skills_urls')),
    path('certifications/', include('apps.progress.certification_urls')),
    path('gamification/', include('apps.progress.gamification_urls')),
    path('', include('apps.progress.assessment_urls')),
    path('', include('apps.progress.rubric_urls')),
    path('reminders/', include('apps.reminders.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('webhooks/', include('apps.webhooks.urls')),
    path('discussions/', include('apps.discussions.urls')),
    path('billing/', include('apps.billing.urls')),
    path('ops/', include('apps.ops.public_urls')),
    path('parent/', include('apps.courses.parent_urls')),

    # SAML 2.0 SSO endpoints (per-tenant, tenant is in URL path).
    path('', include('apps.users.saml_urls')),

    # SCIM 2.0 token management — admin creates/revokes per-tenant bearer tokens.
    path('admin/sso/', include('apps.users.scim_admin_urls')),

    # Chat integrations — Slack / Teams webhook bots (TASK-055).
    path('admin/chat-integrations/', include('apps.integrations_chat.urls')),

    # Auto-translation service (TASK-058) — admin endpoints + teacher read path.
    path(
        'admin/translations/',
        include((translations_admin_urls, 'translations_admin')),
    ),
    path(
        'teacher/',
        include((translations_teacher_urls, 'translations_teacher')),
    ),

    # Calendar integrations — Google / Outlook / iCal (TASK-054).
    path('', include('apps.integrations_calendar.urls')),

    # Semantic search (TASK-057) — pgvector embeddings retrieval.
    path(
        'search/',
        include(('apps.semantic_search.urls_search', 'semantic_search')),
    ),
    path(
        'admin/search/',
        include(('apps.semantic_search.urls_admin', 'semantic_search_admin')),
    ),

    # AI Course Generator (TASK-060) — admin-only, tenant-scoped.
    path(
        'admin/course-generator/',
        include(('apps.course_generator.urls', 'course_generator')),
    ),

    # AI Chatbot Tutor (TASK-059) — authenticated teachers + admins.
    path(
        'chatbot/',
        include(('apps.chatbot.urls', 'chatbot')),
    ),
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
    # CG-P0-9: MAIC slide images served without auth so <img> tags load.
    # Path components include 122-bit tenant + classroom UUIDs → unguessable
    # ≈ S3 presigned URL risk model. Helpers + allowlist regex live in
    # utils/media_views.py:_AI_STUDIO_IMAGE_PATTERN.
    re_path(
        r'^media/(?P<path>course_content/tenant/[^/]+/ai_studio/lessons/[^/]+/images/.+)$',
        public_media_view,
        name='public_media_ai_studio_slide_images',
    ),
    # Protected media files (auth required, tenant-isolated)
    path('media/<path:path>', protected_media_view, name='protected_media'),

    # Public webhook endpoints (no JWT auth, signature-verified)
    path('api/webhooks/cal/', cal_webhook, name='cal_webhook'),
    path('api/webhooks/stripe/', stripe_webhook, name='stripe_webhook'),

    # SCIM 2.0 provisioning protocol — outside /api/v1/ per RFC 7644.
    # IdPs (Okta, Azure AD, OneLogin) call /scim/v2/Users directly.
    path('scim/v2/', include('apps.users.scim_urls')),

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

# Prometheus metrics endpoint (TEST-P1-10).
# Gated by IP allowlist (settings.METRICS_ALLOW_IPS) OR staff session OR DEBUG.
# The view is always wired so prod scrapers can reach it from the allowlisted
# Prometheus host without depending on DEBUG=True.
from utils.metrics import metrics_view  # noqa: E402

urlpatterns += [path('metrics/', metrics_view, name='prometheus_metrics')]

# Also expose django-prometheus's auto-instrumented /-prefixed metrics in DEBUG
# (request count by view, ORM histograms, etc) for local observation.
if settings.DEBUG:
    urlpatterns += [path('django-prometheus/', include('django_prometheus.urls'))]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
