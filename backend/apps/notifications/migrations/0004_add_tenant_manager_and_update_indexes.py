# Migration: Add tenant-scoped indexes to Notification for multi-tenant query performance.
#
# The old indexes (teacher, is_read), (teacher, -created_at), (teacher, is_actionable, is_read)
# were not prefixed with tenant, causing full-tenant scans when filtering notifications across
# a multi-tenant dataset.  The new indexes prefix all lookups with tenant_id so the query
# planner can use an index-range scan restricted to a single tenant.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0003_rename_notificatio_teacher_action_idx_notificatio_teacher_d92bc4_idx'),
    ]

    operations = [
        # ── Remove old non-tenant-prefixed indexes ──────────────────────────
        migrations.RemoveIndex(
            model_name='notification',
            name='notificatio_teacher_c710d0_idx',       # (teacher, is_read)
        ),
        migrations.RemoveIndex(
            model_name='notification',
            name='notificatio_teacher_20d708_idx',       # (teacher, -created_at)
        ),
        migrations.RemoveIndex(
            model_name='notification',
            name='notificatio_teacher_d92bc4_idx',       # (teacher, is_actionable, is_read)
        ),

        # ── Add tenant-prefixed replacements ────────────────────────────────
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(
                fields=['tenant', 'teacher', 'is_read'],
                name='notif_tenant_teacher_read_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(
                fields=['tenant', 'teacher', '-created_at'],
                name='notif_tenant_teacher_created_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(
                fields=['tenant', 'teacher', 'is_actionable', 'is_read'],
                name='notif_tenant_teacher_action_read_idx',
            ),
        ),
    ]
