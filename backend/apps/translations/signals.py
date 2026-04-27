"""Invalidation signals for TASK-058.

When a source translatable field changes we must delete the stored
``ContentTranslation`` rows for that (source_type, source_id, field) so
the admin opts into an explicit re-run. We do NOT auto-enqueue a new
translation job — that keeps provider spend predictable on mass edits.

On ``post_delete`` we cascade-delete translations for the removed object.
"""

from __future__ import annotations

import logging
from typing import Iterable

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.courses.models import Content, Course, Module

from .models import (
    ContentTranslation,
    FIELD_BODY,
    FIELD_DESCRIPTION,
    FIELD_TITLE,
    FIELD_TRANSCRIPT,
    SOURCE_TYPE_CONTENT,
    SOURCE_TYPE_COURSE,
    SOURCE_TYPE_MODULE,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


COURSE_FIELDS = {"title": FIELD_TITLE, "description": FIELD_DESCRIPTION}
MODULE_FIELDS = {"title": FIELD_TITLE, "description": FIELD_DESCRIPTION}
CONTENT_FIELDS = {"title": FIELD_TITLE, "text_content": FIELD_BODY}


def _invalidate(source_type: str, source_id, fields: Iterable[str]) -> int:
    fields = list(fields)
    if not fields:
        return 0
    qs = ContentTranslation.objects.all_tenants().filter(
        source_type=source_type,
        source_id=source_id,
        field__in=fields,
    )
    count = qs.count()
    if count:
        qs.delete()
        logger.info(
            "translation.invalidate source=%s:%s fields=%s removed=%s",
            source_type, source_id, fields, count,
        )
    return count


def _changed_fields(instance, field_map: dict[str, str]) -> list[str]:
    """Return translation-field names whose source value changed."""
    original = getattr(instance, "_translation_original_values", None)
    if original is None:
        return []
    changed: list[str] = []
    for attr, tfield in field_map.items():
        old = original.get(attr)
        new = getattr(instance, attr, None)
        if (old or "") != (new or ""):
            changed.append(tfield)
    return changed


def _stash_original(instance, field_map: dict[str, str]) -> None:
    """Stash pre-save values so post_save can diff.

    On a *new* object (no PK yet) we record empty-string originals so
    the post_save handler reports all non-empty fields as "changed"
    — but since no ContentTranslation rows exist yet, the delete is a
    no-op and the code stays correct.
    """
    if instance.pk is None:
        instance._translation_original_values = {k: "" for k in field_map}
        return
    try:
        # Use all_objects manager where available to avoid tenant filter issues.
        manager = getattr(type(instance), "all_objects", None) or type(instance).objects
        previous = manager.get(pk=instance.pk)
    except type(instance).DoesNotExist:  # pragma: no cover - defensive
        instance._translation_original_values = {k: "" for k in field_map}
        return
    instance._translation_original_values = {
        k: getattr(previous, k, "") for k in field_map
    }


# ---------------------------------------------------------------------------
# Course
# ---------------------------------------------------------------------------


@receiver(pre_save, sender=Course)
def _course_stash_original(sender, instance, **kwargs):
    _stash_original(instance, COURSE_FIELDS)


@receiver(post_save, sender=Course)
def _course_invalidate(sender, instance, created, **kwargs):
    if created:
        return
    changed = _changed_fields(instance, COURSE_FIELDS)
    _invalidate(SOURCE_TYPE_COURSE, instance.pk, changed)


@receiver(post_delete, sender=Course)
def _course_cascade_delete(sender, instance, **kwargs):
    ContentTranslation.objects.all_tenants().filter(
        source_type=SOURCE_TYPE_COURSE,
        source_id=instance.pk,
    ).delete()


# ---------------------------------------------------------------------------
# Module
# ---------------------------------------------------------------------------


@receiver(pre_save, sender=Module)
def _module_stash_original(sender, instance, **kwargs):
    _stash_original(instance, MODULE_FIELDS)


@receiver(post_save, sender=Module)
def _module_invalidate(sender, instance, created, **kwargs):
    if created:
        return
    changed = _changed_fields(instance, MODULE_FIELDS)
    _invalidate(SOURCE_TYPE_MODULE, instance.pk, changed)


@receiver(post_delete, sender=Module)
def _module_cascade_delete(sender, instance, **kwargs):
    ContentTranslation.objects.all_tenants().filter(
        source_type=SOURCE_TYPE_MODULE,
        source_id=instance.pk,
    ).delete()


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------


@receiver(pre_save, sender=Content)
def _content_stash_original(sender, instance, **kwargs):
    _stash_original(instance, CONTENT_FIELDS)


@receiver(post_save, sender=Content)
def _content_invalidate(sender, instance, created, **kwargs):
    if created:
        return
    changed = _changed_fields(instance, CONTENT_FIELDS)
    _invalidate(SOURCE_TYPE_CONTENT, instance.pk, changed)


@receiver(post_delete, sender=Content)
def _content_cascade_delete(sender, instance, **kwargs):
    ContentTranslation.objects.all_tenants().filter(
        source_type=SOURCE_TYPE_CONTENT,
        source_id=instance.pk,
    ).delete()
