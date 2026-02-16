# Initial migration for webhooks app

import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("tenants", "0004_tenant_sso_2fa_custom_domain"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── WebhookEndpoint ─────────────────────────────────────────────
        migrations.CreateModel(
            name="WebhookEndpoint",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(help_text="Friendly name for this webhook", max_length=200)),
                ("url", models.URLField(help_text="HTTPS URL to receive webhook payloads", max_length=500)),
                ("secret", models.CharField(help_text="Secret for HMAC signature verification", max_length=64)),
                ("events", models.JSONField(default=list, help_text="List of event types to subscribe to")),
                ("is_active", models.BooleanField(default=True)),
                ("total_deliveries", models.PositiveIntegerField(default=0)),
                ("successful_deliveries", models.PositiveIntegerField(default=0)),
                ("failed_deliveries", models.PositiveIntegerField(default=0)),
                ("last_triggered_at", models.DateTimeField(blank=True, null=True)),
                ("last_success_at", models.DateTimeField(blank=True, null=True)),
                ("last_failure_at", models.DateTimeField(blank=True, null=True)),
                ("last_failure_reason", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="webhook_endpoints", to="tenants.tenant")),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_webhooks", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "webhook_endpoints",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="webhookendpoint",
            index=models.Index(fields=["tenant", "is_active"], name="wh_tenant_active_idx"),
        ),

        # ── WebhookDelivery ─────────────────────────────────────────────
        migrations.CreateModel(
            name="WebhookDelivery",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("event_type", models.CharField(max_length=50)),
                ("event_id", models.UUIDField(default=uuid.uuid4)),
                ("payload", models.JSONField()),
                ("status", models.CharField(choices=[("pending", "Pending"), ("success", "Success"), ("failed", "Failed"), ("retrying", "Retrying")], default="pending", max_length=20)),
                ("attempt_count", models.PositiveSmallIntegerField(default=0)),
                ("max_attempts", models.PositiveSmallIntegerField(default=5)),
                ("response_status_code", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("response_body", models.TextField(blank=True, default="")),
                ("response_time_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("scheduled_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("next_retry_at", models.DateTimeField(blank=True, null=True)),
                ("endpoint", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="deliveries", to="webhooks.webhookendpoint")),
            ],
            options={
                "db_table": "webhook_deliveries",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="webhookdelivery",
            index=models.Index(fields=["endpoint", "status"], name="whd_endpoint_status_idx"),
        ),
        migrations.AddIndex(
            model_name="webhookdelivery",
            index=models.Index(fields=["status", "next_retry_at"], name="whd_status_retry_idx"),
        ),
        migrations.AddIndex(
            model_name="webhookdelivery",
            index=models.Index(fields=["event_type", "created_at"], name="whd_event_created_idx"),
        ),
    ]
