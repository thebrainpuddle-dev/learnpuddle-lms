"""
Deterministic snapshot helpers for Course / Module / Content.

Used by:
- `versioning_signals.py` to freeze state after every save (TASK-048).
- `versioning_views.py` restore endpoints to rebuild the tree (TASK-048).
- `template_*.py` (TASK-049) as a forward-compatible blueprint shape.

The output is plain-Python JSON-serializable (no Django model instances,
no Decimals, no dates — all converted to strings) so that two consecutive
serializations of the same object tree yield byte-identical JSON. This
is required for the "no-op save should not spam revisions" behavior.

Binary / file assets are referenced by their storage path only (we never
mutate a file in place, so the pointer is a stable identifier).

Field-set registry
------------------
Each model has a declared tuple of restorable scalar field names.  The
restore path in ``versioning_views`` iterates this tuple rather than
hard-coding field assignments, so adding a new snapshotted field only
requires updating one place.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Restorable field registry (data-driven restore)
# ---------------------------------------------------------------------------
#
# These tuples MUST stay in sync with the scalar keys written by the
# `serialize_*` helpers below.  `_apply_*_snapshot` in `versioning_views.py`
# walks these tuples when restoring.
#
# Notes:
# - ``id`` / ``tenant_id`` / ``course_id`` / ``module_id`` are intentionally
#   excluded — they are identity, not restorable state.
# - M2M fields are handled separately (see `COURSE_RESTORABLE_M2M`).

CONTENT_RESTORABLE_FIELDS: tuple = (
    "title",
    "content_type",
    "order",
    "file_url",
    "file_size",
    "duration",
    "text_content",
    "maic_classroom_id",
    "ai_chatbot_id",
    "is_mandatory",
    "is_active",
    "is_deleted",
)

MODULE_RESTORABLE_FIELDS: tuple = (
    "title",
    "description",
    "order",
    "is_active",
    "is_deleted",
)

COURSE_RESTORABLE_FIELDS: tuple = (
    "title",
    "slug",
    "description",
    "thumbnail",
    "is_mandatory",
    "deadline",
    "estimated_hours",
    "assigned_to_all",
    "assigned_to_all_students",
    "course_type",
    "subject_id",
    "is_published",
    "is_active",
    "is_deleted",
)

# M2M fields captured on Course.  Each is a list[str] of UUIDs in the snapshot.
# Restore resyncs via .set() filtered by tenant to prevent cross-tenant
# pollution if a stale ID snuck in.
COURSE_RESTORABLE_M2M: tuple = (
    "assigned_teachers",
    "assigned_students",
)


# ---------------------------------------------------------------------------
# Low-level primitive helpers
# ---------------------------------------------------------------------------

def _to_str_or_none(value) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _date_to_iso(value) -> Optional[str]:
    if value is None:
        return None
    # date / datetime both implement isoformat()
    return value.isoformat()


def _decimal_to_str(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _file_path(field) -> Optional[str]:
    """Return the stored path for a FileField / ImageField, not a URL."""
    if not field:
        return None
    try:
        return field.name or None
    except Exception:
        return None


def _m2m_ids(manager) -> List[str]:
    """Return a sorted list of UUID strings for an M2M manager.

    Sorted so two serializations of the same set yield byte-identical JSON
    (required for the snapshot-equality dedup in the signal).
    """
    try:
        return sorted(str(pk) for pk in manager.values_list("id", flat=True))
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------

def serialize_content(content) -> Dict[str, Any]:
    """Freeze a Content row to a deterministic dict."""
    return {
        "id": str(content.id),
        "module_id": str(content.module_id) if content.module_id else None,
        "title": content.title,
        "content_type": content.content_type,
        "order": int(content.order or 0),
        "file_url": content.file_url or "",
        "file_size": content.file_size,
        "duration": content.duration,
        "text_content": content.text_content or "",
        "maic_classroom_id": _to_str_or_none(content.maic_classroom_id),
        "ai_chatbot_id": _to_str_or_none(content.ai_chatbot_id),
        "is_mandatory": bool(content.is_mandatory),
        "is_active": bool(content.is_active),
        "is_deleted": bool(getattr(content, "is_deleted", False)),
    }


# ---------------------------------------------------------------------------
# Module
# ---------------------------------------------------------------------------

def serialize_module(module, include_contents: bool = True) -> Dict[str, Any]:
    """Freeze a Module row (optionally with children)."""
    data: Dict[str, Any] = {
        "id": str(module.id),
        "course_id": str(module.course_id) if module.course_id else None,
        "title": module.title,
        "description": module.description or "",
        "order": int(module.order or 0),
        "is_active": bool(module.is_active),
        "is_deleted": bool(getattr(module, "is_deleted", False)),
    }
    if include_contents:
        # Import here to avoid circular import at module load time.
        from .models import Content
        contents: List[Dict[str, Any]] = []
        qs = Content.all_objects.filter(module=module).order_by("order", "id")
        for c in qs:
            contents.append(serialize_content(c))
        data["contents"] = contents
    return data


# ---------------------------------------------------------------------------
# Course
# ---------------------------------------------------------------------------

def serialize_course(course, include_children: bool = True) -> Dict[str, Any]:
    """Freeze a Course row + (optionally) its module/content tree.

    M2M fields ``assigned_teachers`` and ``assigned_students`` are captured
    as sorted lists of UUID strings so restore can round-trip teacher /
    student assignment changes.
    """
    data: Dict[str, Any] = {
        "id": str(course.id),
        "tenant_id": str(course.tenant_id) if course.tenant_id else None,
        "title": course.title,
        "slug": course.slug,
        "description": course.description or "",
        "thumbnail": _file_path(getattr(course, "thumbnail", None)),
        "is_mandatory": bool(course.is_mandatory),
        "deadline": _date_to_iso(course.deadline),
        "estimated_hours": _decimal_to_str(course.estimated_hours),
        "assigned_to_all": bool(course.assigned_to_all),
        "assigned_to_all_students": bool(
            getattr(course, "assigned_to_all_students", False)
        ),
        "course_type": course.course_type,
        "subject_id": _to_str_or_none(getattr(course, "subject_id", None)),
        "is_published": bool(course.is_published),
        "is_active": bool(course.is_active),
        "is_deleted": bool(getattr(course, "is_deleted", False)),
        # M2Ms — sorted for deterministic snapshot equality.
        "assigned_teachers": (
            _m2m_ids(course.assigned_teachers)
            if course.pk and hasattr(course, "assigned_teachers")
            else []
        ),
        "assigned_students": (
            _m2m_ids(course.assigned_students)
            if course.pk and hasattr(course, "assigned_students")
            else []
        ),
    }
    if include_children:
        from .models import Module
        modules: List[Dict[str, Any]] = []
        qs = Module.all_objects.filter(course=course).order_by("order", "id")
        for m in qs:
            modules.append(serialize_module(m, include_contents=True))
        data["modules"] = modules
    return data


# ---------------------------------------------------------------------------
# Dispatch helper used by the signal
# ---------------------------------------------------------------------------

def serialize_instance(instance) -> Dict[str, Any]:
    """Dispatch based on model type; used by the post_save signal."""
    from .models import Course, Module, Content
    if isinstance(instance, Course):
        return serialize_course(instance, include_children=True)
    if isinstance(instance, Module):
        return serialize_module(instance, include_contents=True)
    if isinstance(instance, Content):
        return serialize_content(instance)
    raise TypeError(f"Cannot serialize {type(instance).__name__} for versioning")
