"""Migration 0031 — TASK-060 L4: Add COURSE_GENERATION_FLAGGED audit action.

Adds the following action code to AuditLog.ACTION_CHOICES:
  * COURSE_GENERATION_FLAGGED  (27 chars) — prompt-injection detected in source

This separates injection-flagging events from COURSE_GENERATION_STARTED so
that an auditor can filter flagged jobs via
``AuditLog.objects.filter(action="COURSE_GENERATION_FLAGGED")`` without
also pulling the start events.

Fits within the existing max_length=30 on the action field.
"""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0030_auditlog_translation_review_actions"),
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
                    # TASK-054 — Calendar integration audit actions
                    ("CONNECT_CALENDAR", "Calendar Connected"),
                    ("DISCONNECT_CALENDAR", "Calendar Disconnected"),
                    ("SYNC_CALENDAR_ERROR", "Calendar Sync Error"),
                    # TASK-058 — Auto-Translation Service audit actions
                    ("TRANSLATION_STARTED", "Translation Started"),
                    ("TRANSLATION_FINISHED", "Translation Finished"),
                    ("TRANSLATION_FAILED", "Translation Failed"),
                    ("TRANSLATION_PURGED", "Translation Purged"),
                    # TASK-057 — Semantic-search reindex audit actions
                    ("SEMANTIC_REINDEX_STARTED", "Semantic Reindex Started"),
                    ("SEMANTIC_REINDEX_FINISHED", "Semantic Reindex Finished"),
                    ("SEMANTIC_REINDEX_FAILED", "Semantic Reindex Failed"),
                    # TASK-060 — AI Course Generator audit actions
                    ("COURSE_GENERATION_STARTED", "Course Generation Started"),
                    ("COURSE_GENERATION_SUCCEEDED", "Course Generation Succeeded"),
                    ("COURSE_GENERATION_FAILED", "Course Generation Failed"),
                    ("COURSE_GENERATION_FLAGGED", "Course Generation Flagged"),
                    ("COURSE_MATERIALISED", "Course Materialised"),
                    ("COURSE_GENERATION_PURGED", "Course Generation Purged"),
                    # TASK-059 — AI Chatbot Tutor audit actions
                    ("CHAT_QUERY_ASKED", "Chat Query Asked"),
                    ("CHAT_QUERY_PURGED", "Chat Query Purged"),
                    # TASK-064b — Translation per-field review audit actions
                    ("TRANSLATION_FIELD_APPROVED", "Translation Field Approved"),
                    ("TRANSLATION_FIELD_REJECTED", "Translation Field Rejected"),
                    ("TRANSLATION_FIELD_EDITED", "Translation Field Edited"),
                    ("TRANSLATION_PUBLISHED", "Translation Published"),
                ],
            ),
        ),
    ]
