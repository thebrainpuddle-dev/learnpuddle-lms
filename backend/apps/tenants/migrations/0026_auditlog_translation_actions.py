"""Migration 0026 — TASK-058 AuditLog translation actions.

Adds the following action codes to AuditLog.ACTION_CHOICES:
  * TRANSLATION_STARTED
  * TRANSLATION_FINISHED
  * TRANSLATION_FAILED
  * TRANSLATION_PURGED

NB: The task spec filed this as migration 0025 but 0025 is taken by the
Tenant.default_language addition; this ships as 0026.
"""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0025_tenant_default_language"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(
                max_length=30,
                choices=[
                    ("CREATE", "Create"),
                    ("UPDATE", "Update"),
                    ("DELETE", "Delete"),
                    ("LOGIN", "Login"),
                    ("LOGOUT", "Logout"),
                    ("PUBLISH", "Publish"),
                    ("UNPUBLISH", "Unpublish"),
                    ("DEACTIVATE", "Deactivate"),
                    ("ACTIVATE", "Activate"),
                    ("PASSWORD_RESET", "Password Reset"),
                    ("SETTINGS_CHANGE", "Settings Change"),
                    ("IMPORT", "Bulk Import"),
                    ("RUN_REPORT", "Run Report"),
                    ("EXPORT_REPORT", "Export Report"),
                    ("EXPORT_SCORM", "Export SCORM"),
                    ("IMPORT_SCORM", "Import SCORM"),
                    ("CHAT_INTEGRATION_CREATED", "Chat Integration Created"),
                    ("CHAT_INTEGRATION_DELETED", "Chat Integration Deleted"),
                    ("CHAT_DELIVERY_FAILED", "Chat Delivery Failed (DLQ)"),
                    ("CONNECT_CALENDAR", "Calendar Connected"),
                    ("DISCONNECT_CALENDAR", "Calendar Disconnected"),
                    ("SYNC_CALENDAR_ERROR", "Calendar Sync Error"),
                    # TASK-058 — Auto-Translation Service audit actions
                    ("TRANSLATION_STARTED", "Translation Started"),
                    ("TRANSLATION_FINISHED", "Translation Finished"),
                    ("TRANSLATION_FAILED", "Translation Failed"),
                    ("TRANSLATION_PURGED", "Translation Purged"),
                ],
            ),
        ),
    ]
