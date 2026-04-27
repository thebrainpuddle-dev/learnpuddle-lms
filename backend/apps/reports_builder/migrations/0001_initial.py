"""
Initial migration for apps/reports_builder (TASK-053).

Creates:
  * report_definitions
  * report_schedules
  * report_runs

All three tables have tenant FK and use TenantManager at the ORM layer.
ReportRun has its own tenant FK (belt-and-braces — spec requirement).
"""

import uuid
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("tenants", "0021_auditlog_action_choices_task053"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ReportDefinition",
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
                ("name", models.CharField(max_length=300)),
                ("description", models.TextField(blank=True, default="")),
                (
                    "data_source",
                    models.CharField(
                        choices=[
                            ("courses", "Courses"),
                            ("teacher_progress", "Teacher Progress"),
                            ("assignments", "Assignments"),
                            ("quiz_attempts", "Quiz Attempts"),
                            ("gamification", "XP / Gamification"),
                            ("certifications", "Certifications"),
                        ],
                        max_length=50,
                    ),
                ),
                ("filters_json", models.JSONField(blank=True, default=list)),
                ("group_by_json", models.JSONField(blank=True, default=list)),
                ("aggregates_json", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_soft_deleted", models.BooleanField(db_index=True, default=False)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_reports",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="report_definitions",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "report_definitions",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="reportdefinition",
            index=models.Index(
                fields=["tenant", "is_soft_deleted"],
                name="report_def_tenant_deleted_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="reportdefinition",
            index=models.Index(
                fields=["tenant", "data_source"],
                name="report_def_tenant_source_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="reportdefinition",
            index=models.Index(
                fields=["created_by"],
                name="report_def_created_by_idx",
            ),
        ),
        migrations.CreateModel(
            name="ReportSchedule",
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
                    "cadence",
                    models.CharField(
                        choices=[
                            ("daily", "Daily"),
                            ("weekly", "Weekly"),
                            ("monthly", "Monthly"),
                        ],
                        max_length=10,
                    ),
                ),
                (
                    "run_at_hour",
                    models.PositiveSmallIntegerField(
                        default=6, help_text="UTC hour (0\u201323) to run"
                    ),
                ),
                (
                    "run_at_day_of_week",
                    models.PositiveSmallIntegerField(
                        blank=True, help_text="0=Mon \u2026 6=Sun", null=True
                    ),
                ),
                (
                    "run_at_day_of_month",
                    models.PositiveSmallIntegerField(
                        blank=True, help_text="1\u201328", null=True
                    ),
                ),
                (
                    "recipients_json",
                    models.JSONField(
                        default=list,
                        help_text="Array of tenant user email strings",
                    ),
                ),
                ("enabled", models.BooleanField(default=True)),
                ("last_run_at", models.DateTimeField(blank=True, null=True)),
                (
                    "last_run_status",
                    models.CharField(
                        choices=[
                            ("ok", "OK"),
                            ("error", "Error"),
                            ("never_run", "Never Run"),
                        ],
                        default="never_run",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "definition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="schedules",
                        to="reports_builder.reportdefinition",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="report_schedules",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "report_schedules",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="reportschedule",
            index=models.Index(
                fields=["tenant", "enabled"],
                name="report_sched_tenant_enabled_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="reportschedule",
            index=models.Index(
                fields=["definition"],
                name="report_sched_definition_idx",
            ),
        ),
        migrations.CreateModel(
            name="ReportRun",
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
                ("params_snapshot_json", models.JSONField(default=dict)),
                (
                    "started_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("row_count", models.IntegerField(default=0)),
                ("artifact_path", models.TextField(blank=True, default="")),
                ("artifact_sha256", models.CharField(blank=True, default="", max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("success", "Success"),
                            ("error", "Error"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("error", models.TextField(blank=True, default="")),
                (
                    "definition",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="runs",
                        to="reports_builder.reportdefinition",
                    ),
                ),
                (
                    "run_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="report_runs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="report_runs",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "report_runs",
                "ordering": ["-started_at"],
            },
        ),
        migrations.AddIndex(
            model_name="reportrun",
            index=models.Index(
                fields=["tenant", "status"],
                name="report_run_tenant_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="reportrun",
            index=models.Index(
                fields=["tenant", "definition", "started_at"],
                name="report_run_tenant_def_started_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="reportrun",
            index=models.Index(
                fields=["run_by"],
                name="report_run_run_by_idx",
            ),
        ),
    ]
