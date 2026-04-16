"""Data migration: stamp an idle ``audioManifest`` onto every existing
MAICClassroom so the new manifest-aware code paths have a stable shape to
read from. Reversible — ``unstamp_manifest`` pops the key on rollback.
"""
from django.db import migrations


def stamp_manifest(apps, schema_editor):
    MAICClassroom = apps.get_model("courses", "MAICClassroom")
    for classroom in MAICClassroom.objects.iterator():
        content = classroom.content or {}
        if "audioManifest" not in content:
            content["audioManifest"] = {
                "status": "idle",
                "progress": 0,
                "totalActions": 0,
                "completedActions": 0,
                "failedAudioIds": [],
                "generatedAt": None,
            }
            classroom.content = content
            classroom.save(update_fields=["content"])


def unstamp_manifest(apps, schema_editor):
    MAICClassroom = apps.get_model("courses", "MAICClassroom")
    for classroom in MAICClassroom.objects.iterator():
        if classroom.content and "audioManifest" in classroom.content:
            del classroom.content["audioManifest"]
            classroom.save(update_fields=["content"])


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0034_maicclassroom_content"),
    ]

    operations = [
        migrations.RunPython(stamp_manifest, unstamp_manifest),
    ]
