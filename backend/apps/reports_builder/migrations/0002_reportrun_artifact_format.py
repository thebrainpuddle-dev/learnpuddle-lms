"""
Migration 0002 — TASK-065: add artifact_format to ReportRun.

Adds ReportRun.artifact_format (CharField, max_length=4, default="csv") to track
whether a report run produced a CSV or XLSX artifact.  Existing rows default to
"csv" so the field is non-nullable with a safe default.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports_builder", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportrun",
            name="artifact_format",
            field=models.CharField(
                blank=True,
                choices=[("csv", "CSV"), ("xlsx", "Excel")],
                default="csv",
                max_length=4,
            ),
        ),
    ]
