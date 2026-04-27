import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("tenants", "0022_auditlog_chat_actions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatIntegration",
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
                ("provider", models.CharField(
                    choices=[("slack", "Slack"), ("teams", "Microsoft Teams")],
                    max_length=20,
                )),
                ("display_name", models.CharField(max_length=255)),
                ("webhook_url_encrypted", models.TextField(
                    help_text="Fernet-encrypted webhook URL. Never log or return in full."
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("last_delivery_at", models.DateTimeField(blank=True, null=True)),
                ("last_delivery_status", models.CharField(blank=True, default="", max_length=20)),
                ("error", models.TextField(blank=True, default="")),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chat_integrations",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_chat_integrations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "integrations_chat_integration",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ChatRoutingRule",
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
                ("notification_type", models.CharField(
                    choices=[
                        ("COURSE_ASSIGNED", "Course Assigned"),
                        ("ASSIGNMENT_DUE", "Assignment Due"),
                        ("QUIZ_SUBMISSION", "Quiz Submission"),
                        ("CERTIFICATION_EXPIRING", "Certification Expiring"),
                        ("REPORT_GENERATED", "Report Generated"),
                        ("REMINDER", "Reminder"),
                        ("ANNOUNCEMENT", "Announcement"),
                        ("SYSTEM", "System"),
                    ],
                    max_length=30,
                )),
                ("role_filter", models.CharField(
                    blank=True,
                    choices=[
                        ("TEACHER", "Teacher"),
                        ("HOD", "Head of Department"),
                        ("IB_COORDINATOR", "IB Coordinator"),
                        ("SCHOOL_ADMIN", "School Admin"),
                    ],
                    max_length=30,
                    null=True,
                )),
                ("enabled", models.BooleanField(default=True)),
                (
                    "integration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="routing_rules",
                        to="integrations_chat.chatintegration",
                    ),
                ),
            ],
            options={
                "db_table": "integrations_chat_routing_rule",
                "ordering": ["notification_type"],
            },
        ),
        migrations.CreateModel(
            name="ChatDelivery",
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
                ("notification_id", models.UUIDField(db_index=True)),
                ("notification_type", models.CharField(blank=True, default="", max_length=30)),
                ("payload_json", models.JSONField(default=dict)),
                ("status", models.CharField(
                    choices=[
                        ("pending", "Pending"),
                        ("sent", "Sent"),
                        ("failed", "Failed (retrying)"),
                        ("dlq", "Dead Letter Queue"),
                    ],
                    db_index=True,
                    default="pending",
                    max_length=10,
                )),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, default="", max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "integration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deliveries",
                        to="integrations_chat.chatintegration",
                    ),
                ),
            ],
            options={
                "db_table": "integrations_chat_delivery",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="chatintegration",
            index=models.Index(
                fields=["tenant", "is_active"],
                name="chat_int_tenant_active_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="chatdelivery",
            index=models.Index(
                fields=["integration", "status"],
                name="chat_del_int_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="chatdelivery",
            index=models.Index(
                fields=["created_at", "status"],
                name="chat_del_created_status_idx",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="chatroutingrule",
            unique_together={("integration", "notification_type", "role_filter")},
        ),
        migrations.AlterUniqueTogether(
            name="chatdelivery",
            unique_together={("integration", "notification_id")},
        ),
    ]
