"""Migration 0028 — TASK-060 AuditLog course-generator audit actions.

Adds the following action codes:
  * COURSE_GENERATION_STARTED   (26 chars)
  * COURSE_GENERATION_SUCCEEDED (27 chars)
  * COURSE_GENERATION_FAILED    (24 chars)
  * COURSE_MATERIALISED         (19 chars)
  * COURSE_GENERATION_PURGED    (24 chars)

All fit within the existing max_length=30 on the action field.
"""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0027_auditlog_semantic_actions"),
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
                    ("SEMANTIC_REINDEX_STARTED", "Semantic Reindex Started"),
                    ("SEMANTIC_REINDEX_FINISHED", "Semantic Reindex Finished"),
                    ("SEMANTIC_REINDEX_FAILED", "Semantic Reindex Failed"),
                    # TASK-060 — AI Course Generator audit actions
                    ("COURSE_GENERATION_STARTED", "Course Generation Started"),
                    ("COURSE_GENERATION_SUCCEEDED", "Course Generation Succeeded"),
                    ("COURSE_GENERATION_FAILED", "Course Generation Failed"),
                    ("COURSE_MATERIALISED", "Course Materialised"),
                    ("COURSE_GENERATION_PURGED", "Course Generation Purged"),
                ],
            ),
        ),
    ]
