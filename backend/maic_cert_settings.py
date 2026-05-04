"""Settings shim for the MAIC v2 cert / demo daphne process.

Inherits from `config.settings` (the production-shaped Django config)
but overrides the database to a SQLite file so the demo doesn't
require a running Postgres. The SQLite location is read from the
MAIC_CERT_DB env var; the same path was used by the previous
maic_cert_settings module so user/tenant rows survive across daphne
restarts.

Daphne picks this up via DJANGO_SETTINGS_MODULE=maic_cert_settings.
"""
from __future__ import annotations

import os
from pathlib import Path

# Inherit everything from the regular config.
from config.settings import *  # noqa: F401,F403

# ── SQLite override ────────────────────────────────────────────────


_SQLITE_PATH = os.environ.get(
    "MAIC_CERT_DB",
    str(Path("/tmp/maic_cert.sqlite3")),
)

DATABASES = {  # noqa: F811 — intentional override of config.settings
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": _SQLITE_PATH,
        "OPTIONS": {
            "timeout": 30,
        },
    },
}

# DB_* env vars must remain present while config.settings is being
# imported (decouple raises if they're missing). The override above
# already replaced the DATABASES dict — the env vars are no longer
# read by Django after import.
