"""
Celery tasks for semantic search indexing (TASK-057).

Three tasks:

  * reindex_content(content_id)  — embed a single Content row + its
                                    transcript chunks. Idempotent.
  * reindex_course(course_id)    — fan out over every module/content
                                    that belongs to a course.
  * reindex_tenant(tenant_id)    — admin-triggered full rebuild, runs
                                    off-peak. Enqueues per-course
                                    sub-tasks.

All tasks are idempotent on re-run thanks to the
``(tenant, source_type, source_id, chunk_index)`` unique key and the
``text_hash`` skip-condition (``SHA256(text + model)``).
"""

from __future__ import annotations

import hashlib
import logging

from celery import shared_task
from django.db import connection, transaction
from django.utils import timezone

from .chunker import chunk_text
from .embeddings import EmbeddingError, embed_texts, embedder_info
from .models import (
    EmbeddingChunk,
    EmbeddingJobRun,
    SOURCE_TYPE_CONTENT,
    SOURCE_TYPE_COURSE,
    SOURCE_TYPE_MODULE,
    SOURCE_TYPE_TRANSCRIPT,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compose_title_desc(title: str | None, description: str | None) -> str:
    parts = [p.strip() for p in (title or "", description or "") if (p or "").strip()]
    return "\n\n".join(parts)


def _hash_text(text: str, model: str) -> str:
    h = hashlib.sha256()
    h.update((text or "").encode("utf-8"))
    h.update(b"|")
    h.update((model or "").encode("utf-8"))
    return h.hexdigest()


def _has_embedding_column() -> bool:
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name=%s AND column_name=%s",
                ["semantic_search_embeddingchunk", "embedding"],
            )
            return cur.fetchone() is not None
    except Exception:
        return False


def _pgvector_literal(vec) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"


def _upsert_chunk(
    *,
    tenant,
    source_type: str,
    source_id,
    chunk_index: int,
    text: str,
    text_hash: str,
    embedding: list[float] | None,
    model: str,
    provider: str,
) -> bool:
    """
    Upsert a single chunk, skipping re-embedding when text_hash matches.

    Returns True when the row was newly created or replaced with a fresh
    embedding, False when the existing row's text_hash matched and no
    work was done.
    """
    existing = (
        EmbeddingChunk.all_objects.filter(
            tenant=tenant,
            source_type=source_type,
            source_id=source_id,
            chunk_index=chunk_index,
        )
        .only("id", "text_hash")
        .first()
    )

    if existing and existing.text_hash == text_hash:
        return False  # idempotent skip

    # We write the scalar columns via the ORM (upsert), then patch the
    # vector column via raw SQL when pgvector is installed.
    with transaction.atomic():
        if existing:
            existing.text = text
            existing.text_hash = text_hash
            existing.model = model
            existing.provider = provider
            existing.updated_at = timezone.now()
            existing.save(update_fields=["text", "text_hash", "model", "provider", "updated_at"])
            chunk_id = existing.id
        else:
            row = EmbeddingChunk.all_objects.create(
                tenant=tenant,
                source_type=source_type,
                source_id=source_id,
                chunk_index=chunk_index,
                text=text,
                text_hash=text_hash,
                model=model,
                provider=provider,
            )
            chunk_id = row.id

        if embedding is not None and _has_embedding_column():
            try:
                with connection.cursor() as cur:
                    cur.execute(
                        "UPDATE semantic_search_embeddingchunk "
                        "SET embedding = %s::vector WHERE id = %s",
                        [_pgvector_literal(embedding), str(chunk_id)],
                    )
            except Exception:
                logger.exception(
                    "semantic_search: failed to write embedding for chunk=%s", chunk_id
                )
    return True


def _delete_chunks(tenant, source_type: str, source_id) -> int:
    """Remove all chunk rows for a given source under a tenant."""
    deleted, _ = EmbeddingChunk.all_objects.filter(
        tenant=tenant,
        source_type=source_type,
        source_id=source_id,
    ).delete()
    return deleted


# ---------------------------------------------------------------------------
# Task: reindex_content
# ---------------------------------------------------------------------------


@shared_task(
    name="semantic_search.reindex_content",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    ignore_result=True,
)
def reindex_content(self, content_id: str) -> dict:
    """
    Reindex a single ``courses.Content`` row plus its transcript chunks.

    Skips chunks whose ``text_hash`` is unchanged.
    """
    from apps.courses.models import Content

    try:
        content = (
            Content.all_objects.select_related(
                "module", "module__course", "module__course__tenant"
            )
            .get(id=content_id)
        )
    except Content.DoesNotExist:
        logger.info("reindex_content: content=%s not found (likely deleted)", content_id)
        return {"skipped": True, "reason": "not_found"}

    tenant = content.module.course.tenant
    job = EmbeddingJobRun.objects.create(
        tenant=tenant, kind=EmbeddingJobRun.KIND_CONTENT, target_id=str(content.id),
    )

    indexed = 0
    info = embedder_info()
    model_name = info.get("model") or ""
    provider_name = info.get("provider") or ""

    try:
        # 1. Content title + description chunk (single).
        body = _compose_title_desc(
            content.title, getattr(content, "text_content", "")
        )
        if body:
            hash_ = _hash_text(body, model_name)
            vectors: list[list[float]] | None
            try:
                vectors = embed_texts([body])
            except EmbeddingError:
                logger.warning("reindex_content: embedding failed for content %s", content.id)
                vectors = None
            emb = vectors[0] if vectors else None
            if _upsert_chunk(
                tenant=tenant,
                source_type=SOURCE_TYPE_CONTENT,
                source_id=content.id,
                chunk_index=0,
                text=body,
                text_hash=hash_,
                embedding=emb,
                model=model_name,
                provider=provider_name,
            ):
                indexed += 1

        # 2. Transcript chunks (if present on the attached VideoAsset).
        transcript_full = ""
        try:
            va = getattr(content, "video_asset", None)
            if va is not None:
                tr = getattr(va, "transcript", None)
                if tr is not None:
                    transcript_full = tr.full_text or ""
        except Exception:
            # Video pipeline / transcript FK missing — safe ignore.
            transcript_full = ""

        if transcript_full and transcript_full.strip():
            chunks = chunk_text(transcript_full)
            # Build batch of texts whose hashes differ — then embed once.
            to_embed: list[tuple[int, str, str]] = []
            for idx, piece in chunks:
                hash_ = _hash_text(piece, model_name)
                existing = (
                    EmbeddingChunk.all_objects.filter(
                        tenant=tenant,
                        source_type=SOURCE_TYPE_TRANSCRIPT,
                        source_id=content.id,
                        chunk_index=idx,
                    )
                    .only("id", "text_hash")
                    .first()
                )
                if existing and existing.text_hash == hash_:
                    continue
                to_embed.append((idx, piece, hash_))

            vectors_batch: list[list[float]] | None = None
            if to_embed:
                try:
                    vectors_batch = embed_texts([t[1] for t in to_embed])
                except EmbeddingError:
                    logger.warning(
                        "reindex_content: transcript embedding failed for %s", content.id
                    )
                    vectors_batch = None

            for i, (idx, piece, hash_) in enumerate(to_embed):
                emb = vectors_batch[i] if vectors_batch else None
                if _upsert_chunk(
                    tenant=tenant,
                    source_type=SOURCE_TYPE_TRANSCRIPT,
                    source_id=content.id,
                    chunk_index=idx,
                    text=piece,
                    text_hash=hash_,
                    embedding=emb,
                    model=model_name,
                    provider=provider_name,
                ):
                    indexed += 1

        job.chunks_indexed = indexed
        job.status = EmbeddingJobRun.STATUS_SUCCEEDED
        job.finished_at = timezone.now()
        job.save(update_fields=["chunks_indexed", "status", "finished_at"])
        return {"indexed": indexed, "content_id": str(content.id)}

    except Exception as exc:  # pragma: no cover — reported to caller
        logger.exception("reindex_content failed content=%s", content_id)
        job.status = EmbeddingJobRun.STATUS_FAILED
        job.error = str(exc)[:2000]
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error", "finished_at"])
        raise


# ---------------------------------------------------------------------------
# Task: reindex_course
# ---------------------------------------------------------------------------


@shared_task(
    name="semantic_search.reindex_course",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    ignore_result=True,
)
def reindex_course(self, course_id: str) -> dict:
    """
    Index a Course row and fan-out per-content reindex tasks.

    - Writes one chunk for the course (title+description).
    - Writes one chunk per module (title only).
    - Enqueues ``reindex_content`` for every content row.
    """
    from apps.courses.models import Course, Module, Content

    try:
        course = Course.all_objects.select_related("tenant").get(id=course_id)
    except Course.DoesNotExist:
        return {"skipped": True, "reason": "not_found"}

    tenant = course.tenant
    job = EmbeddingJobRun.objects.create(
        tenant=tenant, kind=EmbeddingJobRun.KIND_COURSE, target_id=str(course.id),
    )

    info = embedder_info()
    model_name = info.get("model") or ""
    provider_name = info.get("provider") or ""

    indexed = 0

    try:
        # Course chunk
        body = _compose_title_desc(course.title, course.description)
        if body:
            hash_ = _hash_text(body, model_name)
            try:
                vec = embed_texts([body])
                emb = vec[0] if vec else None
            except EmbeddingError:
                emb = None
            if _upsert_chunk(
                tenant=tenant,
                source_type=SOURCE_TYPE_COURSE,
                source_id=course.id,
                chunk_index=0,
                text=body,
                text_hash=hash_,
                embedding=emb,
                model=model_name,
                provider=provider_name,
            ):
                indexed += 1

        # Module chunks
        modules = list(Module.all_objects.filter(course=course))
        if modules:
            mod_bodies = [
                _compose_title_desc(m.title, getattr(m, "description", ""))
                for m in modules
            ]
            to_embed: list[tuple[int, Module, str, str]] = []
            for m, body in zip(modules, mod_bodies):
                if not body:
                    continue
                h = _hash_text(body, model_name)
                existing = (
                    EmbeddingChunk.all_objects.filter(
                        tenant=tenant,
                        source_type=SOURCE_TYPE_MODULE,
                        source_id=m.id,
                        chunk_index=0,
                    )
                    .only("id", "text_hash")
                    .first()
                )
                if existing and existing.text_hash == h:
                    continue
                to_embed.append((0, m, body, h))

            vecs: list[list[float]] | None = None
            if to_embed:
                try:
                    vecs = embed_texts([t[2] for t in to_embed])
                except EmbeddingError:
                    vecs = None
            for i, (idx, m, body, h) in enumerate(to_embed):
                emb = vecs[i] if vecs else None
                if _upsert_chunk(
                    tenant=tenant,
                    source_type=SOURCE_TYPE_MODULE,
                    source_id=m.id,
                    chunk_index=idx,
                    text=body,
                    text_hash=h,
                    embedding=emb,
                    model=model_name,
                    provider=provider_name,
                ):
                    indexed += 1

        # Fan out content reindex.
        content_ids = list(
            Content.all_objects.filter(module__course=course).values_list(
                "id", flat=True
            )
        )
        for cid in content_ids:
            reindex_content.apply_async(args=[str(cid)])

        job.chunks_indexed = indexed
        job.status = EmbeddingJobRun.STATUS_SUCCEEDED
        job.finished_at = timezone.now()
        job.save(update_fields=["chunks_indexed", "status", "finished_at"])
        return {
            "indexed": indexed,
            "fanout_content": len(content_ids),
            "course_id": str(course.id),
        }
    except Exception as exc:
        logger.exception("reindex_course failed course=%s", course_id)
        job.status = EmbeddingJobRun.STATUS_FAILED
        job.error = str(exc)[:2000]
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error", "finished_at"])
        raise


# ---------------------------------------------------------------------------
# Task: reindex_tenant
# ---------------------------------------------------------------------------


@shared_task(
    name="semantic_search.reindex_tenant",
    bind=True,
    max_retries=0,
    ignore_result=True,
)
def reindex_tenant(self, tenant_id: str) -> dict:
    """
    Admin-triggered full rebuild for a tenant.

    Fans out ``reindex_course`` for every non-deleted course, then runs
    ``ANALYZE`` on the chunks table so the IVFFLAT index has fresh
    statistics. Safe to call multiple times (each sub-task is idempotent).
    """
    from apps.tenants.models import Tenant
    from apps.courses.models import Course

    try:
        tenant = Tenant.objects.get(id=tenant_id)
    except Tenant.DoesNotExist:
        return {"skipped": True, "reason": "not_found"}

    job = EmbeddingJobRun.objects.create(
        tenant=tenant, kind=EmbeddingJobRun.KIND_TENANT, target_id=str(tenant.id),
    )

    try:
        course_ids = list(
            Course.all_objects.filter(tenant=tenant).values_list("id", flat=True)
        )
        for cid in course_ids:
            reindex_course.apply_async(args=[str(cid)])

        # Fresh ANALYZE so the IVFFLAT index planner has good stats after
        # a large bulk insert. Best-effort: ignored if the extension is
        # missing locally.
        try:
            with connection.cursor() as cur:
                cur.execute("ANALYZE semantic_search_embeddingchunk;")
        except Exception:
            logger.debug("semantic_search: ANALYZE skipped (pgvector unavailable)")

        job.status = EmbeddingJobRun.STATUS_SUCCEEDED
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "finished_at"])
        return {"courses_queued": len(course_ids), "tenant_id": str(tenant.id)}
    except Exception as exc:
        logger.exception("reindex_tenant failed tenant=%s", tenant_id)
        job.status = EmbeddingJobRun.STATUS_FAILED
        job.error = str(exc)[:2000]
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error", "finished_at"])
        raise
