# config/settings.py
from pathlib import Path
from decouple import config
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

_platform_domain_early = config('PLATFORM_DOMAIN', default='localhost')
_default_allowed_hosts = ["localhost", "127.0.0.1"]
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
X_FRAME_OPTIONS = "DENY"
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
    'apps.users',
    'apps.courses',
    'apps.progress',
    'apps.uploads',
    # 'apps.media',  # TODO: Implement media library app (Wave 2.13)
    'apps.reports',
    'apps.reminders',
    'apps.notifications',
    'apps.webhooks',
    'apps.discussions',
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
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT'),
        'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=600, cast=int),  # Reuse connections for 10 min
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

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

    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "access_key": AWS_ACCESS_KEY_ID,
            "secret_key": AWS_SECRET_ACCESS_KEY,
            "bucket_name": AWS_STORAGE_BUCKET_NAME,
            "region_name": AWS_S3_REGION_NAME or None,
            "endpoint_url": AWS_S3_ENDPOINT_URL or None,
            "use_ssl": AWS_S3_USE_SSL,
            "querystring_auth": AWS_QUERYSTRING_AUTH,
        },
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
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB before streaming to temp
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
MAX_VIDEO_UPLOAD_SIZE_MB = config("MAX_VIDEO_UPLOAD_SIZE_MB", default=500, cast=int)
FILE_UPLOAD_HANDLERS = [
    "django.core.files.uploadhandler.TemporaryFileUploadHandler",
]

# Ollama LLM for quiz generation (local, self-hosted)
OLLAMA_BASE_URL = config("OLLAMA_BASE_URL", default="http://localhost:11434")
OLLAMA_MODEL = config("OLLAMA_MODEL", default="mistral")

# REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
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
        'login': '5/minute',
        'password_reset': '3/minute',
        'register': '10/minute',
        'reminder_send': '10/hour',
        'video_upload': '20/hour',
        'impersonate': '10/hour',
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
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=config('JWT_ACCESS_TOKEN_LIFETIME', default=15, cast=int)),
    'REFRESH_TOKEN_LIFETIME': timedelta(minutes=config('JWT_REFRESH_TOKEN_LIFETIME', default=10080, cast=int)),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': config('JWT_SIGNING_KEY', default=SECRET_KEY),  # Separate from SECRET_KEY in prod
    'AUTH_HEADER_TYPES': ('Bearer',),
}

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
else:
    CORS_ALLOWED_ORIGINS = []

CORS_ALLOW_CREDENTIALS = True

# Production: use regex to allow wildcard subdomains (e.g., *.learnpuddle.com)
_escaped_domain = _platform_domain_early.replace('.', r'\.')
_cors_regex = config("CORS_ALLOWED_ORIGIN_REGEX", default=rf"^https://.*\.{_escaped_domain}$" if not DEBUG else "")
if _cors_regex:
    CORS_ALLOWED_ORIGIN_REGEXES = [_cors_regex]

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
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": config("REDIS_URL", default="redis://localhost:6379/1"),
        "OPTIONS": {
            "db": config("REDIS_CACHE_DB", default=1, cast=int),
        },
        "KEY_PREFIX": "lms",
        "TIMEOUT": 300,  # 5 minutes default
    }
}

# -----------------------------------------------------------------------------
# Celery (async job queue) - used for video processing pipeline
# -----------------------------------------------------------------------------
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=CELERY_BROKER_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_TIME_LIMIT = config("CELERY_TASK_TIME_LIMIT", default=60 * 60 * 2, cast=int)  # 2h
CELERY_TASK_SOFT_TIME_LIMIT = config("CELERY_TASK_SOFT_TIME_LIMIT", default=60 * 60 * 2 - 60, cast=int)
CELERY_RESULT_EXPIRES = config("CELERY_RESULT_EXPIRES", default=60 * 60 * 24, cast=int)  # 24h

# -----------------------------------------------------------------------------
# Django Channels (WebSocket) - real-time notifications
# -----------------------------------------------------------------------------
ASGI_APPLICATION = "config.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [config("REDIS_URL", default="redis://localhost:6379/2")],
            "capacity": 1500,
            "expiry": 10,
        },
    },
}

# Email Configuration
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default=f'noreply@{_platform_domain_early}')

# Platform branding (used in emails and public pages)
PLATFORM_NAME = config('PLATFORM_NAME', default='LearnPuddle')
PLATFORM_DOMAIN = _platform_domain_early

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
CSP_PATHS = ['/admin/', '/api/docs/', '/api/redoc/']  # Paths that get Django CSP (not React SPA)

# -----------------------------------------------------------------------------
# Sentry error tracking (optional; set SENTRY_DSN to enable)
# -----------------------------------------------------------------------------
SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN:
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            traces_sample_rate=config('SENTRY_TRACES_RATE', default=0.1, cast=float),
            send_default_pii=False,
            environment=config('SENTRY_ENVIRONMENT', default='production'),
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
# Two-Factor Authentication (2FA / MFA)
# -----------------------------------------------------------------------------
OTP_TOTP_ISSUER = config('OTP_ISSUER', default='Brain LMS')

# Number of backup codes to generate
OTP_STATIC_THROTTLE_FACTOR = 1
BACKUP_CODES_COUNT = 10
