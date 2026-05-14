# config/settings.py
from pathlib import Path
from decouple import config
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit

BASE_DIR = Path(__file__).resolve().parent.parent


def _redis_url_with_db(url: str, db: int) -> str:
    """Return a Redis URL using the same endpoint but a different DB index."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return f"redis://localhost:6379/{db}"
    if parts.scheme not in {"redis", "rediss"} or not parts.netloc:
        return f"redis://localhost:6379/{db}"
    return urlunsplit((parts.scheme, parts.netloc, f"/{db}", parts.query, parts.fragment))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

_platform_domain_early = config('PLATFORM_DOMAIN', default='localhost')
_default_allowed_hosts = ["localhost", ".localhost", "127.0.0.1"]
if _platform_domain_early != 'localhost':
    _default_allowed_hosts.append(f".{_platform_domain_early}")
_env_allowed_hosts = [h.strip() for h in config("ALLOWED_HOSTS", default="").split(",") if h.strip()]
ALLOWED_HOSTS = sorted(set(_default_allowed_hosts + _env_allowed_hosts))

# -----------------------------------------------------------------------------
# Production security hardening (configure via env in real deployments)
# -----------------------------------------------------------------------------

# If behind a proxy/load balancer (e.g., nginx), set X-Forwarded-Proto so Django
# can correctly detect HTTPS.
SECURE_PROXY_SSL_HEADER = (
    config("SECURE_PROXY_SSL_HEADER_NAME", default="HTTP_X_FORWARDED_PROTO"),
    config("SECURE_PROXY_SSL_HEADER_VALUE", default="https"),
)

SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=not DEBUG, cast=bool)

SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=not DEBUG, cast=bool)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=not DEBUG, cast=bool)

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

SESSION_COOKIE_SAMESITE = config("SESSION_COOKIE_SAMESITE", default="Lax")
CSRF_COOKIE_SAMESITE = config("CSRF_COOKIE_SAMESITE", default="Lax")

# Cookie domain — set to .{PLATFORM_DOMAIN} so cookies work across tenant subdomains
_cookie_domain = f".{_platform_domain_early}" if not DEBUG and _platform_domain_early != 'localhost' else None
SESSION_COOKIE_DOMAIN = config("SESSION_COOKIE_DOMAIN", default=_cookie_domain)
CSRF_COOKIE_DOMAIN = config("CSRF_COOKIE_DOMAIN", default=_cookie_domain)

SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=0 if DEBUG else 31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=not DEBUG, cast=bool)
SECURE_HSTS_PRELOAD = config("SECURE_HSTS_PRELOAD", default=not DEBUG, cast=bool)

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "SAMEORIGIN"
SECURE_REFERRER_POLICY = "same-origin"

# CSRF trusted origins (comma-separated), e.g. https://demo.lms.com,https://*.lms.com
_csrf_env = [o.strip() for o in config("CSRF_TRUSTED_ORIGINS", default="").split(",") if o.strip()]
_platform_domain = config('PLATFORM_DOMAIN', default='lms.com')
_csrf_defaults = [f"https://*.{_platform_domain}", f"https://{_platform_domain}"] if not DEBUG else []
CSRF_TRUSTED_ORIGINS = sorted(set(_csrf_env + _csrf_defaults))

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party apps
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',  # Token blacklisting
    'corsheaders',
    'django_filters',
    'django_celery_beat',  # Celery beat scheduler with DB backend
    'drf_spectacular',  # OpenAPI 3.0 schema generation
    'django_prometheus',  # Prometheus metrics
    'channels',  # WebSocket support
    'social_django',  # Social authentication (Google SSO)
    'django_otp',  # Two-factor authentication
    'django_otp.plugins.otp_totp',  # TOTP devices
    'django_otp.plugins.otp_static',  # Backup codes
    
    # Local apps
    'apps.tenants',
    'apps.billing',
    'apps.users',
    'apps.courses',
    'apps.maic',                    # AI Classroom v2 (MAIC) — Phase 0+, see docs/AI_CLASSROOM_BLUEPRINT.md
    'apps.maic_pbl',                # AI Classroom v2 PBL — Phase 7, see phase-7-pbl/ in obsidian-vault brain
    'apps.progress',
    'apps.uploads',
    'apps.media',
    'apps.reports',
    'apps.reminders',
    'apps.notifications',
    'apps.webhooks',
    'apps.discussions',
    'apps.ops',
    'apps.academics',
    'apps.reports_builder',  # Custom Report Builder (TASK-053)
    'apps.integrations_common',    # Shared crypto + helpers (TASK-055 / TASK-054)
    'apps.integrations_chat',      # Slack / Teams webhook bots (TASK-055)
    'apps.integrations_calendar',  # Google / Outlook / iCal calendar sync (TASK-054)
    'apps.translations',           # Auto-translation service (TASK-058)
    'apps.semantic_search',        # pgvector semantic search (TASK-057)
    'apps.course_generator',       # AI Course Generator (TASK-060)
    'apps.chatbot',                # AI Chatbot Tutor (TASK-059)
]

# Custom User Model
AUTH_USER_MODEL = 'users.User'

MIDDLEWARE = [
    # Prometheus metrics — must be at the very top for accurate timing
    'django_prometheus.middleware.PrometheusBeforeMiddleware',
    
    'utils.request_id_middleware.RequestIDMiddleware',  # Assigns X-Request-ID
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',  # CORS - must be before CommonMiddleware
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'utils.media_xframe_middleware.MediaXFrameExemptMiddleware',
    'utils.csp_middleware.CSPMiddleware',  # CSP with nonce support for Django admin

    # IMPORTANT: Tenant middleware must be after AuthenticationMiddleware
    'utils.tenant_middleware.TenantMiddleware',
    'utils.maintenance_middleware.MaintenanceModeWriteBlockMiddleware',
    'utils.ops_error_middleware.OpsRouteErrorCaptureMiddleware',
    
    # Logging context — must be after Auth and Tenant to capture user_id and tenant_id
    'utils.request_id_middleware.LoggingContextMiddleware',
    
    # Prometheus metrics — must be at the very bottom
    'django_prometheus.middleware.PrometheusAfterMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
# Using psycopg3 (modern PostgreSQL adapter)
_DB_CONN_MAX_AGE_DEFAULT = 0 if DEBUG else 600
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT'),
        # Local/CI runs do not have PgBouncer, and concurrent teacher tabs can
        # exhaust Postgres if every request thread parks an idle connection.
        # Production can keep reuse enabled via DB_CONN_MAX_AGE behind pooling.
        'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=_DB_CONN_MAX_AGE_DEFAULT, cast=int),
        'CONN_HEALTH_CHECKS': config('DB_CONN_HEALTH_CHECKS', default=True, cast=bool),
    }
}

# Password validation
# The TenantPasswordValidator reads the current tenant's
# TenantPasswordPolicy (see apps.tenants.password_policy_models) and
# enforces composition, common-password and history rules.  If no
# policy row exists (super-admin / mgmt commands) it falls back to a
# strict baseline (12 chars, mixed case, digit, common rejected).
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
    {'NAME': 'apps.users.password_validators.TenantPasswordValidator'},
]

# Password reset token expiration (Django default is 3 days = 259200 seconds)
PASSWORD_RESET_TIMEOUT = config('PASSWORD_RESET_TIMEOUT', default=1800, cast=int)  # 30 minutes

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# -----------------------------------------------------------------------------
# Storage (local filesystem by default; S3/MinIO optional)
# -----------------------------------------------------------------------------
STORAGE_BACKEND = config("STORAGE_BACKEND", default="local")  # local|s3

# Django 5 storage configuration uses STORAGES
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {
            "location": str(MEDIA_ROOT),
            "base_url": MEDIA_URL,
        },
    },
    # Use ManifestStaticFilesStorage in production for cache busting
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
            if not DEBUG else
            "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
    },
}

if STORAGE_BACKEND.lower() == "s3":
    # S3-compatible object storage (e.g. AWS S3, MinIO, Cloudflare R2)
    AWS_ACCESS_KEY_ID = config("STORAGE_ACCESS_KEY", default="")
    AWS_SECRET_ACCESS_KEY = config("STORAGE_SECRET_KEY", default="")
    AWS_STORAGE_BUCKET_NAME = config("STORAGE_BUCKET", default="")
    AWS_S3_REGION_NAME = config("STORAGE_REGION", default="")
    AWS_S3_ENDPOINT_URL = config("STORAGE_ENDPOINT", default="")
    AWS_S3_USE_SSL = config("STORAGE_USE_SSL", default=True, cast=bool)
    AWS_QUERYSTRING_AUTH = config("STORAGE_QUERYSTRING_AUTH", default=False, cast=bool)
    AWS_DEFAULT_ACL = None

    s3_options = {
        "access_key": AWS_ACCESS_KEY_ID,
        "secret_key": AWS_SECRET_ACCESS_KEY,
        "bucket_name": AWS_STORAGE_BUCKET_NAME,
        "region_name": AWS_S3_REGION_NAME or None,
        "endpoint_url": AWS_S3_ENDPOINT_URL or None,
        "use_ssl": AWS_S3_USE_SSL,
        "querystring_auth": AWS_QUERYSTRING_AUTH,
    }

    # Faster object upload throughput for larger files (server -> S3/Spaces).
    multipart_threshold_mb = max(config("S3_MULTIPART_THRESHOLD_MB", default=16, cast=int), 5)
    multipart_chunk_mb = max(config("S3_MULTIPART_CHUNK_SIZE_MB", default=8, cast=int), 5)
    max_concurrency = max(config("S3_MAX_CONCURRENCY", default=12, cast=int), 1)
    use_threads = config("S3_USE_THREADS", default=True, cast=bool)
    try:
        from boto3.s3.transfer import TransferConfig

        s3_options["transfer_config"] = TransferConfig(
            multipart_threshold=multipart_threshold_mb * 1024 * 1024,
            multipart_chunksize=multipart_chunk_mb * 1024 * 1024,
            max_concurrency=max_concurrency,
            use_threads=use_threads,
        )
    except Exception:
        pass

    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": s3_options,
    }

# -----------------------------------------------------------------------------
# CDN Configuration (for media delivery via CloudFront, Cloudflare, etc.)
# -----------------------------------------------------------------------------
# Set CDN_DOMAIN to serve media files through a CDN for better performance.
# Example: cdn.yourdomain.com, d1234567890.cloudfront.net
CDN_DOMAIN = config("CDN_DOMAIN", default="")
CDN_ENABLED = bool(CDN_DOMAIN)

if CDN_ENABLED:
    # Override MEDIA_URL to use CDN
    MEDIA_URL = f"https://{CDN_DOMAIN}/media/"
    
    # For S3 storage with CloudFront
    if STORAGE_BACKEND.lower() == "s3":
        # Use custom domain for S3 storage
        STORAGES["default"]["OPTIONS"]["custom_domain"] = CDN_DOMAIN

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# -----------------------------------------------------------------------------
# File upload settings (large video files must stream to disk, not memory)
# -----------------------------------------------------------------------------
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50MB (MAIC classroom sync
#   payloads can approach this — PATCH /classrooms/<id>/update/ ships
#   content {slides, scenes, sceneSlideBounds} for ~20-scene classrooms.
#   Was 10 MB and silently 400-rejected large classrooms. See PERF-P0-3.
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB — video uploads stream
#   to disk via FILE_UPLOAD_HANDLERS below, so this threshold stays tight.
MAX_VIDEO_UPLOAD_SIZE_MB = config("MAX_VIDEO_UPLOAD_SIZE_MB", default=500, cast=int)
# Shorter HLS segments improve startup latency and recovery on weak networks.
HLS_SEGMENT_DURATION_SECONDS = max(config("HLS_SEGMENT_DURATION_SECONDS", default=4, cast=int), 2)
FILE_UPLOAD_HANDLERS = [
    "django.core.files.uploadhandler.TemporaryFileUploadHandler",
]

# LLM Provider configuration
LLM_PROVIDER = config("LLM_PROVIDER", default="auto")
OPENROUTER_API_KEY = config("OPENROUTER_API_KEY", default="")
OPENROUTER_BASE_URL = config("OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1")
OPENROUTER_DEFAULT_MODEL = config("OPENROUTER_DEFAULT_MODEL", default="deepseek/deepseek-chat-v3-0324")
OPENROUTER_FALLBACK_MODELS = config("OPENROUTER_FALLBACK_MODELS", default="qwen/qwen3.6-plus:free,nvidia/nemotron-nano-9b-v2:free")

# Ollama LLM for quiz generation (local, self-hosted)
OLLAMA_BASE_URL = config("OLLAMA_BASE_URL", default="http://localhost:11434")
OLLAMA_MODEL = config("OLLAMA_MODEL", default="mistral")

# REST Framework Configuration
REST_FRAMEWORK = {
    # Normalize DRF's auto-generated {"detail": "..."} to {"error": "..."}
    # for consistency with manual error responses across all views.
    'EXCEPTION_HANDLER': 'utils.exception_handler.custom_exception_handler',
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
        # AUDIT-2026-04-26-PHASE3-12: enforce must_change_password flag globally.
        # Users with the flag set can only reach the password-change / login /
        # logout / token-refresh / health allowlist until they complete the reset.
        'apps.users.permissions.MustNotRequirePasswordChange',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
    ],
    # Basic rate-limiting (tune via env)
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': config('THROTTLE_ANON', default='200/minute'),
        'user': config('THROTTLE_USER', default='1000/minute'),
        'login': config('THROTTLE_LOGIN', default='5/minute'),
        'password_reset': '3/minute',
        'register': '10/minute',
        'reminder_send': '10/hour',
        'video_upload': '20/hour',
        'impersonate': '10/hour',
        'superadmin_email': '30/hour',
        # Email verification
        'email_verify': '10/minute',
        'resend_verify': '3/minute',
        # Tenant onboarding
        'tenant_signup': '5/hour',
        'subdomain_check': '30/minute',
        # Upload endpoints
        'upload': '30/minute',
        # 2FA verification (prevent brute force on 6-digit codes)
        'twofa_verify': '5/minute',
        # Teacher invitation acceptance (public endpoint — prevent brute force)
        'invitation_accept': '5/minute',
        # Academic admin destructive operations
        'csv_import': '10/hour',
        'promotion': '5/hour',
        # Client-side error ingestion (public endpoint)
        'client_error_ingest': '30/minute',
        # AI Chatbot chat endpoint
        'chatbot_chat': '30/minute',
        # Stripe webhook ingestion (public endpoint, signature-verified).
        # Rate-limit per-IP to mitigate DoS from invalid-signature spam.
        'stripe_webhook': '120/minute',
        # SAML Assertion Consumer Service — per-IP rate limit deters
        # signature-spam / replay attempts.
        'saml_acs': config('THROTTLE_SAML_ACS', default='30/minute'),
        # SCIM 2.0 protocol endpoints (AUDIT-2026-04-26-PHASE3-5):
        # ``scim-unauth`` is per-IP and protects against bearer-token guess
        # attacks (each guess is an unauth request); 30/min keeps it tight.
        # ``scim-token`` is per-token-hash steady-state — Okta/Azure can hit
        # ~100/min during a sync, 600/min gives ample headroom while still
        # containing a runaway IdP loop or a leaked-token scraper.
        'scim-unauth': config('SCIM_UNAUTH_RATE', default='30/min'),
        'scim-token': config('SCIM_TOKEN_RATE', default='600/min'),
        # Chat integration /test/ endpoint — prevent webhook spam / abuse.
        'chat_integration_test': config('THROTTLE_CHAT_INTEGRATION_TEST', default='5/hour'),
        # Semantic search query endpoint (TASK-057) — 60/min/user.
        'search_semantic': config('THROTTLE_SEARCH_SEMANTIC', default='60/minute'),
        # Teacher translation-read endpoint (TASK-058): 120/min/user.
        'teacher_translation_read': config('THROTTLE_TEACHER_TRANSLATION_READ', default='120/minute'),
    },
    # OpenAPI schema generation
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# -----------------------------------------------------------------------------
# API Documentation (drf-spectacular) - OpenAPI 3.0 schema
# Access Swagger UI at /api/docs/ and ReDoc at /api/redoc/
# -----------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    'TITLE': 'LMS Platform API',
    'DESCRIPTION': '''
Multi-tenant Learning Management System API.

## Authentication
Most endpoints require JWT authentication. Obtain tokens via `/api/v1/auth/token/`.

## Multi-tenancy
All requests must include the tenant subdomain (e.g., `demo.lms.com`).
The tenant is determined from the `Host` header or `X-Tenant-Subdomain` header.

## Roles
- **superadmin**: Platform-wide administration
- **admin**: Tenant administration (manage teachers, courses, settings)
- **teacher**: Course consumption (view courses, take quizzes, earn certificates)
''',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': True,
        'filter': True,
    },
    'SWAGGER_UI_DIST': 'SIDECAR',  # Use bundled swagger-ui
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    'REDOC_DIST': 'SIDECAR',
    # Security schemes for JWT
    'SECURITY': [{'bearerAuth': []}],
    'APPEND_COMPONENTS': {
        'securitySchemes': {
            'bearerAuth': {
                'type': 'http',
                'scheme': 'bearer',
                'bearerFormat': 'JWT',
            }
        }
    },
    # Tags for organizing endpoints
    'TAGS': [
        {'name': 'auth', 'description': 'Authentication and token management'},
        {'name': 'users', 'description': 'User management'},
        {'name': 'courses', 'description': 'Course management'},
        {'name': 'progress', 'description': 'Learning progress and certificates'},
        {'name': 'notifications', 'description': 'Notifications and announcements'},
        {'name': 'tenants', 'description': 'Tenant management (superadmin)'},
        {'name': 'admin', 'description': 'Tenant administration'},
        {'name': 'reports', 'description': 'Analytics and reporting'},
    ],
}

# JWT Configuration
JWT_SIGNING_KEY = config('JWT_SIGNING_KEY', default=SECRET_KEY)

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=config('JWT_ACCESS_TOKEN_LIFETIME', default=15, cast=int)),
    'REFRESH_TOKEN_LIFETIME': timedelta(minutes=config('JWT_REFRESH_TOKEN_LIFETIME', default=10080, cast=int)),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': JWT_SIGNING_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# Enforce separate JWT signing key in production
if not DEBUG and JWT_SIGNING_KEY == SECRET_KEY:
    import warnings
    warnings.warn(
        "SECURITY: JWT_SIGNING_KEY should be different from SECRET_KEY in production. "
        "Set JWT_SIGNING_KEY in environment variables.",
        RuntimeWarning,
        stacklevel=1,
    )

# CORS Configuration (for frontend)
# CORS - Allow localhost only in DEBUG mode, use regex for production
if DEBUG:
    CORS_ALLOWED_ORIGINS = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
    ]
    # Allow any subdomain of localhost (e.g., demo.localhost:3000) for tenant testing
    CORS_ALLOWED_ORIGIN_REGEXES = [
        r"^http://([a-z0-9-]+\.)?localhost:(3000|3001|3002|8000)$",
    ]
else:
    CORS_ALLOWED_ORIGINS = []

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-lp-portal",
    "x-lp-tab",
    "x-lp-route",
    "x-lp-component",
    "x-tenant-subdomain",
]

# Production: use regex to allow root + subdomains (learnpuddle.com, school.learnpuddle.com)
_escaped_domain = _platform_domain_early.replace('.', r'\.')
_cors_regex = config(
    "CORS_ALLOWED_ORIGIN_REGEX",
    default=rf"^https://([a-z0-9-]+\.)*{_escaped_domain}$" if not DEBUG else "",
)
if _cors_regex:
    CORS_ALLOWED_ORIGIN_REGEXES = [_cors_regex]

# Safety check: warn if no CORS origins are configured in production
if not DEBUG and not CORS_ALLOWED_ORIGINS and not CORS_ALLOWED_ORIGIN_REGEXES:
    import warnings
    warnings.warn(
        "CORS: No allowed origins configured for production. "
        "Set CORS_ALLOWED_ORIGINS or CORS_ALLOWED_ORIGIN_REGEX.",
        RuntimeWarning,
    )

# -----------------------------------------------------------------------------
# Logging - Structured JSON logging for production, simple format for dev
# Ships to any log aggregator (CloudWatch, Datadog, ELK, etc.)
# -----------------------------------------------------------------------------

# Use JSON logging in production, simple format in DEBUG mode
_use_json_logging = config("LOG_JSON", default=not DEBUG, cast=bool)
_log_level = config("LOG_LEVEL", default="INFO")

if _use_json_logging:
    # JSON structured logging with request context
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "utils.logging.ContextualJsonFormatter",
            },
            "simple": {
                "format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",
            },
        },
        "root": {
            "handlers": ["console"],
            "level": _log_level,
        },
        "loggers": {
            "django": {
                "handlers": ["console"],
                "level": _log_level,
                "propagate": False,
            },
            "django.request": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "django.db.backends": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "celery": {
                "handlers": ["console"],
                "level": _log_level,
                "propagate": False,
            },
            "apps": {
                "handlers": ["console"],
                "level": _log_level,
                "propagate": False,
            },
            "utils": {
                "handlers": ["console"],
                "level": _log_level,
                "propagate": False,
            },
        },
    }
else:
    # Simple format for local development
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "simple": {
                "format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "simple",
            },
        },
        "root": {
            "handlers": ["console"],
            "level": _log_level,
        },
    }

# -----------------------------------------------------------------------------
# Cache (Redis) - used for rate limiting, account lockout, and general caching
# -----------------------------------------------------------------------------
REDIS_URL = config("REDIS_URL", default="redis://localhost:6379/1")
REDIS_CACHE_DB = config("REDIS_CACHE_DB", default=1, cast=int)
REDIS_CHANNEL_DB = config("REDIS_CHANNEL_DB", default=2, cast=int)
REDIS_CACHE_URL = config(
    "REDIS_CACHE_URL",
    default=_redis_url_with_db(REDIS_URL, REDIS_CACHE_DB),
)
CHANNEL_REDIS_URL = config(
    "CHANNEL_REDIS_URL",
    default=_redis_url_with_db(REDIS_URL, REDIS_CHANNEL_DB),
)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_CACHE_URL,
        "OPTIONS": {
            "db": REDIS_CACHE_DB,
        },
        "KEY_PREFIX": "lms",
        "TIMEOUT": 300,  # 5 minutes default
    }
}

# -----------------------------------------------------------------------------
# Celery (async job queue) - used for video processing pipeline
# -----------------------------------------------------------------------------
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=CELERY_BROKER_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_TIME_LIMIT = config("CELERY_TASK_TIME_LIMIT", default=60 * 60 * 2, cast=int)  # 2h
CELERY_TASK_SOFT_TIME_LIMIT = config("CELERY_TASK_SOFT_TIME_LIMIT", default=60 * 60 * 2 - 60, cast=int)
CELERY_RESULT_EXPIRES = config("CELERY_RESULT_EXPIRES", default=60 * 60 * 24, cast=int)  # 24h

# Celery Beat periodic task schedule
#
# DO NOT add tasks here.  Celery's config_from_object() layer (namespace="CELERY")
# is overridden by the explicit app.conf.beat_schedule assignment in
# config/celery.py, making any entry here a silent no-op.
#
# → Add all periodic tasks to the beat_schedule dict in config/celery.py instead.
#
# This CELERY_BEAT_SCHEDULE key is intentionally left absent so that Django's
# check framework does not flag an "unused setting" warning, and so that no
# developer is misled into thinking entries here take effect.

# -----------------------------------------------------------------------------
# Django Channels (WebSocket) - real-time notifications
# -----------------------------------------------------------------------------
ASGI_APPLICATION = "config.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [CHANNEL_REDIS_URL],
            "capacity": 1500,
            "expiry": 10,
        },
    },
}

# Email Configuration
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='smtp.resend.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_TIMEOUT = config('EMAIL_TIMEOUT', default=15, cast=int)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default=f'noreply@{_platform_domain_early}')

# Reminder email sending (disabled by default - uses in-app notifications only)
# Set REMINDER_EMAIL_ENABLED=True to also send reminder emails
REMINDER_EMAIL_ENABLED = config('REMINDER_EMAIL_ENABLED', default=False, cast=bool)
SEND_ONBOARDING_EMAIL = config('SEND_ONBOARDING_EMAIL', default=True, cast=bool)
COURSE_ASSIGNMENT_EMAIL_ENABLED = config('COURSE_ASSIGNMENT_EMAIL_ENABLED', default=True, cast=bool)
EMAIL_FAIL_SILENTLY = config('EMAIL_FAIL_SILENTLY', default=False, cast=bool)
AUTO_COURSE_REMINDERS_ENABLED = config('AUTO_COURSE_REMINDERS_ENABLED', default=True, cast=bool)
# CSV list of lead-day checkpoints when automation sends reminders.
# Example: "7,3,1,0" => one week, three days, one day, and due day.
AUTO_COURSE_REMINDER_LEAD_DAYS = config('AUTO_COURSE_REMINDER_LEAD_DAYS', default='7,3,1,0')

# Cal.com webhook integration (demo booking automation)
CAL_WEBHOOK_SECRET = config('CAL_WEBHOOK_SECRET', default='')

# Platform branding (used in emails and public pages)
PLATFORM_NAME = config('PLATFORM_NAME', default='LearnPuddle')
PLATFORM_DOMAIN = _platform_domain_early

# Ops / super-admin operations pipeline settings
OPS_PROBE_TIMEOUT_SECONDS = config("OPS_PROBE_TIMEOUT_SECONDS", default=5, cast=int)
OPS_PROBE_BASE_URL = config("OPS_PROBE_BASE_URL", default="")
OPS_PROBE_SCHEME = config("OPS_PROBE_SCHEME", default="https" if not DEBUG else "http")
OPS_HARNESS_SHARED_SECRET = config("OPS_HARNESS_SHARED_SECRET", default="")
OPS_RETENTION_DAYS = config("OPS_RETENTION_DAYS", default=30, cast=int)

# TEST-P1-10: Prometheus /metrics scrape endpoint allowlist.
# Comma-separated list of IPs that may scrape /metrics/. Empty list (default)
# means deny-all to non-staff. SUPER_ADMIN + SCHOOL_ADMIN sessions always pass.
# In production set this to the Prometheus scraper's IP (e.g. internal VPC).
# Example: METRICS_ALLOW_IPS=10.0.0.5,10.0.0.6
METRICS_ALLOW_IPS = [
    ip.strip()
    for ip in config("METRICS_ALLOW_IPS", default="").split(",")
    if ip.strip()
]

# -----------------------------------------------------------------------------
# Content Security Policy (CSP) configuration
# -----------------------------------------------------------------------------
# CSP is applied differently for:
# - Django admin/docs: Strict CSP with nonces (via CSPMiddleware)
# - React SPA: CSP set in nginx (requires 'unsafe-inline' for styles due to React/Tailwind)
#
# The main security benefit comes from script-src restrictions. Style-based attacks
# (CSS exfiltration) are much more limited than XSS via script injection.

CSP_ENABLED = config('CSP_ENABLED', default=True, cast=bool)
CSP_REPORT_ONLY = config('CSP_REPORT_ONLY', default=False, cast=bool)  # Set True to test without enforcing
CSP_REPORT_URI = config('CSP_REPORT_URI', default='')  # e.g., /api/csp-report/ or external service
CSP_PATHS = ['/django-admin/', '/api/docs/', '/api/redoc/']  # Paths that get Django CSP (not React SPA)

# -----------------------------------------------------------------------------
# Sentry error tracking (optional; set SENTRY_DSN to enable)
# -----------------------------------------------------------------------------
SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.redis import RedisIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[
                DjangoIntegration(),
                CeleryIntegration(),
                RedisIntegration(),
            ],
            traces_sample_rate=config('SENTRY_TRACES_RATE', default=0.1 if not DEBUG else 1.0, cast=float),
            send_default_pii=False,
            environment=config('SENTRY_ENVIRONMENT', default='development' if DEBUG else 'production'),
        )
    except ImportError:
        pass  # sentry-sdk not installed; silently skip

# -----------------------------------------------------------------------------
# Social Authentication (SSO) - Google Workspace
# -----------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    'social_core.backends.google.GoogleOAuth2',
    'django.contrib.auth.backends.ModelBackend',
]

# Google OAuth2 credentials (from Google Cloud Console)
SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = config('GOOGLE_OAUTH_CLIENT_ID', default='')
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = config('GOOGLE_OAUTH_CLIENT_SECRET', default='')
SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE = [
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
]

# Where to redirect after successful SSO login
SOCIAL_AUTH_LOGIN_REDIRECT_URL = '/auth/sso-callback'
SOCIAL_AUTH_LOGIN_ERROR_URL = '/login?error=sso_failed'

# Pipeline to handle user creation/matching
SOCIAL_AUTH_PIPELINE = (
    'social_core.pipeline.social_auth.social_details',
    'social_core.pipeline.social_auth.social_uid',
    'social_core.pipeline.social_auth.auth_allowed',
    'social_core.pipeline.social_auth.social_user',
    'social_core.pipeline.user.get_username',
    'apps.users.sso_pipeline.associate_by_email',  # Custom: match by email
    'apps.users.sso_pipeline.create_user_if_allowed',  # Custom: create only if tenant allows
    'social_core.pipeline.social_auth.associate_user',
    'social_core.pipeline.social_auth.load_extra_data',
    'social_core.pipeline.user.user_details',
)

# Restrict SSO to certain domains (Google Workspace domains)
SOCIAL_AUTH_GOOGLE_OAUTH2_WHITELISTED_DOMAINS = config(
    'SSO_ALLOWED_DOMAINS',
    default='',
    cast=lambda v: [d.strip() for d in v.split(',') if d.strip()] if v else []
)

# -----------------------------------------------------------------------------
# Calendar Integrations (TASK-054) — Google Calendar + Outlook / MS Graph
# -----------------------------------------------------------------------------
GOOGLE_CALENDAR_CLIENT_ID = config('GOOGLE_CALENDAR_CLIENT_ID', default='')
GOOGLE_CALENDAR_CLIENT_SECRET = config('GOOGLE_CALENDAR_CLIENT_SECRET', default='')
# Full redirect URI, e.g. https://app.learnpuddle.com/api/v1/calendar/google/callback/
GOOGLE_CALENDAR_REDIRECT_URI = config('GOOGLE_CALENDAR_REDIRECT_URI', default='')

OUTLOOK_CLIENT_ID = config('OUTLOOK_CLIENT_ID', default='')
OUTLOOK_CLIENT_SECRET = config('OUTLOOK_CLIENT_SECRET', default='')
# Use "common" for multi-tenant MS apps, or a specific tenant UUID.
OUTLOOK_TENANT_ID = config('OUTLOOK_TENANT_ID', default='common')
OUTLOOK_CALENDAR_REDIRECT_URI = config('OUTLOOK_CALENDAR_REDIRECT_URI', default='')

# -----------------------------------------------------------------------------
# Two-Factor Authentication (2FA / MFA)
# -----------------------------------------------------------------------------
OTP_TOTP_ISSUER = config('OTP_ISSUER', default='LearnPuddle')

# Number of backup codes to generate
OTP_STATIC_THROTTLE_FACTOR = 1
BACKUP_CODES_COUNT = 10

# -----------------------------------------------------------------------------
# Stripe Configuration (billing & subscriptions)
# -----------------------------------------------------------------------------
STRIPE_SECRET_KEY = config('STRIPE_SECRET_KEY', default='')
STRIPE_PUBLISHABLE_KEY = config('STRIPE_PUBLISHABLE_KEY', default='')
STRIPE_WEBHOOK_SECRET = config('STRIPE_WEBHOOK_SECRET', default='')

# -----------------------------------------------------------------------------
# ElevenLabs TTS (Text-to-Speech)
# -----------------------------------------------------------------------------
ELEVENLABS_API_KEY = config('ELEVENLABS_API_KEY', default='')

# -----------------------------------------------------------------------------
# Auto-Translation Service (TASK-058)
# -----------------------------------------------------------------------------
# Provider selection: 'auto' (OpenRouter → Azure → Stub), 'openrouter',
# 'azure', or 'stub'. Stub is disallowed in production unless
# TRANSLATION_ALLOW_STUB=1 (defence against accidental deploys).
TRANSLATION_PROVIDER = config('TRANSLATION_PROVIDER', default='auto')
TRANSLATION_ALLOW_STUB = config('TRANSLATION_ALLOW_STUB', default=False, cast=bool)
TRANSLATION_OPENROUTER_MODEL = config(
    'TRANSLATION_OPENROUTER_MODEL',
    default='meta-llama/llama-3.1-70b-instruct',
)

# Allowlisted target languages (comma-separated BCP-47 codes). Values not
# in this list are rejected by the API with 400 UNSUPPORTED_LANGUAGE.
TRANSLATION_TARGET_LANGUAGES = config(
    'TRANSLATION_TARGET_LANGUAGES',
    default='es,fr,de,hi,zh-CN,ar',
)

# Azure Translator credentials (optional fallback provider).
AZURE_TRANSLATOR_KEY = config('AZURE_TRANSLATOR_KEY', default='')
AZURE_TRANSLATOR_REGION = config('AZURE_TRANSLATOR_REGION', default='')
AZURE_TRANSLATOR_ENDPOINT = config(
    'AZURE_TRANSLATOR_ENDPOINT',
    default='https://api.cognitive.microsofttranslator.com',
)

# -----------------------------------------------------------------------------
# AI Course Generator (TASK-060)
# -----------------------------------------------------------------------------
# Provider selection: 'auto' (OpenRouter → Ollama → Stub), 'openrouter',
# 'ollama', or 'stub'. Stub is disallowed in production unless
# COURSE_GENERATOR_ALLOW_STUB=1.
COURSE_GENERATOR_LLM_PROVIDER = config('COURSE_GENERATOR_LLM_PROVIDER', default='auto')
COURSE_GENERATOR_ALLOW_STUB = config('COURSE_GENERATOR_ALLOW_STUB', default=False, cast=bool)
COURSE_GENERATOR_OPENROUTER_MODEL = config(
    'COURSE_GENERATOR_OPENROUTER_MODEL',
    default='meta-llama/llama-3.1-70b-instruct',
)
COURSE_GENERATOR_OLLAMA_MODEL = config('COURSE_GENERATOR_OLLAMA_MODEL', default='llama3')

# AI Chatbot Tutor (TASK-059)
# -----------------------------------------------------------------------------
# Provider selection: 'auto' (OpenRouter → Ollama → Stub), 'openrouter',
# 'ollama', or 'stub'. Stub is disallowed in production unless
# CHATBOT_ALLOW_STUB=1.
CHATBOT_LLM_PROVIDER = config('CHATBOT_LLM_PROVIDER', default='auto')
CHATBOT_ALLOW_STUB = config('CHATBOT_ALLOW_STUB', default=False, cast=bool)
CHATBOT_OPENROUTER_MODEL = config(
    'CHATBOT_OPENROUTER_MODEL',
    default='meta-llama/llama-3.1-70b-instruct',
)
CHATBOT_OLLAMA_MODEL = config('CHATBOT_OLLAMA_MODEL', default='llama3')

# AI Classroom v2 (MAIC v2)
# -----------------------------------------------------------------------------
# Master kill-switch for the new MAIC stack added in apps/maic/. When False,
# the V2 WS route (/ws/maic/v2/classroom/<session_id>/) is NOT mounted in
# config/asgi.py and (in MAIC-007) the V2 HTTP routes + frontend probe page
# are unreachable.  V1 (apps/courses/maic_*) is unaffected by this flag.
# See docs/AI_CLASSROOM_BLUEPRINT.md and the project brain at
# obsidian-vault/agent-hq/projects/learnpuddle-lms/maic-rebuild/.
MAIC_V2_ENABLED = config('MAIC_V2_ENABLED', default=False, cast=bool)
# MAIC v2 must use a tenant's configured provider in production. The stub
# stream is kept for explicit local/test probes only and is off by default.
MAIC_V2_ALLOW_STUB = config('MAIC_V2_ALLOW_STUB', default=False, cast=bool)
MAIC_V2_ALLOW_REQUEST_MODEL_OVERRIDE = config(
    'MAIC_V2_ALLOW_REQUEST_MODEL_OVERRIDE',
    default=False,
    cast=bool,
)

# Phase 4+ (MAIC-431) — generation pipeline v1→v2 gate. The teacher portal
# wizard now submits to `/api/maic/v2/generate/` by default. Keep the flag as
# the emergency rollback switch: set MAIC_GENERATION_USE_V2=false to remount
# the legacy per-step v1 generation endpoints during an incident.
MAIC_GENERATION_USE_V2 = config('MAIC_GENERATION_USE_V2', default=True, cast=bool)
