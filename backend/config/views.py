import logging

from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def health_view(_request):
    """
    Health check endpoint that verifies critical dependencies.
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
        from django.conf import settings
        import redis as redis_lib
        r = redis_lib.from_url(settings.CELERY_BROKER_URL)
        r.ping()
        checks["redis"] = "ok"
    except Exception as e:
        logger.error("Health check: redis failed: %s", e)
        checks["redis"] = "error"

    all_ok = all(v == "ok" for v in checks.values())
    return JsonResponse(
        {"status": "ok" if all_ok else "degraded", "checks": checks},
        status=200 if all_ok else 503,
    )
