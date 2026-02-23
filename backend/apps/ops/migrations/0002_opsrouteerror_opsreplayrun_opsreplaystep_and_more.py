# Generated manually by Codex on 2026-02-23

import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ops", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OpsReplayRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("portal", models.CharField(choices=[("TENANT_ADMIN", "Tenant Admin"), ("TEACHER", "Teacher")], max_length=20)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("RUNNING", "Running"),
                            ("COMPLETED", "Completed"),
                            ("FAILED", "Failed"),
                            ("CANCELLED", "Cancelled"),
                        ],
                        db_index=True,
                        default="PENDING",
                        max_length=12,
                    ),
                ),
                ("priority", models.CharField(choices=[("NORMAL", "Normal"), ("HIGH", "High")], default="NORMAL", max_length=10)),
                ("dry_run", models.BooleanField(default=True)),
                ("requested_cases_json", models.JSONField(blank=True, default=list)),
                ("summary_json", models.JSONField(blank=True, default=dict)),
                ("incident_links_json", models.JSONField(blank=True, default=list)),
                ("started_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("ended_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ops_replay_runs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ops_replay_runs",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "ops_replay_runs",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["tenant", "created_at"], name="ops_replay__tenant__24f5f9_idx"),
                    models.Index(fields=["status", "created_at"], name="ops_replay__status_795cd6_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="OpsRouteError",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "portal",
                    models.CharField(
                        choices=[
                            ("SUPER_ADMIN", "Super Admin"),
                            ("TENANT_ADMIN", "Tenant Admin"),
                            ("TEACHER", "Teacher"),
                            ("UNKNOWN", "Unknown"),
                        ],
                        db_index=True,
                        default="UNKNOWN",
                        max_length=20,
                    ),
                ),
                ("tab_key", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("route_path", models.CharField(blank=True, default="", max_length=255)),
                ("component_name", models.CharField(blank=True, default="", max_length=128)),
                ("endpoint", models.CharField(db_index=True, max_length=255)),
                ("method", models.CharField(db_index=True, max_length=10)),
                ("status_code", models.PositiveSmallIntegerField(db_index=True)),
                ("fingerprint", models.CharField(max_length=255, unique=True)),
                ("first_seen_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("last_seen_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("last_request_id", models.CharField(blank=True, default="", max_length=64)),
                ("total_count", models.PositiveIntegerField(default=0)),
                ("count_1h", models.PositiveIntegerField(default=0)),
                ("count_24h", models.PositiveIntegerField(default=0)),
                ("sample_payload_json", models.JSONField(blank=True, default=dict)),
                ("sample_response_excerpt", models.TextField(blank=True, default="")),
                ("sample_error_message", models.TextField(blank=True, default="")),
                ("is_locked", models.BooleanField(db_index=True, default=False)),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "locked_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="locked_ops_route_errors",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ops_route_errors",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "ops_route_errors",
                "ordering": ["-last_seen_at"],
                "indexes": [
                    models.Index(fields=["tenant", "status_code", "last_seen_at"], name="ops_route__tenant__416fbe_idx"),
                    models.Index(fields=["portal", "tab_key", "status_code"], name="ops_route__portal_15c9b0_idx"),
                    models.Index(fields=["is_locked", "last_seen_at"], name="ops_route__is_lock_7164de_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="OpsReplayStep",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("case_id", models.CharField(max_length=128)),
                ("case_label", models.CharField(blank=True, default="", max_length=200)),
                ("endpoint", models.CharField(max_length=255)),
                ("method", models.CharField(default="GET", max_length=10)),
                ("request_payload_json", models.JSONField(blank=True, default=dict)),
                ("response_status", models.PositiveSmallIntegerField(blank=True, db_index=True, null=True)),
                ("response_excerpt", models.TextField(blank=True, default="")),
                ("latency_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("pass_fail", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "error_group",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="replay_steps",
                        to="ops.opsrouteerror",
                    ),
                ),
                (
                    "run",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="steps", to="ops.opsreplayrun"),
                ),
            ],
            options={
                "db_table": "ops_replay_steps",
                "ordering": ["created_at"],
                "indexes": [
                    models.Index(fields=["run", "created_at"], name="ops_replay__run_id_4f894f_idx"),
                    models.Index(fields=["case_id", "pass_fail"], name="ops_replay__case_id_caed20_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="OpsActionApproval",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "approval_status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("APPROVED", "Approved"),
                            ("REJECTED", "Rejected"),
                            ("AUTO_APPROVED", "Auto Approved"),
                        ],
                        db_index=True,
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("approval_note", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "action_log",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE, related_name="approval", to="ops.opsactionlog"
                    ),
                ),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="approved_ops_approvals",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="requested_ops_approvals",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "ops_action_approvals",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["approval_status", "created_at"], name="ops_action__approva_758d79_idx"),
                ],
            },
        ),
    ]
