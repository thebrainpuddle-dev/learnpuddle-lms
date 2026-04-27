"""Migration 0027 — TASK-057 AuditLog semantic-search actions.

Adds the following action codes to AuditLog.ACTION_CHOICES:
  * SEMANTIC_REINDEX_STARTED
  * SEMANTIC_REINDEX_FINISHED
  * SEMANTIC_REINDEX_FAILED

The task spec called for this to land as 0023; that slot was taken by the
calendar-integrations migration (TASK-054). We bump to the next free
slot (0027) to keep migrations linear.

max_length=30 was already set by 0022_auditlog_chat_actions (TASK-055).
"""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0026_auditlog_translation_actions"),
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
                    ("TRANSLATION_STARTED", "Translation Started"),
                    ("TRANSLATION_FINISHED", "Translation Finished"),
                    ("TRANSLATION_FAILED", "Translation Failed"),
                    ("TRANSLATION_PURGED", "Translation Purged"),
                    # TASK-057 — Semantic search reindex audit actions
                    ("SEMANTIC_REINDEX_STARTED", "Semantic Reindex Started"),
                    ("SEMANTIC_REINDEX_FINISHED", "Semantic Reindex Finished"),
                    ("SEMANTIC_REINDEX_FAILED", "Semantic Reindex Failed"),
                ],
            ),
        ),
    ]
