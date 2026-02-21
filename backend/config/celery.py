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
    "send-automated-course-deadline-reminders-daily": {
        "task": "reminders.send_automated_course_deadline_reminders",
        "schedule": crontab(hour=6, minute=30),  # every day at 06:30 UTC
    },
    "ops-synthetic-probes-30s": {
        "task": "apps.ops.tasks.ops_run_synthetic_probes",
        "schedule": 30.0,
    },
    "ops-internal-failure-sweep-60s": {
        "task": "apps.ops.tasks.ops_sweep_internal_failures",
        "schedule": 60.0,
    },
    "ops-incident-evaluation-60s": {
        "task": "apps.ops.tasks.ops_evaluate_incidents",
        "schedule": 60.0,
    },
    "ops-maintenance-scheduler-5m": {
        "task": "apps.ops.tasks.ops_run_maintenance_scheduler",
        "schedule": 300.0,
    },
    "ops-data-cleanup-daily": {
        "task": "apps.ops.tasks.ops_cleanup_data",
        "schedule": crontab(hour=2, minute=30),
    },
}
