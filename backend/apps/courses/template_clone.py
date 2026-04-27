"""
Blueprint serialization + template -> tenant clone helpers (TASK-049).

This module is deliberately self-contained. If TASK-048 merges its own
``versioning_snapshot.py`` helpers, the two modules converge on the same
JSON shape (see ``BLUEPRINT_SCHEMA_VERSION``); until then this is the
single source of truth.

Public API:
    * ``BLUEPRINT_SCHEMA_VERSION``          — bump if the JSON shape changes.
    * ``serialize_course_to_blueprint()``   — course -> dict (not used by
      TASK-049 itself; exposed so the future "Fork from my course" flow can
      reuse it).
    * ``clone_template_to_tenant()``        — materialises a template's
      ``blueprint_json`` into real Course / Module / Content rows belonging
      to the given tenant. Runs inside an atomic transaction; new UUIDs are
      generated for every row.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils.text import slugify


BLUEPRINT_SCHEMA_VERSION = 1

# Content types whose real artefacts (video files, SCORM packages, uploaded
# quiz banks, etc.) are tenant-scoped and therefore CANNOT be copied across
# when we clone a platform template into a tenant. We still materialize the
# content row so order + title survive, but we flag it as a placeholder so
# the admin knows they need to replace it before publishing.
TENANT_SCOPED_CONTENT_TYPES = frozenset({"VIDEO", "SCORM", "QUIZ"})


def serialize_course_to_blueprint(course) -> Dict[str, Any]:
    """
    Serialize a ``Course`` + its active modules + contents into a blueprint
    dict. Does not traverse tenant-scoped artefacts (video files, etc.);
    those are represented by the content row's metadata only.
    """
    modules_payload: List[Dict[str, Any]] = []
    module_qs = course.modules.filter(is_active=True).order_by("order").prefetch_related("contents")
    for module in module_qs:
        contents_payload: List[Dict[str, Any]] = []
        content_qs = module.contents.filter(is_active=True).order_by("order")
        for content in content_qs:
            contents_payload.append({
                "title": content.title,
                "content_type": content.content_type,
                "order": content.order,
                "text_content": content.text_content or "",
                "file_url": content.file_url or "",
                "duration": content.duration,
                "is_mandatory": content.is_mandatory,
                "meta_json": {},
            })
        modules_payload.append({
            "title": module.title,
            "description": module.description or "",
            "order": module.order,
            "contents": contents_payload,
        })

    return {
        "schema_version": BLUEPRINT_SCHEMA_VERSION,
        "course": {
            "title": course.title,
            "description": course.description or "",
            "estimated_hours": int(course.estimated_hours or 0),
            "is_mandatory": bool(course.is_mandatory),
        },
        "modules": modules_payload,
    }


def _unique_course_slug(tenant, base_title: str) -> str:
    """Generate a slug that doesn't collide within the tenant."""
    from .models import Course  # local import to avoid circular

    base = slugify(base_title) or "course"
    # Include a short UUID suffix so re-cloning the same template twice
    # never trips the (tenant, slug) unique constraint.
    suffix = uuid.uuid4().hex[:8]
    candidate = f"{base}-{suffix}"
    while Course.all_objects.filter(tenant=tenant, slug=candidate).exists():
        suffix = uuid.uuid4().hex[:8]
        candidate = f"{base}-{suffix}"
    return candidate


def clone_template_to_tenant(
    template,
    tenant,
    user,
    title_override: Optional[str] = None,
    module_prefix: Optional[str] = None,
):
    """
    Materialize ``template.blueprint_json`` into real rows under ``tenant``.

    * Atomic: any exception mid-clone rolls everything back.
    * Generates fresh UUIDs for every row (no collision with the template).
    * ``course.tenant = tenant``, ``course.created_by = user``,
      ``course.is_published = False`` (admin publishes later).
    * Video / SCORM / Quiz contents get ``meta_json.is_placeholder = True``
      and a "Replace me" body, since their underlying artefacts are
      tenant-scoped and can't be copied.

    Returns the newly created ``Course`` instance.
    """
    from .models import Course, Module, Content  # local import

    blueprint = template.blueprint_json or {}
    course_payload = blueprint.get("course") or {}
    modules_payload = blueprint.get("modules") or []

    title = title_override or course_payload.get("title") or template.title

    with transaction.atomic():
        course = Course.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            title=title,
            slug=_unique_course_slug(tenant, title),
            description=course_payload.get("description") or template.description or "",
            estimated_hours=course_payload.get("estimated_hours") or template.estimated_hours or 0,
            is_mandatory=bool(course_payload.get("is_mandatory", False)),
            is_published=False,
            is_active=True,
            created_by=user,
        )

        for mod_idx, mod_data in enumerate(modules_payload, start=1):
            mod_title = mod_data.get("title") or f"Module {mod_idx}"
            if module_prefix:
                mod_title = f"{module_prefix}{mod_title}"
            module = Module.objects.create(
                id=uuid.uuid4(),
                course=course,
                title=mod_title,
                description=mod_data.get("description") or "",
                order=mod_data.get("order") or mod_idx,
                is_active=True,
            )

            for content_idx, content_data in enumerate(
                mod_data.get("contents") or [], start=1
            ):
                content_type = content_data.get("content_type") or "TEXT"
                is_placeholder = content_type in TENANT_SCOPED_CONTENT_TYPES

                meta = dict(content_data.get("meta_json") or {})
                if is_placeholder:
                    meta["is_placeholder"] = True
                    meta["placeholder_reason"] = (
                        f"{content_type} artefacts are tenant-scoped and "
                        "must be re-uploaded in your tenant."
                    )

                # For placeholder types we intentionally drop file_url + duration
                # so admins don't see dangling references to platform assets.
                text_body = content_data.get("text_content") or ""
                if is_placeholder and not text_body:
                    text_body = (
                        f"Replace me — this {content_type.lower()} was provided as a "
                        "template placeholder. Upload or configure the real "
                        "content here before publishing."
                    )

                Content.objects.create(
                    id=uuid.uuid4(),
                    module=module,
                    title=content_data.get("title") or f"Content {content_idx}",
                    content_type=content_type,
                    order=content_data.get("order") or content_idx,
                    file_url="" if is_placeholder else (content_data.get("file_url") or ""),
                    duration=None if is_placeholder else content_data.get("duration"),
                    text_content=text_body,
                    is_mandatory=bool(content_data.get("is_mandatory", True)),
                    is_active=True,
                    meta_json=meta,
                )

        return course
