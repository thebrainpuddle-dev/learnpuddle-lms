"""Safety helpers for MAIC-generated media references."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


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


def is_placeholder_image_host(host: str | None) -> bool:
    normalized = (host or "").strip().lower().rstrip(".")
    if not normalized:
        return False
    return (
        normalized in PLACEHOLDER_IMAGE_HOSTS
        or any(normalized.endswith(suffix) for suffix in PLACEHOLDER_IMAGE_HOST_SUFFIXES)
    )


def should_strip_generated_image_src(
    src: object,
    *,
    allow_bare_ids: bool = False,
) -> bool:
    """Return True when a generated image source is unsafe or placeholder-only.

    ``allow_bare_ids`` is used by the v2 materializer, where upstream may
    preserve source-image IDs such as ``img_1`` for a later resolver. The
    legacy scene-content service keeps the stricter behavior and strips bare
    strings so only real media paths or http(s) URLs leave that boundary.
    """

    value = str(src or "").strip()
    if not value:
        return False
    if value.startswith("/media/"):
        return False

    parsed = urlparse(value)
    if not parsed.scheme:
        return not allow_bare_ids
    if parsed.scheme not in {"http", "https"}:
        return True
    return is_placeholder_image_host(parsed.hostname)


def scrub_placeholder_image_srcs(payload: Any, *, allow_bare_ids: bool = True) -> bool:
    """Mutate a MAIC payload in-place, clearing placeholder image URLs.

    The walker is intentionally shape-tolerant because MAIC content exists in
    legacy monolithic blobs, sharded scene arrays, flat ``content_meta.slides``,
    and per-element task maps.
    """

    changed = False

    def walk(value: Any) -> None:
        nonlocal changed

        if isinstance(value, list):
            for item in value:
                walk(item)
            return

        if not isinstance(value, dict):
            return

        node_type = str(value.get("type") or "").lower()
        is_image_node = node_type == "image"

        if "src" in value and should_strip_generated_image_src(
            value.get("src"),
            allow_bare_ids=allow_bare_ids,
        ):
            value["src"] = ""
            changed = True

        if is_image_node and "url" in value and should_strip_generated_image_src(
            value.get("url"),
            allow_bare_ids=allow_bare_ids,
        ):
            value["url"] = ""
            changed = True

        if is_image_node and "content" in value and should_strip_generated_image_src(
            value.get("content"),
            allow_bare_ids=allow_bare_ids,
        ):
            value["content"] = ""
            changed = True

        for child in value.values():
            walk(child)

    walk(payload)
    return changed
