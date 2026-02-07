import os

from celery import Celery
from celery.schedules import crontab


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("lms")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


# ── Periodic (beat) schedule ───────────────────────────────────────────────
app.conf.beat_schedule = {
    "check-trial-expirations-daily": {
        "task": "tenants.check_trial_expirations",
        "schedule": crontab(hour=6, minute=0),  # every day at 06:00 UTC
    },
}

