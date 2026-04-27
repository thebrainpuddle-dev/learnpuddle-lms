"""Service helpers for TASK-058 — translation extraction, hashing, limits."""

from __future__ import annotations

import hashlib
import re
from typing import Iterable, List, Tuple

from django.conf import settings

from .models import (
    FIELD_BODY,
    FIELD_DESCRIPTION,
    FIELD_TITLE,
    FIELD_TRANSCRIPT,
    SOURCE_TYPE_CONTENT,
    SOURCE_TYPE_COURSE,
    SOURCE_TYPE_MODULE,
)

# ---------------------------------------------------------------------------
# Constants — language allowlist + caps
# ---------------------------------------------------------------------------

DEFAULT_TARGET_LANGUAGES = ("es", "fr", "de", "hi", "zh-CN", "ar")

# Per-field cap — 50 KB (bytes). Enforced before enqueueing work.
FIELD_SIZE_CAP_BYTES = 50 * 1024

# Course-level cost guard — estimate = char_count // 4; reject > 500k tokens.
COURSE_TOKEN_ESTIMATE_CAP = 500_000

# BCP-47-ish language code shape: 2-3 letter primary + optional -REGION part.
_LANG_RE = re.compile(r"^[a-zA-Z]{2,3}(-[A-Za-z0-9]{2,8})?$")


def allowed_target_languages() -> List[str]:
    """Return allowlist of permitted target languages from settings.

    Parses the comma-separated env ``TRANSLATION_TARGET_LANGUAGES``.
    """
    raw = getattr(settings, "TRANSLATION_TARGET_LANGUAGES", "")
    if not raw:
        return list(DEFAULT_TARGET_LANGUAGES)
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def is_valid_language_code(code: str) -> bool:
    """Validate BCP-47-ish shape (not a full parser)."""
    if not code or not isinstance(code, str):
        return False
    return bool(_LANG_RE.match(code))


def validate_target_languages(codes: Iterable[str]) -> Tuple[List[str], List[str]]:
    """Return ``(valid, rejected)`` lists.

    A code is valid when it passes shape validation AND is in the
    allowlist.
    """
    allow = set(allowed_target_languages())
    valid: List[str] = []
    rejected: List[str] = []
    for code in codes or []:
        if not isinstance(code, str):
            rejected.append(str(code))
            continue
        c = code.strip()
        if is_valid_language_code(c) and c in allow:
            valid.append(c)
        else:
            rejected.append(c)
    return valid, rejected


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------


def extract_course_fields(course) -> List[Tuple[str, str]]:
    return [
        (FIELD_TITLE, course.title or ""),
        (FIELD_DESCRIPTION, course.description or ""),
    ]


def extract_module_fields(module) -> List[Tuple[str, str]]:
    return [
        (FIELD_TITLE, module.title or ""),
        (FIELD_DESCRIPTION, module.description or ""),
    ]


def extract_content_fields(content) -> List[Tuple[str, str]]:
    """Return translatable (field, text) pairs for a Content row.

    Mapping:
      * ``title``       → ``Content.title``
      * ``body``        → ``Content.text_content`` (rich-text / body)
      * ``transcript``  → ``VideoAsset.transcript.full_text`` when a
        transcribed video is linked. Missing/empty → row is omitted.

    ``description`` is intentionally NOT included — Content has no such
    field in this codebase; admins place descriptive copy in the body.
    """
    pairs: List[Tuple[str, str]] = [
        (FIELD_TITLE, content.title or ""),
        (FIELD_BODY, content.text_content or ""),
    ]
    transcript = _content_transcript(content)
    if transcript:
        pairs.append((FIELD_TRANSCRIPT, transcript))
    return pairs


def _content_transcript(content) -> str:
    try:
        video_asset = getattr(content, "video_asset", None)
        if video_asset is None:
            return ""
        t = getattr(video_asset, "transcript", None)
        if t is None:
            return ""
        return t.full_text or ""
    except Exception:  # pragma: no cover - defensive
        return ""


# ---------------------------------------------------------------------------
# Hashing / size
# ---------------------------------------------------------------------------


def compute_source_hash(
    text: str, source_language: str, target_language: str, model: str
) -> str:
    """Return sha256 hex digest of (text + src + tgt + model)."""
    blob = f"{text}\x00{source_language}\x00{target_language}\x00{model}"
    return hashlib.sha256(blob.encode("utf-8", errors="replace")).hexdigest()


def field_bytes(text: str) -> int:
    return len(text.encode("utf-8", errors="replace")) if text else 0


def oversize_fields(
    pairs: Iterable[Tuple[str, str]],
) -> List[str]:
    """Return list of field names whose UTF-8 size exceeds the cap."""
    over: List[str] = []
    for field, text in pairs:
        if field_bytes(text) > FIELD_SIZE_CAP_BYTES:
            over.append(field)
    return over


def estimate_course_token_count(course) -> int:
    """Rough char/4 token estimate across course + modules + content."""
    total_chars = 0
    for _field, text in extract_course_fields(course):
        total_chars += len(text or "")
    # Walk modules + contents. Use all_objects to include unpublished
    # drafts that admins may still want translated.
    for module in course.modules.all():
        for _field, text in extract_module_fields(module):
            total_chars += len(text or "")
        for content in module.contents.all():
            for _field, text in extract_content_fields(content):
                total_chars += len(text or "")
    return total_chars // 4
