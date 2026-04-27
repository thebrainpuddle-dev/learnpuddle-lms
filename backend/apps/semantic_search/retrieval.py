"""
Retrieval helper for semantic search (TASK-057).

Public entry point: :func:`search`. Embeds the query once and runs a
parametrised pgvector cosine-distance query scoped to the current
tenant, optionally narrowed by ``kinds`` and/or ``course_id``.

Returns a list of hits with structure::

    {
      "source_type": "content",
      "source_id":   "<uuid>",
      "chunk_index": 3,
      "score":       0.812,           # 1 - cosine_distance
      "snippet":     "...first 240 chars...",
      "context": {
         "course_id":    "...",
         "course_title": "...",
         "module_id":    "...",
         "content_id":   "..."
      }
    }

Designed to be side-effect-free: TASK-059's RAG chatbot will layer its
own caching / reranking on top.
"""

from __future__ import annotations

import logging
from typing import Iterable

from django.db import connection, ProgrammingError, OperationalError

from .embeddings import EmbeddingError, embed_texts
from .models import (
    EmbeddingChunk,
    SOURCE_TYPE_CONTENT,
    SOURCE_TYPE_COURSE,
    SOURCE_TYPE_MODULE,
    SOURCE_TYPE_TRANSCRIPT,
)


logger = logging.getLogger(__name__)


MAX_TOP_K = 50
MAX_QUERY_CHARS = 2000
SNIPPET_CHARS = 240
ALLOWED_KINDS = {
    SOURCE_TYPE_COURSE,
    SOURCE_TYPE_MODULE,
    SOURCE_TYPE_CONTENT,
    SOURCE_TYPE_TRANSCRIPT,
}


class SearchValidationError(ValueError):
    """Raised for inputs that violate the hard API caps."""


def _has_embedding_column() -> bool:
    """Return True iff pgvector ``embedding`` column exists on the chunks table."""
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


def _resolve_course_scope(tenant, course_id) -> tuple[list[str], list[str]] | None:
    """
    Given a course UUID, return ``(module_ids, content_ids)`` that belong
    to it. Returns ``None`` when the course does not belong to the tenant
    (caller should then return empty results).
    """
    # Lazy import to avoid circulars.
    from apps.courses.models import Course, Module, Content

    try:
        course = Course.all_objects.get(id=course_id, tenant=tenant)
    except Course.DoesNotExist:
        return None

    module_ids = list(
        Module.all_objects.filter(course=course).values_list("id", flat=True)
    )
    content_ids = list(
        Content.all_objects.filter(module_id__in=module_ids).values_list(
            "id", flat=True
        )
    )
    return (
        [str(m) for m in module_ids],
        [str(c) for c in content_ids],
    )


def _build_context_index(tenant, rows) -> dict:
    """Batch-lookup course/module/content metadata for the given rows.

    Returns ``{(source_type, source_id): {course_id, course_title,
    module_id, content_id, content_title, module_title}}``.

    ``content_title`` is populated for content/transcript hits (the
    Content.title field).  ``module_title`` is populated for
    content/transcript and module hits (the Module.title field).  Both
    default to ``None`` for course-level hits or unresolved rows.
    """
    from apps.courses.models import Course, Module, Content

    content_ids: set[str] = set()
    module_ids: set[str] = set()
    course_ids: set[str] = set()

    for r in rows:
        st, sid = r["source_type"], str(r["source_id"])
        if st == SOURCE_TYPE_CONTENT or st == SOURCE_TYPE_TRANSCRIPT:
            content_ids.add(sid)
        elif st == SOURCE_TYPE_MODULE:
            module_ids.add(sid)
        elif st == SOURCE_TYPE_COURSE:
            course_ids.add(sid)

    contents = {
        str(c.id): c
        for c in Content.all_objects.filter(
            id__in=list(content_ids), module__course__tenant=tenant
        ).select_related("module", "module__course")
    }
    modules = {
        str(m.id): m
        for m in Module.all_objects.filter(
            id__in=list(module_ids), course__tenant=tenant
        ).select_related("course")
    }
    courses = {
        str(c.id): c
        for c in Course.all_objects.filter(
            id__in=list(course_ids), tenant=tenant
        )
    }

    idx: dict = {}
    for r in rows:
        st, sid = r["source_type"], str(r["source_id"])
        ctx = {
            "course_id": None,
            "course_title": None,
            "module_id": None,
            "content_id": None,
            "content_title": None,
            "module_title": None,
        }
        if st in (SOURCE_TYPE_CONTENT, SOURCE_TYPE_TRANSCRIPT) and sid in contents:
            c = contents[sid]
            ctx["content_id"] = str(c.id)
            ctx["content_title"] = c.title
            ctx["module_id"] = str(c.module_id)
            ctx["module_title"] = c.module.title
            ctx["course_id"] = str(c.module.course_id)
            ctx["course_title"] = c.module.course.title
        elif st == SOURCE_TYPE_MODULE and sid in modules:
            m = modules[sid]
            ctx["module_id"] = str(m.id)
            ctx["module_title"] = m.title
            ctx["course_id"] = str(m.course_id)
            ctx["course_title"] = m.course.title
        elif st == SOURCE_TYPE_COURSE and sid in courses:
            course = courses[sid]
            ctx["course_id"] = str(course.id)
            ctx["course_title"] = course.title
        idx[(st, sid)] = ctx
    return idx


def search(
    tenant,
    query: str,
    *,
    top_k: int = 10,
    kinds: Iterable[str] | None = None,
    course_id: str | None = None,
) -> list[dict]:
    """
    Tenant-scoped semantic similarity search.

    Arguments
    ---------
    tenant     the Tenant instance to scope results to (required).
    query      text query; rejected with SearchValidationError if
               longer than MAX_QUERY_CHARS or empty.
    top_k      max hits to return; hard-capped at MAX_TOP_K.
    kinds      optional iterable of source_type values to include;
               must be subset of ALLOWED_KINDS.
    course_id  optional Course UUID; if set, restricts to chunks whose
               content/module/course belong to that course.

    Raises
    ------
    SearchValidationError  on invalid inputs (caller converts to 400).
    EmbeddingError         on upstream embedding failure (caller → 503).
    """
    if tenant is None:
        raise SearchValidationError("tenant is required")

    q = (query or "").strip()
    if not q:
        raise SearchValidationError("query must be non-empty")
    if len(q) > MAX_QUERY_CHARS:
        raise SearchValidationError("QUERY_TOO_LONG")

    try:
        top_k_int = int(top_k)
    except Exception as exc:  # noqa: BLE001
        raise SearchValidationError("top_k must be an integer") from exc
    if top_k_int <= 0:
        raise SearchValidationError("top_k must be positive")
    if top_k_int > MAX_TOP_K:
        raise SearchValidationError("TOP_K_TOO_LARGE")

    if kinds is not None:
        kinds = list(kinds)
        for k in kinds:
            if k not in ALLOWED_KINDS:
                raise SearchValidationError(f"Unknown kind: {k}")

    # Course filter resolution — may short-circuit to empty.
    allowed_content_ids: list[str] | None = None
    allowed_module_ids: list[str] | None = None
    allowed_course_id: str | None = None
    if course_id:
        scope = _resolve_course_scope(tenant, course_id)
        if scope is None:
            return []
        module_ids, content_ids = scope
        allowed_module_ids = module_ids
        allowed_content_ids = content_ids
        allowed_course_id = str(course_id)

    # If pgvector isn't installed on this DB, gracefully return empty.
    if not _has_embedding_column():
        logger.warning(
            "semantic_search.search: pgvector embedding column missing; "
            "returning empty results (tenant=%s)", getattr(tenant, "id", None),
        )
        return []

    # 1. Embed the query (one call).
    embeddings = embed_texts([q])
    if not embeddings:
        raise EmbeddingError("Embedding provider returned no vectors")
    qvec = embeddings[0]

    # 2. Build and run the parametrised SQL. We use raw SQL only for the
    # pgvector ``<=>`` ORDER BY (no other unsafe clauses); all user input
    # is bound as parameters.
    params: list = [str(tenant.id)]
    clauses = ["tenant_id = %s"]

    if kinds:
        placeholders = ",".join(["%s"] * len(kinds))
        clauses.append(f"source_type IN ({placeholders})")
        params.extend(kinds)

    if course_id:
        # Build the course-scope OR clause:
        #   (source_type='course' AND source_id = :course)
        #   OR (source_type='module' AND source_id IN :modules)
        #   OR (source_type IN ('content','transcript') AND source_id IN :contents)
        sub_clauses: list[str] = []
        sub_clauses.append("(source_type = %s AND source_id = %s)")
        params.extend([SOURCE_TYPE_COURSE, allowed_course_id])
        if allowed_module_ids:
            ph = ",".join(["%s"] * len(allowed_module_ids))
            sub_clauses.append(f"(source_type = %s AND source_id::text IN ({ph}))")
            params.append(SOURCE_TYPE_MODULE)
            params.extend(allowed_module_ids)
        if allowed_content_ids:
            ph = ",".join(["%s"] * len(allowed_content_ids))
            sub_clauses.append(
                f"(source_type IN (%s, %s) AND source_id::text IN ({ph}))"
            )
            params.extend([SOURCE_TYPE_CONTENT, SOURCE_TYPE_TRANSCRIPT])
            params.extend(allowed_content_ids)
        clauses.append("(" + " OR ".join(sub_clauses) + ")")

    # pgvector literal: convert python list → '[x,y,z]' string; bound as param.
    vec_literal = "[" + ",".join(f"{x:.8f}" for x in qvec) + "]"

    sql = (
        "SELECT id, source_type, source_id, chunk_index, text, "
        "embedding <=> %s::vector AS distance "
        "FROM semantic_search_embeddingchunk "
        "WHERE " + " AND ".join(clauses) + " "
        "ORDER BY embedding <=> %s::vector "
        "LIMIT %s"
    )
    # <=> appears twice (filter clause then ORDER BY); bind vector twice.
    bound_params = [vec_literal] + params + [vec_literal, top_k_int]

    try:
        with connection.cursor() as cur:
            cur.execute(sql, bound_params)
            rows = cur.fetchall()
    except (ProgrammingError, OperationalError) as exc:
        # ProgrammingError covers missing pgvector extension / undefined operator.
        # OperationalError covers transient connection issues we want to swallow.
        # All other DB errors (IntegrityError, DataError, etc.) propagate so
        # they surface as 500s rather than being silently swallowed.
        logger.exception(
            "semantic_search.search: vector query failed (tenant=%s): %s",
            getattr(tenant, "id", None), exc,
        )
        return []

    # 3. Hydrate hit rows + join context via a minimal in-memory lookup.
    raw = [
        {
            "id": str(r[0]),
            "source_type": r[1],
            "source_id": r[2],
            "chunk_index": r[3],
            "text": r[4] or "",
            "score": round(max(0.0, 1.0 - float(r[5])), 6),
        }
        for r in rows
    ]
    ctx_index = _build_context_index(tenant, raw)

    hits: list[dict] = []
    for r in raw:
        snippet = r["text"].strip().replace("\n", " ")
        if len(snippet) > SNIPPET_CHARS:
            snippet = snippet[:SNIPPET_CHARS].rstrip()
        hits.append(
            {
                "source_type": r["source_type"],
                "source_id": str(r["source_id"]),
                "chunk_index": r["chunk_index"],
                "score": r["score"],
                "snippet": snippet,
                "context": ctx_index.get((r["source_type"], str(r["source_id"]))) or {
                    "course_id": None,
                    "course_title": None,
                    "module_id": None,
                    "content_id": None,
                    "content_title": None,
                    "module_title": None,
                },
            }
        )
    return hits
