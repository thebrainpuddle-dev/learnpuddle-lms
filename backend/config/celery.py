import os

from celery import Celery
from celery.schedules import crontab


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("lms")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
app.autodiscover_tasks(["apps.courses"], related_name="ai_studio_tasks")


# ── PERF-P0-5: dedicated `tts` queue for per-scene TTS fan-out ─────────────
# The chord-orchestrated TTS pipeline (see ``apps.courses.maic_tasks``) splits
# every classroom into one ``_tts_one_scene`` task per scene plus a
# ``_finalize_classroom_tts`` callback. Routing them onto a dedicated queue
# lets us spin up a separate ``worker-tts`` service whose concurrency is
# tuned to the TTS provider's per-tenant rate-limit (≈8-16 concurrent
# requests) without starving the default queue (notifications, ops, etc.).
#
# Tasks already named with a ``.tts.`` prefix in their ``name=`` kwarg are
# routed automatically; the orchestrator parent task
# (``pre_generate_classroom_tts``) intentionally stays on the ``default``
# queue so that the publish endpoint's ``.delay()`` call is not throttled by
# TTS-worker capacity.
app.conf.task_routes = {
    "apps.courses.maic_tasks.tts.*": {"queue": "tts"},
    # CG-P0-5 (2026-04-27): without an explicit route, Celery would put this
    # on the default-named "celery" queue, which our workers don't subscribe
    # to (-Q default,video,notifications). Tasks accumulated forever in Redis
    # → images_pending stayed True forever → slides rendered with empty src.
    # Pin to "default" so the existing worker pool actually executes it.
    "apps.courses.maic_tasks.fill_classroom_images": {"queue": "default"},
    # Same root cause: semantic_search.* tasks were unrouted and piled up
    # 210-deep on the unread "celery" queue. Pin to default.
    "semantic_search.*": {"queue": "default"},
}


# ── SPRINT-2-BATCH-9-F3: bound chord-result row lifetime ───────────────────
# The PERF-P0-5 chord pipeline emits one result-backend row per chord member
# (``_tts_one_scene``) plus one for the callback (``_finalize_classroom_tts``)
# per published classroom. Without a finite ``result_expires`` these rows
# accumulate forever in Redis (or django-celery-results' DB table), bloating
# the result-backend over time. 1 hour is well past the chord's worst-case
# completion (≈ minutes) and gives Flower enough window to surface failures.
app.conf.result_expires = 3600  # seconds — 1 hour


# ── Periodic (beat) schedule ───────────────────────────────────────────────
#
# IMPORTANT: This is the SINGLE authoritative source for all Celery beat tasks.
#
# Do NOT add tasks to CELERY_BEAT_SCHEDULE in settings.py — that key is
# processed by Celery's config_from_object() layer, which is overridden by
# this explicit app.conf.beat_schedule assignment.  Any task registered only
# in CELERY_BEAT_SCHEDULE will be silently ignored.
#
# All tasks from the former settings.py CELERY_BEAT_SCHEDULE have been
# merged here to fix the silent-drop bug (2026-04-28).
app.conf.beat_schedule = {
    # ── Tenant / subscription lifecycle ──────────────────────────────────
    "check-trial-expirations-daily": {
        "task": "tenants.check_trial_expirations",
        "schedule": crontab(hour=6, minute=0),  # every day at 06:00 UTC
    },

    # ── Reminders ─────────────────────────────────────────────────────────
    "send-automated-course-deadline-reminders-daily": {
        "task": "reminders.send_automated_course_deadline_reminders",
        "schedule": crontab(hour=6, minute=30),  # every day at 06:30 UTC
    },

    # ── Ops / SRE synthetic probes and maintenance ─────────────────────────
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

    # ── Progress / certifications ──────────────────────────────────────────
    "check-certification-expiry-daily": {
        "task": "progress.check_certification_expiry_and_autorenew",
        "schedule": crontab(hour=7, minute=0),  # every day at 07:00 UTC
    },

    # ── Gamification: streaks and leaderboards ─────────────────────────────
    # TASK-016 — Process streak breaks and freeze resets — daily at 00:05 UTC.
    "process-daily-streaks": {
        "task": "progress.process_daily_streaks",
        "schedule": crontab(hour=0, minute=5),
    },
    # Compute leaderboard rankings — every 15 minutes.
    "compute-leaderboard-snapshots": {
        "task": "progress.compute_leaderboard_snapshots",
        "schedule": crontab(minute="*/15"),
    },
    # TASK-016 — 10-tier League Leaderboards: weekly reset Mondays 00:00 UTC.
    "progress-close-league-week-weekly": {
        "task": "progress.close_league_week",
        "schedule": crontab(hour=0, minute=0, day_of_week="mon"),
    },

    # ── TASK-053 — Custom Report Builder ──────────────────────────────────
    "report-builder-run-scheduled-reports-hourly": {
        "task": "reports_builder.run_scheduled_reports",
        "schedule": crontab(minute=0),  # top of every hour
    },

    # ── Billing ───────────────────────────────────────────────────────────
    # Flag subscriptions past_due for >7 days — daily at 08:00 UTC.
    "billing-check-past-due-daily": {
        "task": "billing.check_past_due_subscriptions",
        "schedule": crontab(hour=8, minute=0),
    },
    # Clean up webhook events older than 90 days — weekly Saturday 03:00 UTC.
    "billing-cleanup-webhook-events-weekly": {
        "task": "billing.cleanup_stale_webhook_events",
        "schedule": crontab(hour=3, minute=0, day_of_week=6),
    },

    # ── Integrations ──────────────────────────────────────────────────────
    # Chat: prune terminal delivery rows older than 30 days — daily 02:00 UTC.
    "prune-chat-deliveries-daily": {
        "task": "integrations_chat.prune_chat_deliveries",
        "schedule": crontab(hour=2, minute=0),
    },
    # Calendar: push LMS deadlines to Google/Outlook — every 15 min.
    "sync-all-calendar-connections": {
        "task": "integrations_calendar.sync_all_calendar_connections",
        "schedule": crontab(minute="*/15"),
    },

    # ── Notification archival — 90-day TTL ────────────────────────────────
    # Archive notifications older than 90 days daily at 03:00 UTC.
    # Archived rows are hidden from the active manager but preserved for audit.
    "notifications-archive-old-daily": {
        "task": "notifications.archive_old_notifications",
        "schedule": crontab(hour=3, minute=0),  # daily 03:00 UTC
    },
    # Hard-delete notifications that have been archived for 30+ days
    # (120-day total lifecycle: 90 days active + 30 days archived grace period).
    # Runs weekly on Sundays at 04:00 UTC to minimise DB load on weekdays.
    "notifications-delete-archived-weekly": {
        "task": "notifications.delete_archived_notifications",
        "schedule": crontab(hour=4, minute=0, day_of_week="sun"),  # weekly Sun 04:00 UTC
    },

    # ── TASK-059 — AI Chatbot Tutor ───────────────────────────────────────
    # Purge ChatQuery rows older than 30 days — daily 01:00 UTC.
    "chatbot-purge-old-chat-queries-daily": {
        "task": "chatbot.purge_old_chat_queries",
        "schedule": crontab(hour=1, minute=0),  # daily 01:00 UTC
    },
}
