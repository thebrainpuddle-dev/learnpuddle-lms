"""
PERF-P0-4 — Normalize MAICClassroom.content into sharded JSONFields.

Adds three new JSONFields (content_scenes, content_agents, content_meta) that
split the formerly monolithic ``content`` blob so partial saves only rewrite
the changed segment rather than the entire TOAST blob.

The legacy ``content`` field is NOT dropped in this migration — it stays as a
fallback during the transition period. A follow-up migration will drop it once
the shards are verified in production.

Backfill strategy (RunPython):
    Walk every existing MAICClassroom row. For rows that have non-empty
    ``content``, extract the three sections:
        content["scenes"]       → content_scenes
        content["agents"]       → content_agents
        remainder (everything else, e.g. audioManifest) → content_meta

Reversible: the reverse func merges shards back into ``content``.
"""

from django.db import migrations, models


# ---------------------------------------------------------------------------
# Forward: populate shards from legacy content
# ---------------------------------------------------------------------------

def populate_shards(apps, schema_editor):
    MAICClassroom = apps.get_model("courses", "MAICClassroom")

    # Use the all_objects manager (bypasses TenantManager which requires
    # thread-local tenant to be set, which isn't available in migrations).
    manager = (
        MAICClassroom.all_objects
        if hasattr(MAICClassroom, "all_objects")
        else MAICClassroom.objects
    )

    total = 0
    backfilled = 0

    for classroom in manager.iterator(chunk_size=200):
        total += 1
        legacy = classroom.content
        if not legacy or not isinstance(legacy, dict):
            # Empty or non-dict content — nothing to backfill (already default).
            continue

        scenes = legacy.get("scenes")
        agents = legacy.get("agents")
        # Collect everything that is NOT scenes/agents into meta.
        meta = {k: v for k, v in legacy.items() if k not in ("scenes", "agents")}

        classroom.content_scenes = scenes if isinstance(scenes, list) else []
        classroom.content_agents = agents if isinstance(agents, list) else []
        classroom.content_meta = meta

        classroom.save(
            update_fields=["content_scenes", "content_agents", "content_meta"]
        )
        backfilled += 1

    print(
        f"\n[0043_classroom_sharded_content] "
        f"scanned={total} backfilled={backfilled}"
    )


# ---------------------------------------------------------------------------
# Reverse: merge shards back into legacy content
# ---------------------------------------------------------------------------

def depopulate_shards(apps, schema_editor):
    MAICClassroom = apps.get_model("courses", "MAICClassroom")

    manager = (
        MAICClassroom.all_objects
        if hasattr(MAICClassroom, "all_objects")
        else MAICClassroom.objects
    )

    total = 0
    restored = 0

    for classroom in manager.iterator(chunk_size=200):
        total += 1
        # Only act on rows where at least one shard was populated.
        if not (classroom.content_scenes or classroom.content_agents or classroom.content_meta):
            continue

        merged: dict = {}
        if classroom.content_agents:
            merged["agents"] = classroom.content_agents
        if classroom.content_scenes:
            merged["scenes"] = classroom.content_scenes
        if classroom.content_meta:
            merged.update(classroom.content_meta)

        classroom.content = merged
        classroom.content_scenes = []
        classroom.content_agents = []
        classroom.content_meta = {}
        classroom.save(
            update_fields=["content", "content_scenes", "content_agents", "content_meta"]
        )
        restored += 1

    print(
        f"\n[0043_classroom_sharded_content REVERSE] "
        f"scanned={total} restored={restored}"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0042_classroom_images_pending"),
    ]

    operations = [
        # ── Schema: add the three shard fields ──────────────────────────────
        migrations.AddField(
            model_name="maicclassroom",
            name="content_scenes",
            field=models.JSONField(
                default=list,
                blank=True,
                help_text=(
                    "PERF-P0-4 shard: scenes array "
                    "(slides, actions, image srcs, audio URLs)"
                ),
            ),
        ),
        migrations.AddField(
            model_name="maicclassroom",
            name="content_agents",
            field=models.JSONField(
                default=list,
                blank=True,
                help_text="PERF-P0-4 shard: agent profile list",
            ),
        ),
        migrations.AddField(
            model_name="maicclassroom",
            name="content_meta",
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text=(
                    "PERF-P0-4 shard: audioManifest + miscellaneous top-level keys"
                ),
            ),
        ),
        # ── Data: backfill shards from legacy content ────────────────────────
        migrations.RunPython(populate_shards, depopulate_shards),
    ]
