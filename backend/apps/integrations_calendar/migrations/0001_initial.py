"""
Migration 0001 — Initial schema for integrations_calendar.

Tables:
  integrations_calendar_connection   — CalendarConnection
  integrations_calendar_synced_event — CalendarSyncedEvent
  integrations_calendar_ical_token   — ICalToken

Hand-written from models.py field definitions (docker not available at
migration generation time — to be verified by `python manage.py migrate`).
"""

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("tenants", "0023_auditlog_calendar_actions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ------------------------------------------------------------------
        # CalendarConnection
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="CalendarConnection",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "provider",
                    models.CharField(
                        max_length=20,
                        choices=[
                            ("google", "Google Calendar"),
                            ("outlook", "Outlook Calendar"),
                        ],
                    ),
                ),
                (
                    "provider_user_id",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                (
                    "access_token_encrypted",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Fernet-encrypted access token. Never log or return in full.",
                    ),
                ),
                (
                    "refresh_token_encrypted",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Fernet-encrypted refresh token. Never log or return in full.",
                    ),
                ),
                ("scopes", models.TextField(blank=True, default="")),
                (
                    "target_calendar_id",
                    models.CharField(blank=True, default="", max_length=500),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("expired", "Expired (token needs refresh)"),
                            ("revoked", "Revoked"),
                        ],
                        db_index=True,
                        default="active",
                        max_length=10,
                    ),
                ),
                ("error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_synced_at", models.DateTimeField(blank=True, null=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="calendar_connections",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="calendar_connections",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "integrations_calendar_connection",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="calendarconnection",
            constraint=models.UniqueConstraint(
                fields=["user", "provider"],
                name="unique_user_provider",
            ),
        ),
        migrations.AddIndex(
            model_name="calendarconnection",
            index=models.Index(
                fields=["tenant", "status"],
                name="cal_conn_tenant_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="calendarconnection",
            index=models.Index(
                fields=["user", "provider"],
                name="cal_conn_user_provider_idx",
            ),
        ),
        # ------------------------------------------------------------------
        # CalendarSyncedEvent
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="CalendarSyncedEvent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "source_type",
                    models.CharField(
                        max_length=20,
                        choices=[
                            ("deadline", "Enrollment Deadline"),
                            ("assignment", "Assignment Due Date"),
                            ("quiz", "Quiz Deadline"),
                            ("certification", "Certification Expiry"),
                        ],
                    ),
                ),
                ("source_id", models.CharField(max_length=255)),
                (
                    "provider_event_id",
                    models.CharField(blank=True, default="", max_length=500),
                ),
                (
                    "title_hash",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                (
                    "last_pushed_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                (
                    "connection",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="synced_events",
                        to="integrations_calendar.calendarconnection",
                    ),
                ),
            ],
            options={
                "db_table": "integrations_calendar_synced_event",
            },
        ),
        migrations.AddConstraint(
            model_name="calendarsyncedevent",
            constraint=models.UniqueConstraint(
                fields=["connection", "source_type", "source_id"],
                name="unique_connection_source",
            ),
        ),
        migrations.AddIndex(
            model_name="calendarsyncedevent",
            index=models.Index(
                fields=["connection", "source_type"],
                name="cal_event_conn_type_idx",
            ),
        ),
        # ------------------------------------------------------------------
        # ICalToken
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="ICalToken",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ical_tokens",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "integrations_calendar_ical_token",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="icaltoken",
            index=models.Index(
                fields=["user", "revoked_at"],
                name="ical_token_user_revoked_idx",
            ),
        ),
    ]
