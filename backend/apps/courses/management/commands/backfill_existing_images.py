"""Backfill images on already-generated MAIC classrooms.

Use case: before the image_provider default was flipped from 'disabled'
to 'pollinations', classroom scene-content was generated with empty
image src AND `meta.imageProviderDisabled=true` stamped on every image
element. The frontend renders those as "AI images disabled" placeholders
forever. This command:

1. Scrubs `meta.imageProviderDisabled` from existing image elements.
2. Populates empty `src` via `fetch_scene_image(element['content'])`
   using the tenant's current image_provider config.
3. Synthesizes a new image element when a slide has zero image elements
   at all — keyword derived from slide title + scene title.

Idempotent: safe to re-run. A fully-populated classroom is a no-op.

Usage:
    python manage.py backfill_existing_images --tenant keystone [--dry-run] [--only-disabled]
"""

from __future__ import annotations

import time
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.courses.image_service import fetch_scene_image
from apps.courses.maic_models import MAICClassroom
from apps.tenants.models import Tenant


SLEEP_BETWEEN_IMAGES_SEC = 0.3
"""Rate-limit throttle between image fetches to stay under free-tier
quotas (Pollinations in particular)."""


class Command(BaseCommand):
    help = (
        "Backfill images on already-generated MAIC classrooms: strip "
        "imageProviderDisabled flags, populate empty src URLs, and "
        "synthesize an image element on slides that have none."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--tenant",
            required=True,
            help="Tenant subdomain to scope the backfill to (e.g. 'keystone').",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Log intended changes without saving.",
        )
        parser.add_argument(
            "--only-disabled",
            action="store_true",
            help=(
                "Only process classrooms that have at least one "
                "imageProviderDisabled flag (skips classrooms that look "
                "correct already)."
            ),
        )
        parser.add_argument(
            "--classroom-id",
            default=None,
            help="Optional: restrict to a single classroom UUID for targeted repair.",
        )

    def handle(self, *args, **opts) -> None:
        subdomain = opts["tenant"]
        dry_run = bool(opts["dry_run"])
        only_disabled = bool(opts["only_disabled"])
        single_id = opts.get("classroom_id")

        try:
            tenant = Tenant.objects.get(subdomain=subdomain)
        except Tenant.DoesNotExist as e:
            raise CommandError(f"Tenant with subdomain={subdomain!r} not found") from e

        qs = MAICClassroom.objects.filter(tenant=tenant).exclude(status="ARCHIVED")
        if single_id:
            qs = qs.filter(pk=single_id)
        total = qs.count()

        self.stdout.write(
            f"Backfilling images for tenant={subdomain!r} "
            f"(classrooms={total}, dry_run={dry_run}, only_disabled={only_disabled})"
        )

        touched = 0
        skipped = 0
        errors = 0

        for cls in qs.iterator():
            try:
                result = self._backfill_classroom(cls, dry_run=dry_run, only_disabled=only_disabled)
            except Exception as exc:  # noqa: BLE001 — one bad classroom mustn't abort the batch
                errors += 1
                self.stderr.write(
                    self.style.ERROR(
                        f"  ERROR classroom={cls.id} title={cls.title!r}: {exc}"
                    )
                )
                continue

            if result is None:
                skipped += 1
                continue

            touched += 1
            stamp = " (DRY RUN)" if dry_run else ""
            self.stdout.write(
                f"  ok {cls.id} {cls.title!r}{stamp} - "
                f"slides_changed={result['slides_changed']} "
                f"images_fetched={result['images_fetched']} "
                f"images_synthesized={result['images_synthesized']} "
                f"flags_stripped={result['flags_stripped']}"
            )

        self.stdout.write(self.style.SUCCESS(
            f"Done. touched={touched} skipped={skipped} errors={errors} total={total}"
        ))

    # ------------------------------------------------------------------

    def _backfill_classroom(
        self,
        classroom: MAICClassroom,
        *,
        dry_run: bool,
        only_disabled: bool,
    ) -> dict[str, int] | None:
        """Mutate classroom.content in place; save inside an atomic
        transaction. Returns a stats dict if any change was made, else
        None when skipped."""
        content = classroom.content or {}
        slides = content.get("slides") or []
        if not slides:
            return None

        # Early-out for --only-disabled: skip if nothing has the flag.
        if only_disabled:
            has_flag = any(
                isinstance(el, dict)
                and el.get("type") == "image"
                and (el.get("meta") or {}).get("imageProviderDisabled")
                for slide in slides
                for el in (slide.get("elements") or [])
            )
            if not has_flag:
                return None

        stats = {
            "slides_changed": 0,
            "images_fetched": 0,
            "images_synthesized": 0,
            "flags_stripped": 0,
        }
        scene_title_by_slide = self._scene_title_lookup(content)

        for slide_idx, slide in enumerate(slides):
            slide_changed = False
            elements = slide.get("elements") or []
            image_elements = [
                el for el in elements
                if isinstance(el, dict) and el.get("type") == "image"
            ]

            # Synthesize an image element when the slide has none.
            if not image_elements:
                scene_title = scene_title_by_slide.get(slide.get("id", ""), "")
                synthesized = self._make_image_element(
                    slide=slide,
                    slide_idx=slide_idx,
                    scene_title=scene_title,
                )
                elements.append(synthesized)
                slide["elements"] = elements
                image_elements = [synthesized]
                stats["images_synthesized"] += 1
                slide_changed = True

            # Strip the disabled flag + populate empty src.
            for el in image_elements:
                meta = el.get("meta") or {}
                if meta.get("imageProviderDisabled"):
                    meta.pop("imageProviderDisabled", None)
                    if not meta:
                        el.pop("meta", None)
                    else:
                        el["meta"] = meta
                    stats["flags_stripped"] += 1
                    slide_changed = True

                if not el.get("src"):
                    keyword = str(el.get("content") or "").strip()
                    if not keyword:
                        keyword = slide.get("title") or classroom.title or "educational illustration"
                        el["content"] = f"Educational illustration: {keyword[:120]}"
                    if dry_run:
                        # Don't hit the network on dry-run. Pretend we fetched.
                        stats["images_fetched"] += 1
                        slide_changed = True
                        continue
                    try:
                        url = fetch_scene_image(keyword)
                        if url:
                            el["src"] = url
                            stats["images_fetched"] += 1
                            slide_changed = True
                    except Exception as exc:  # noqa: BLE001 — one bad fetch mustn't abort the slide
                        self.stderr.write(
                            f"    image fetch failed slide={slide.get('id')} keyword={keyword!r}: {exc}"
                        )
                    # Throttle so the provider's free tier isn't saturated.
                    if not dry_run:
                        time.sleep(SLEEP_BETWEEN_IMAGES_SEC)

            if slide_changed:
                stats["slides_changed"] += 1

        # Silence no-op when nothing actually changed.
        if stats["slides_changed"] == 0:
            return None

        if dry_run:
            return stats

        # Persist. One atomic save per classroom keeps failures isolated.
        with transaction.atomic():
            classroom.content = content
            classroom.save(update_fields=["content", "updated_at"])
        return stats

    # ------------------------------------------------------------------

    def _scene_title_lookup(self, content: dict[str, Any]) -> dict[str, str]:
        """Map slide_id -> owning scene title so synthesized image
        keywords can borrow semantic context from the scene."""
        lookup: dict[str, str] = {}
        for scene in (content.get("scenes") or []):
            if not isinstance(scene, dict):
                continue
            title = str(scene.get("title") or "").strip()
            for slide in (scene.get("slides") or []):
                if isinstance(slide, dict):
                    sid = slide.get("id")
                    if sid and title:
                        lookup[sid] = title
        return lookup

    def _make_image_element(
        self,
        *,
        slide: dict,
        slide_idx: int,
        scene_title: str,
    ) -> dict:
        """Create an image element positioned on the right half of the
        slide - non-destructive to any text elements already laid out on
        the left. Keyword derives from slide title + scene title."""
        slide_title = str(slide.get("title") or "").strip()
        parts = [p for p in [slide_title, scene_title] if p]
        keyword_core = " - ".join(parts) or "educational illustration"
        keyword = f"Educational illustration: {keyword_core[:120]}"
        return {
            "type": "image",
            "id": f"el-s{slide_idx + 1}-img-backfill",
            "x": 460, "y": 90, "width": 300, "height": 240,
            "content": keyword,
            "src": "",
        }
