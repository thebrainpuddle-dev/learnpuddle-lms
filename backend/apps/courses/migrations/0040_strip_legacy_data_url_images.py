"""Data migration: strip legacy `data:` URL images from MAICClassroom.content.

Context: SEC-P0-4 (2026-04-23) now blocks LLM-supplied `data:` URLs from
reaching `MAICClassroom.content.slides[*].elements[*].src` at both backend
ingress (`_fill_image_urls`) and frontend render (`SlideRenderer`). But
rows persisted BEFORE that guard can still contain huge base64 JPEGs
(~800 KB per image × 50 slides = 40 MB per classroom).

This migration walks every MAICClassroom and replaces any `data:` src with
an empty string. The frontend renderer falls through to its
"provider disabled" placeholder when src is empty — acceptable degrade
for legacy rows, and drops classroom size from tens of megabytes to
kilobytes so:
  - PATCH updates land under DATA_UPLOAD_MAX_MEMORY_SIZE (PERF-P0-3).
  - Detail responses when `?full=1` or status=READY don't megabyte-bloat
    every poll (PERF-P0-1).
  - JSONField TOAST rewrites on partial save finish in milliseconds.

Idempotent: running twice is a no-op (second pass finds no data: URLs).
"""

from django.db import migrations


def _strip_data_urls(classroom) -> bool:
    """Mutate classroom.content in place; return True if anything changed."""
    content = classroom.content or {}
    slides = content.get("slides") or []
    changed = False
    for slide in slides:
        for el in slide.get("elements") or []:
            src = el.get("src")
            if isinstance(src, str) and src.startswith("data:"):
                el["src"] = ""
                changed = True
    return changed


def strip_data_urls(apps, schema_editor):
    MAICClassroom = apps.get_model("courses", "MAICClassroom")
    total = MAICClassroom.all_objects.count() if hasattr(MAICClassroom, "all_objects") else MAICClassroom.objects.count()
    touched = 0
    # Use the unfiltered manager to sweep rows across every tenant.
    manager = MAICClassroom.all_objects if hasattr(MAICClassroom, "all_objects") else MAICClassroom.objects
    for classroom in manager.iterator(chunk_size=100):
        if _strip_data_urls(classroom):
            classroom.save(update_fields=["content", "updated_at"])
            touched += 1
    # Migration output surfaces in `manage.py migrate` logs.
    print(f"\n[0040_strip_legacy_data_url_images] scanned={total} stripped={touched}")


def noop_reverse(apps, schema_editor):
    """One-way data cleanup — can't restore base64 blobs from a backup here."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0039_maic_progress_heartbeat"),
    ]

    operations = [
        migrations.RunPython(strip_data_urls, noop_reverse),
    ]
