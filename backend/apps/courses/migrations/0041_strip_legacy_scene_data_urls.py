"""Data migration: strip `data:` URLs from scene content as well.

Follow-up to 0040 which only walked `content.slides[*].elements[*].src`.
The classroom schema actually has a parallel structure at
`content.scenes[*].content.elements[*].src` (slide-like rendering inside
each scene's content blob). Legacy classrooms had ~1 MB data: URLs
embedded there too — ~5 MB per classroom across 5-10 scenes.

Idempotent (second run finds nothing).
"""

from django.db import migrations


def _strip(classroom) -> bool:
    content = classroom.content or {}
    changed = False

    def _walk_elements(elements):
        nonlocal changed
        if not isinstance(elements, list):
            return
        for el in elements:
            if not isinstance(el, dict):
                continue
            src = el.get("src")
            if isinstance(src, str) and src.startswith("data:"):
                el["src"] = ""
                changed = True

    # Covered by 0040 but harmless to re-sweep (idempotent).
    for slide in content.get("slides") or []:
        _walk_elements(slide.get("elements"))

    # New path 0040 missed: scene-nested elements.
    for scene in content.get("scenes") or []:
        scene_content = scene.get("content") or {}
        if isinstance(scene_content, dict):
            _walk_elements(scene_content.get("elements"))

    return changed


def strip_scene_data_urls(apps, schema_editor):
    MAICClassroom = apps.get_model("courses", "MAICClassroom")
    manager = MAICClassroom.all_objects if hasattr(MAICClassroom, "all_objects") else MAICClassroom.objects
    total, touched = 0, 0
    for classroom in manager.iterator(chunk_size=100):
        total += 1
        if _strip(classroom):
            classroom.save(update_fields=["content", "updated_at"])
            touched += 1
    print(f"\n[0041_strip_legacy_scene_data_urls] scanned={total} stripped={touched}")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0040_strip_legacy_data_url_images"),
    ]

    operations = [
        migrations.RunPython(strip_scene_data_urls, noop_reverse),
    ]
