"""
Service-layer helpers for semantic_search (TASK-057b).

Provides ``purge_embeddings_for_source`` — a thin wrapper around the
``EmbeddingChunk`` queryset delete that is reused by:

  * ``apps.semantic_search.signals`` — ``post_delete`` receivers (hard delete)
  * ``apps.semantic_search.signals`` — ``soft_deleted`` receivers (soft delete)

Keeping the delete logic in one place ensures both code paths stay in sync
if the query shape changes (e.g. adding a shard key).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def purge_embeddings_for_source(source_type: str, source_id, tenant) -> int:
    """
    Delete all ``EmbeddingChunk`` rows matching (tenant, source_type, source_id).

    Returns the number of rows deleted (0 if none matched or on error).

    Parameters
    ----------
    source_type:
        One of ``'course'``, ``'module'``, ``'content'``, ``'transcript'``.
    source_id:
        UUID (or any value accepted by the ``source_id`` column) of the
        deleted source object.
    tenant:
        A ``Tenant`` instance (or anything with a truthy value and an
        ``id`` attribute).  Passed straight to the ORM filter so the
        query is always tenant-scoped.
    """
    if not tenant:
        logger.warning(
            "purge_embeddings_for_source: tenant is falsy — skipping "
            "purge for %s:%s", source_type, source_id,
        )
        return 0

    try:
        from .models import EmbeddingChunk
        deleted, _ = EmbeddingChunk.all_objects.filter(
            tenant=tenant,
            source_type=source_type,
            source_id=source_id,
        ).delete()
        if deleted:
            logger.debug(
                "purge_embeddings_for_source: deleted %d chunk(s) "
                "for %s:%s tenant=%s",
                deleted, source_type, source_id, getattr(tenant, "id", tenant),
            )
        return deleted
    except Exception:
        logger.exception(
            "purge_embeddings_for_source: error purging %s:%s tenant=%s",
            source_type, source_id, getattr(tenant, "id", tenant),
        )
        return 0
