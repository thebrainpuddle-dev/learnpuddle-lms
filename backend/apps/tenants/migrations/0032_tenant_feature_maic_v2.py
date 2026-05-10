"""Add Tenant.feature_maic_v2 — per-tenant access gate for the MAIC v2 stack.

Phase 8 / MAIC-800. Additive, reversible. Does NOT modify any other field
or index — leaves repo migration drift (autodetector wanted to rename
several indexes + alter unrelated fields) for a separate cleanup migration
so this one can be reverted cleanly.

Default is False so no existing tenant gets V2 access automatically.
Production gate is the global `MAIC_V2_ENABLED` env var (deploy-level
kill-switch); this field is the per-tenant access gate inside the gate.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0031_auditlog_course_gen_flagged"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="feature_maic_v2",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Enable MAIC v2 — the rebuilt multi-agent classroom + PBL "
                    "stack (Phases 0–7). Independent of feature_maic; both can "
                    "be on during rollout. Production gate is the global "
                    "MAIC_V2_ENABLED env var (deploy kill-switch); this field "
                    "is the per-tenant access gate."
                ),
            ),
        ),
    ]
