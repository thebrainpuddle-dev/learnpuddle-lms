import logging

from django.conf import settings
from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def health_live_view(_request):
    """
    Lightweight liveness probe.
    Confirms the process is alive without checking external dependencies.
    """
    return JsonResponse({"status": "ok", "probe": "live"}, status=200)


def health_ready_view(_request):
    """
    Readiness probe that verifies critical dependencies.
    Returns 200 only if DB and Redis are reachable.
    """
    checks = {}

    # Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as e:
        logger.error("Health check: database failed: %s", e)
        checks["database"] = "error"

    # Redis / Celery broker check
    try:
        import redis as redis_lib
        redis_url = getattr(settings, "CELERY_BROKER_URL", None) or getattr(settings, "REDIS_URL", "redis://localhost:6379/1")
        r = redis_lib.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        r.ping()
        checks["redis"] = "ok"
    except Exception as e:
        logger.error("Health check: redis failed: %s", e)
        checks["redis"] = "error"

    all_ok = all(v == "ok" for v in checks.values())
    return JsonResponse(
        {"status": "ok" if all_ok else "degraded", "probe": "ready", "checks": checks},
        status=200 if all_ok else 503,
    )


def health_view(request):
    """
    Backward-compatible health endpoint.
    Historically /health/ represented readiness, so keep that behavior.
    """
    return health_ready_view(request)
