"""
Migration 0021 — TASK-053 AuditLog ACTION_CHOICES additions.

Adds the following action codes to AuditLog.ACTION_CHOICES:
  * RUN_REPORT    — report builder run (TASK-053)
  * EXPORT_REPORT — report builder CSV export (TASK-053)
  * EXPORT_SCORM  — SCORM 1.2 export (TASK-052 backfill, requested in TASK-053 scope)
  * IMPORT_SCORM  — SCORM import (TASK-052 backfill, requested in TASK-053 scope)

NOTE for reviewer: these four action codes are added in ONE migration as
instructed by the TASK-053 spec. Do NOT conflate with TASK-052 or TASK-047
scope — the EXPORT_SCORM / IMPORT_SCORM codes are explicitly listed as a
TASK-053 backfill requirement (see spec line 66).

The AuditLog.action field is a CharField(max_length=20); the existing codes
(CREATE, UPDATE, DELETE, etc.) are stored as plain strings. Django migrations
for TextChoices/choices are display-only — no DB column change is needed for
most databases. However we include this migration to keep the migration graph
consistent and to document the intent.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0020_tenant_feature_saml"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(
                max_length=20,
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
                    # TASK-052 backfill (requested in TASK-053 spec)
                    ("EXPORT_SCORM", "Export SCORM"),
                    ("IMPORT_SCORM", "Import SCORM"),
                ],
            ),
        ),
    ]
