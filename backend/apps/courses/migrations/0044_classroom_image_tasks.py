"""F2 (P0) — Per-element image task store on MAICClassroom.

Source: 2026-04-28 OpenMAIC deep-dive followups (F2).

Adds a new ``content_image_tasks`` JSONField shard keyed by a stable
per-element string (``"<scene_idx>:<slide_idx>:<element_idx>:<element_id>"``).
Status states: ``pending → generating → done | failed``.

Default ``{}`` so existing rows need no backfill — the global
``images_pending`` boolean (CG-P0-3) remains the legacy authority for
"any image still in flight" until F3 adopts the per-task store. Both
fields coexist; ``content_image_tasks`` is additive.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0043_classroom_sharded_content"),
    ]

    operations = [
        migrations.AddField(
            model_name="maicclassroom",
            name="content_image_tasks",
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text=(
                    "F2 (P0): per-element image generation task state, keyed "
                    "by ``<scene_idx>:<slide_idx>:<element_idx>:<element_id>``. "
                    "Status states: pending|generating|done|failed."
                ),
            ),
        ),
    ]
