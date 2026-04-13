import re
from typing import Dict, Iterable, Set

import bleach
from bleach.css_sanitizer import CSSSanitizer
from bs4 import BeautifulSoup
from django.conf import settings
from django.core.files.storage import default_storage

from utils.s3_utils import sign_url

RTIMG_PREFIX = "rtimg:"
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)

ALLOWED_TAGS = [
    "p",
    "br",
    "strong",
    "em",
    "u",
    "s",
    "sub",
    "sup",
    "blockquote",
    "code",
    "pre",
    "ul",
    "ol",
    "li",
    "a",
    "img",
    "h1",
    "h2",
    "h3",
    "h4",
    "span",
    "div",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "hr",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height", "data-image-id"],
    "span": ["style"],
    "p": ["style"],
    "h1": ["style"],
    "h2": ["style"],
    "h3": ["style"],
    "h4": ["style"],
    "div": ["style"],
    "table": ["style"],
    "th": ["style"],
    "td": ["style"],
    "tr": ["style"],
}

ALLOWED_PROTOCOLS = ["http", "https", "mailto", "tel", "rtimg"]
ALLOWED_CSS_PROPS = {
    "font-size", "margin-left", "text-align",
    # Layout & spacing
    "margin", "margin-top", "margin-bottom", "margin-right",
    "padding", "padding-top", "padding-bottom", "padding-left", "padding-right",
    # Colors & backgrounds
    "color", "background", "background-color",
    # Borders
    "border", "border-left", "border-right", "border-top", "border-bottom",
    "border-radius", "border-collapse",
    # Typography
    "font-weight", "font-style", "line-height",
    # Table
    "width", "max-width",
}


def _normalize_style(style: str) -> str:
    if not style:
        return ""
    out = []
    for part in style.split(";"):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key not in ALLOWED_CSS_PROPS or not value:
            continue
        out.append(f"{key}: {value}")
    return "; ".join(out)


def _extract_image_id(image_id: str | None, src: str | None) -> str | None:
    candidate = (image_id or "").strip()
    if candidate and UUID_RE.match(candidate):
        return candidate

    src_val = (src or "").strip()
    if src_val.startswith(RTIMG_PREFIX):
        image_from_src = src_val[len(RTIMG_PREFIX) :]
        if UUID_RE.match(image_from_src):
            return image_from_src

    match = re.search(r"/rtimg/([0-9a-fA-F\-]{36})", src_val)
    if match and UUID_RE.match(match.group(1)):
        return match.group(1)

    return None


def collect_rich_text_image_ids(raw_html: str) -> Set[str]:
    if not raw_html:
        return set()
    soup = BeautifulSoup(raw_html, "html.parser")
    ids = set()
    for img in soup.find_all("img"):
        image_id = _extract_image_id(img.get("data-image-id"), img.get("src"))
        if image_id:
            ids.add(image_id)
    return ids


def sanitize_rich_text_html(raw_html: str) -> str:
    """
    Sanitize rich HTML and canonicalize inline image references.

    Canonical image source format in DB: `rtimg:<uuid>`.
    """
    if not raw_html:
        return ""

    css_sanitizer = CSSSanitizer(allowed_css_properties=list(ALLOWED_CSS_PROPS))
    cleaned = bleach.clean(
        raw_html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        css_sanitizer=css_sanitizer,
        strip=True,
    )
    cleaned = bleach.linkify(cleaned)

    soup = BeautifulSoup(cleaned, "html.parser")

    for el in soup.find_all(True):
        style = el.attrs.get("style")
        if style is not None:
            normalized = _normalize_style(style)
            if normalized:
                el.attrs["style"] = normalized
            else:
                del el.attrs["style"]

    for img in soup.find_all("img"):
        image_id = _extract_image_id(img.get("data-image-id"), img.get("src"))
        if not image_id:
            img.decompose()
            continue
        img.attrs["data-image-id"] = image_id
        img.attrs["src"] = f"{RTIMG_PREFIX}{image_id}"

    return str(soup)


def build_rich_text_image_url_map(
    image_ids: Iterable[str],
    *,
    expires_in: int = 14400,
    request=None,
    tenant=None,
) -> Dict[str, str]:
    ids = [i for i in set(image_ids) if UUID_RE.match(i)]
    if not ids:
        return {}

    from apps.courses.models import RichTextImageAsset

    tenant_obj = tenant or getattr(request, "tenant", None)
    if not tenant_obj:
        return {}

    rows = RichTextImageAsset.all_objects.filter(
        tenant=tenant_obj,
        id__in=ids,
    ).values("id", "storage_key")
    url_map: Dict[str, str] = {}
    for row in rows:
        key = row.get("storage_key") or ""
        if not key:
            continue

        if getattr(settings, "STORAGE_BACKEND", "local").lower() == "s3":
            url = sign_url(key, expires_in=expires_in)
        else:
            url = default_storage.url(key)
            if request and url.startswith("/"):
                url = request.build_absolute_uri(url)

        url_map[str(row["id"])] = url

    return url_map


def rewrite_rich_text_html_for_output(raw_html: str, image_url_map: Dict[str, str]) -> str:
    """Replace canonical image refs in rich HTML with current signed/public URLs."""
    if not raw_html:
        return ""

    soup = BeautifulSoup(raw_html, "html.parser")
    for img in soup.find_all("img"):
        image_id = _extract_image_id(img.get("data-image-id"), img.get("src"))
        if not image_id:
            continue
        resolved = image_url_map.get(image_id)
        if resolved:
            img.attrs["data-image-id"] = image_id
            img.attrs["src"] = resolved

    return str(soup)


def rewrite_rich_text_for_serializer(raw_html: str, context: dict) -> str:
    """Rewrite rich text HTML by resolving inline image IDs to signed/public URLs.

    This is the canonical implementation of the ``_rewrite_rich_text`` pattern that
    appears in DRF serializers.  Serializers should call this helper instead of
    duplicating the logic:

        def _rewrite_rich_text(self, raw_html: str) -> str:
            return rewrite_rich_text_for_serializer(raw_html, self.context)

    Args:
        raw_html: Raw HTML string (may contain ``rtimg:<uuid>`` src attributes).
        context:  DRF serializer context dict.  Must contain ``"request"`` to
                  resolve tenant for image lookups.  A ``"_rich_text_image_url_map"``
                  key is used as a per-serialization cache to avoid repeated DB/S3
                  round-trips when multiple fields reference the same images.

    Returns:
        HTML string with resolved image URLs.
    """
    image_ids = collect_rich_text_image_ids(raw_html)
    if not image_ids:
        return raw_html

    cache = context.setdefault("_rich_text_image_url_map", {})
    missing = [image_id for image_id in image_ids if image_id not in cache]
    if missing:
        cache.update(
            build_rich_text_image_url_map(
                missing,
                request=context.get("request"),
            )
        )
    return rewrite_rich_text_html_for_output(raw_html, cache)
