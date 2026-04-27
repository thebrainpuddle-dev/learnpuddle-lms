"""Course materialiser for TASK-060 — AI Course Generator.

Converts a validated CourseBlueprint into a draft Course + Module + Content
rows, all within a single transaction.atomic().

Key rules:
- Course is created with is_published=False (draft — invisible to teachers).
- quiz-type contents → LINK with meta_json comment about TASK-043.
- assignment-type contents → TEXT placeholder.
- Never auto-publishes.
"""

from __future__ import annotations

import logging

from django.db import transaction

from .outline_service import CourseBlueprint

logger = logging.getLogger(__name__)

# Content type constants (mirrors courses.models.Content.CONTENT_TYPE_CHOICES)
CONTENT_TYPE_TEXT = "TEXT"
CONTENT_TYPE_LINK = "LINK"


@transaction.atomic
def materialise_course(
    blueprint: CourseBlueprint,
    tenant,
    created_by,
    title_hint: str | None = None,
) -> "courses.Course":  # type: ignore[name-defined]  # noqa: F821
    """Create and return a draft Course from a CourseBlueprint.

    All database operations are wrapped in a single transaction; any failure
    rolls back completely.

    Args:
        blueprint: Validated CourseBlueprint dataclass.
        tenant: Tenant instance (already resolved from request).
        created_by: User instance that triggered generation.
        title_hint: Optional title hint used to derive slug if different from blueprint.

    Returns:
        The newly created (unpublished) Course instance.
    """
    from apps.courses.models import Course, Module, Content

    # ── create Course ────────────────────────────────────────────────────────
    course = Course(
        tenant=tenant,
        title=blueprint.title,
        description=blueprint.description,
        is_published=False,   # Draft — never auto-publish
        is_active=True,
        created_by=created_by,
    )
    # Let Course.save() handle slug generation
    course.save()

    logger.info(
        "Materialised draft Course %s (%r) for tenant %s",
        course.id,
        course.title,
        tenant.id,
    )

    # ── create Modules + Contents ─────────────────────────────────────────────
    for mod_index, mod_bp in enumerate(blueprint.modules):
        module = Module.objects.create(
            course=course,
            title=mod_bp.title,
            order=mod_index,
            is_active=True,
        )

        for content_index, content_bp in enumerate(mod_bp.contents):
            content_type, text_content, meta = _resolve_content_type(content_bp)
            Content.objects.create(
                module=module,
                title=content_bp.title,
                content_type=content_type,
                order=content_index,
                text_content=text_content,
                is_active=True,
                meta_json=meta,
            )

    return course


def _resolve_content_type(content_bp) -> tuple[str, str, dict]:
    """Return (content_type, text_content, meta_json) for a ContentBlueprint.

    Mapping per spec:
    - "text"       → TEXT, description as text_content.
    - "quiz"       → LINK placeholder, meta notes TASK-043.
    - "assignment" → TEXT placeholder, meta notes future work.
    """
    ctype = content_bp.type

    if ctype == "quiz":
        meta = {
            "is_placeholder": True,
            "placeholder_type": "quiz",
            "note": "TODO: attach quiz config via TASK-043",
            "description": content_bp.description,
        }
        return CONTENT_TYPE_LINK, "", meta

    if ctype == "assignment":
        text = (
            f"{content_bp.description}\n\n"
            "[Placeholder assignment — configure details via the course editor]"
        )
        meta = {
            "is_placeholder": True,
            "placeholder_type": "assignment",
            "description": content_bp.description,
        }
        return CONTENT_TYPE_TEXT, text, meta

    # Default: text
    return CONTENT_TYPE_TEXT, content_bp.description, {}
