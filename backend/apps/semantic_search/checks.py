"""
Django system checks for ``apps.semantic_search``.

Verifies that the PostgreSQL ``pgvector`` extension is installed in the
active database. TASK-057's migration 0001 installs the extension
best-effort (wrapped in a savepoint), so a stock ``postgres:15`` image
still boots the app but silently returns ``[]`` for every semantic
search query. These checks surface that misconfiguration loudly.

Severity is environment-aware:

* ``DEBUG=True``  → emits ``semantic_search.W001`` (warning). Dev laptops
  can still run the non-semantic-search surface area of the app.
* ``DEBUG=False`` → emits ``semantic_search.E001`` (error). This causes
  ``manage.py check --deploy`` to fail and Gunicorn to refuse to start,
  preventing a prod deploy from silently losing vector search.

The probe is wrapped in a broad ``try/except``: any DB access error
(e.g. ``makemigrations --no-database``, ``collectstatic`` in a build
container without a live DB) causes the check to no-op.
"""

from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, Tags, Warning as CheckWarning, register
from django.db import connection


_REMEDIATION = (
    "Install pgvector — update the docker-compose db image to "
    "`pgvector/pgvector:pg15` (the upstream image used by docker-compose.yml) "
    "— not stock `postgres:15`. `ankane/pgvector:pg15` is a deprecated alias "
    "of the same image. Alternatively, run `CREATE EXTENSION vector;` as a DB "
    "superuser against the target database."
)


@register(Tags.database)
def pgvector_extension_installed(app_configs, **kwargs):
    """
    System check: verify ``CREATE EXTENSION vector`` has been run.

    Returns an empty list when the DB is unreachable so that offline
    management commands (``makemigrations``, ``collectstatic``) do not
    spuriously fail.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
            )
            row = cursor.fetchone()
    except Exception:
        # DB unreachable / wrong engine / permission denied — skip silently.
        return []

    if row is not None:
        return []

    message = (
        "pgvector extension is not installed on the active database. "
        "Semantic search will silently return empty results for every "
        "query. " + _REMEDIATION
    )

    if settings.DEBUG:
        return [
            CheckWarning(
                message,
                hint=_REMEDIATION,
                id="semantic_search.W001",
            )
        ]

    return [
        Error(
            message,
            hint=_REMEDIATION,
            id="semantic_search.E001",
        )
    ]
