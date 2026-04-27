"""
Migration 0022 — TASK-055 AuditLog ACTION_CHOICES additions.

Adds the following action codes to AuditLog.ACTION_CHOICES:
  * CHAT_INTEGRATION_CREATED — admin created a Slack/Teams integration
  * CHAT_INTEGRATION_DELETED — admin soft-deleted an integration
  * CHAT_DELIVERY_FAILED     — delivery reached DLQ after max retries
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0021_auditlog_action_choices_task053"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(
                max_length=30,  # extend to 30 to fit CHAT_INTEGRATION_CREATED
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
                    # TASK-053 additions
                    ("RUN_REPORT", "Run Report"),
                    ("EXPORT_REPORT", "Export Report"),
                    # TASK-052 backfill
                    ("EXPORT_SCORM", "Export SCORM"),
                    ("IMPORT_SCORM", "Import SCORM"),
                    # TASK-055 — Chat integration audit actions
                    ("CHAT_INTEGRATION_CREATED", "Chat Integration Created"),
                    ("CHAT_INTEGRATION_DELETED", "Chat Integration Deleted"),
                    ("CHAT_DELIVERY_FAILED", "Chat Delivery Failed (DLQ)"),
                ],
            ),
        ),
    ]
