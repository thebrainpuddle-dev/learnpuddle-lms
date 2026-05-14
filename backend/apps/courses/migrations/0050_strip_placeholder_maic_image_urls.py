"""Strip reserved/placeholder image URLs from sharded MAIC classroom content."""

from __future__ import annotations

from urllib.parse import urlparse

from django.db import migrations


PLACEHOLDER_IMAGE_HOSTS = {
    "example.com",
    "www.example.com",
    "example.org",
    "www.example.org",
    "example.net",
    "www.example.net",
    "placehold.co",
    "placeholder.com",
    "via.placeholder.com",
    "source.unsplash.com",
}

PLACEHOLDER_IMAGE_HOST_SUFFIXES = (
    ".example.com",
    ".example.org",
    ".example.net",
)


def _is_placeholder_host(host):
    value = (host or "").strip().lower().rstrip(".")
    return value in PLACEHOLDER_IMAGE_HOSTS or any(
        value.endswith(suffix) for suffix in PLACEHOLDER_IMAGE_HOST_SUFFIXES
    )


def _should_strip(src):
    value = str(src or "").strip()
    if not value or value.startswith("/media/"):
        return False
    parsed = urlparse(value)
    if not parsed.scheme:
        return False
    if parsed.scheme not in {"http", "https"}:
        return True
    return _is_placeholder_host(parsed.hostname)


def _scrub(payload):
    changed = False

    def walk(value):
        nonlocal changed
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, dict):
            return

        is_image_node = str(value.get("type") or "").lower() == "image"
        if "src" in value and _should_strip(value.get("src")):
            value["src"] = ""
            changed = True
        if is_image_node and "url" in value and _should_strip(value.get("url")):
            value["url"] = ""
            changed = True
        if is_image_node and "content" in value and _should_strip(value.get("content")):
            value["content"] = ""
            changed = True

        for child in value.values():
            walk(child)

    walk(payload)
    return changed


def strip_placeholder_maic_image_urls(apps, schema_editor):
    MAICClassroom = apps.get_model("courses", "MAICClassroom")
    manager = (
        MAICClassroom.all_objects
        if hasattr(MAICClassroom, "all_objects")
        else MAICClassroom.objects
    )

    total = 0
    touched = 0
    fields = (
        "content",
        "content_scenes",
        "content_meta",
        "content_image_tasks",
    )
    for classroom in manager.iterator(chunk_size=100):
        total += 1
        update_fields = []
        for field in fields:
            payload = getattr(classroom, field, None)
            if _scrub(payload):
                setattr(classroom, field, payload)
                update_fields.append(field)
        if update_fields:
            classroom.save(update_fields=update_fields + ["updated_at"])
            touched += 1
    print(f"\n[0050_strip_placeholder_maic_image_urls] scanned={total} scrubbed={touched}")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0049_tenantaiconfig_ollama_choice"),
    ]

    operations = [
        migrations.RunPython(strip_placeholder_maic_image_urls, noop_reverse),
    ]
