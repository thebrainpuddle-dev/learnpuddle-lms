"""
Migration 0024 — TASK-020 Education vs Corporate mode.

Additive migration: adds two new fields to Tenant with safe defaults.
- `mode` CharField (choices: education|corporate, default='education')
- `mode_label_overrides` JSONField (default=dict, blank=True)

No data backfill required: existing rows receive default values, which
preserves current behaviour ("education" terminology).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0023_auditlog_calendar_actions"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="mode",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("education", "Education"),
                    ("corporate", "Corporate"),
                ],
                default="education",
                help_text=(
                    "Display-terminology mode. 'education' uses Teacher/"
                    "Course/Badge; 'corporate' uses Employee/Training "
                    "Program/Achievement. Purely a display switch — no "
                    "stored gamification data is re-keyed."
                ),
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="mode_label_overrides",
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text=(
                    "Per-tenant overrides layered on top of "
                    "MODE_LABEL_DEFAULTS for the active mode, e.g., "
                    "{'course': 'Masterclass'}."
                ),
            ),
        ),
    ]
