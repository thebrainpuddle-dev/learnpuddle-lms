"""
Signal handlers for the semantic_search app (TASK-057 / TASK-057b).

post_save on Course/Module/Content
    Debounced reindex enqueue (Celery).

post_delete on Course/Module/Content
    Hard-delete cleanup — removes matching EmbeddingChunk rows.

soft_deleted on Course/Module/Content  (TASK-057b)
    Soft-delete cleanup — removes matching EmbeddingChunk rows.
    ``post_delete`` does NOT fire on soft-delete, so we need a separate
    receiver connected to the custom ``soft_deleted`` signal dispatched by
    ``SoftDeleteMixin.soft_delete()``.

**Debounce strategy**: rapid edits during a single admin session
should coalesce into one reindex. We use ``cache.add`` with a 30s TTL
as a lightweight mutex around a ``countdown=30`` Celery apply_async.
If ``cache.add`` returns False (key already taken) we skip enqueue —
the pending task will pick up the latest DB state when it runs.

On cache outage the ``cache.add`` call may raise; we log and fall
through to an immediate enqueue (failing OPEN here is fine — correct
indexing is more important than deduplication).
"""

from __future__ import annotations

import logging

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .services import purge_embeddings_for_source


logger = logging.getLogger(__name__)


DEBOUNCE_WINDOW_SECONDS = 30


def _debounce_key(kind: str, obj_id) -> str:
    return f"semantic_search:debounce:{kind}:{obj_id}"


def _try_acquire_debounce(kind: str, obj_id) -> bool:
    """Return True when we should enqueue; False when a recent enqueue exists."""
    key = _debounce_key(kind, obj_id)
    try:
        acquired = cache.add(key, "1", timeout=DEBOUNCE_WINDOW_SECONDS)
        return bool(acquired)
    except Exception:
        logger.warning(
            "semantic_search.debounce: cache.add failed for %s:%s — enqueuing anyway",
            kind, obj_id,
        )
        return True


# ---------------------------------------------------------------------------
# post_save — debounced enqueue
# ---------------------------------------------------------------------------


@receiver(post_save, sender="courses.Content")
def on_content_saved(sender, instance, created: bool, **kwargs):
    if not _try_acquire_debounce("content", instance.pk):
        return
    try:
        from .tasks import reindex_content
        reindex_content.apply_async(
            args=[str(instance.pk)],
            countdown=DEBOUNCE_WINDOW_SECONDS,
        )
    except Exception:
        logger.exception(
            "semantic_search: enqueue reindex_content failed for %s", instance.pk,
        )


@receiver(post_save, sender="courses.Module")
def on_module_saved(sender, instance, created: bool, **kwargs):
    if not _try_acquire_debounce("module", instance.pk):
        return
    try:
        # Reindex the whole course — covers module title + all content.
        from .tasks import reindex_course
        reindex_course.apply_async(
            args=[str(instance.course_id)],
            countdown=DEBOUNCE_WINDOW_SECONDS,
        )
    except Exception:
        logger.exception(
            "semantic_search: enqueue reindex_course(module=%s) failed", instance.pk,
        )


@receiver(post_save, sender="courses.Course")
def on_course_saved(sender, instance, created: bool, **kwargs):
    if not _try_acquire_debounce("course", instance.pk):
        return
    try:
        from .tasks import reindex_course
        reindex_course.apply_async(
            args=[str(instance.pk)],
            countdown=DEBOUNCE_WINDOW_SECONDS,
        )
    except Exception:
        logger.exception(
            "semantic_search: enqueue reindex_course failed for %s", instance.pk,
        )


# ---------------------------------------------------------------------------
# post_delete — row cleanup (hard delete)
# ---------------------------------------------------------------------------


@receiver(post_delete, sender="courses.Content")
def on_content_deleted(sender, instance, **kwargs):
    try:
        tenant_id = instance.module.course.tenant_id
    except Exception:
        tenant_id = None
    if not tenant_id:
        return
    try:
        tenant = instance.module.course.tenant
    except Exception:
        return
    purge_embeddings_for_source("content", instance.pk, tenant)
    purge_embeddings_for_source("transcript", instance.pk, tenant)


@receiver(post_delete, sender="courses.Module")
def on_module_deleted(sender, instance, **kwargs):
    try:
        tenant = instance.course.tenant
    except Exception:
        return
    purge_embeddings_for_source("module", instance.pk, tenant)


@receiver(post_delete, sender="courses.Course")
def on_course_deleted(sender, instance, **kwargs):
    tenant = getattr(instance, "tenant", None)
    if tenant is None:
        return
    purge_embeddings_for_source("course", instance.pk, tenant)


# ---------------------------------------------------------------------------
# soft_deleted — row cleanup (soft delete, TASK-057b)
#
# The ``soft_deleted`` signal is defined in ``apps.courses.signals`` so that
# apps/courses/ does NOT need to import from apps/semantic_search/ (avoiding
# a circular dependency).  We connect here inside the SemanticSearchConfig
# ready() hook (see apps.py) so the import only happens after all apps load.
# ---------------------------------------------------------------------------


def _get_tenant_for_content(instance):
    """Resolve the Tenant from a Content instance, traversing the FK chain."""
    try:
        return instance.module.course.tenant
    except Exception:
        return None


def _get_tenant_for_module(instance):
    """Resolve the Tenant from a Module instance."""
    try:
        return instance.course.tenant
    except Exception:
        return None


def on_course_soft_deleted(sender, instance, **kwargs):
    """
    Purge all EmbeddingChunks belonging to a soft-deleted Course.

    Because SoftDeleteMixin.soft_delete() does NOT cascade to children
    automatically, we iterate the course's modules and contents here
    (using all_objects so already-soft-deleted children are included).
    """
    from apps.courses.models import Module, Content

    tenant = getattr(instance, "tenant", None)
    if tenant is None:
        return

    # Purge course-level chunks.
    purge_embeddings_for_source("course", instance.pk, tenant)

    # Cascade purge to each module and its contents.
    modules = Module.all_objects.filter(course=instance)
    for module in modules:
        purge_embeddings_for_source("module", module.pk, tenant)
        contents = Content.all_objects.filter(module=module)
        for content in contents:
            purge_embeddings_for_source("content", content.pk, tenant)
            purge_embeddings_for_source("transcript", content.pk, tenant)


def on_module_soft_deleted(sender, instance, **kwargs):
    """Purge EmbeddingChunks for a soft-deleted Module."""
    tenant = _get_tenant_for_module(instance)
    if tenant is None:
        return
    purge_embeddings_for_source("module", instance.pk, tenant)


def on_content_soft_deleted(sender, instance, **kwargs):
    """Purge EmbeddingChunks (content + transcript) for a soft-deleted Content."""
    tenant = _get_tenant_for_content(instance)
    if tenant is None:
        return
    purge_embeddings_for_source("content", instance.pk, tenant)
    purge_embeddings_for_source("transcript", instance.pk, tenant)


def connect_soft_delete_receivers():
    """
    Connect the soft_deleted signal receivers.

    Called from SemanticSearchConfig.ready() after all apps have loaded so
    that the lazy string sender references (``"courses.Course"`` etc.) are
    already resolved by Django's app registry.
    """
    from apps.courses.signals import soft_deleted
    from apps.courses.models import Course, Module, Content

    soft_deleted.connect(
        on_course_soft_deleted,
        sender=Course,
        dispatch_uid="semantic_search.on_course_soft_deleted",
    )
    soft_deleted.connect(
        on_module_soft_deleted,
        sender=Module,
        dispatch_uid="semantic_search.on_module_soft_deleted",
    )
    soft_deleted.connect(
        on_content_soft_deleted,
        sender=Content,
        dispatch_uid="semantic_search.on_content_soft_deleted",
    )
