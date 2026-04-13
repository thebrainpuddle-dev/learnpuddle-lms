# apps/courses/chatbot_rag_service.py
"""
RAG pipeline for AI Chatbot:
1. Embed student query
2. Hybrid search: pgvector similarity + PostgreSQL full-text keyword search
3. Assemble context + system prompt
4. Stream LLM response via SSE
"""
import json
import logging
import time
from typing import Generator

import requests as http_requests
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector

try:
    from pgvector.django import CosineDistance
    HAS_PGVECTOR = True
except ImportError:
    CosineDistance = None
    HAS_PGVECTOR = False

from apps.courses.chatbot_models import AIChatbotChunk, EMBEDDING_MODEL
from apps.courses.chatbot_guardrails import build_system_prompt
from apps.courses.chatbot_tasks import _get_encoding

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.4  # cosine distance threshold
TOP_K = 5                    # number of chunks to retrieve
HISTORY_TOKEN_BUDGET = 6000  # max tokens for conversation history
MAX_HISTORY_MESSAGES = 40    # hard cap on history length from client

# Cache pgvector availability to avoid repeated DB queries
_pgvector_available: bool | None = None


def _has_embedding_column() -> bool:
    """Check if the embedding column exists in ai_chatbot_chunks (cached)."""
    global _pgvector_available
    if _pgvector_available is not None:
        return _pgvector_available
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'ai_chatbot_chunks' AND column_name = 'embedding'"
            )
            _pgvector_available = cursor.fetchone() is not None
    except Exception:
        _pgvector_available = False
    return _pgvector_available


def _normalize_base_url(base_url: str) -> str:
    """Ensure base_url ends with /v1 (no duplication)."""
    base = base_url.rstrip("/") if base_url else "https://api.openai.com/v1"
    if not base.endswith("/v1"):
        base += "/v1"
    return base


def _embed_query(query: str, api_key: str, base_url: str = "") -> list[float]:
    """Embed a single query string with retry (3 attempts, exponential backoff)."""
    url = _normalize_base_url(base_url) + "/embeddings"
    last_exc = None
    for attempt in range(3):
        try:
            resp = http_requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": EMBEDDING_MODEL, "input": [query]},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
        except http_requests.RequestException as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(2 ** attempt)  # 1s, 2s
    raise last_exc


def _vector_search(
    chatbot_id: str,
    tenant_id: str,
    query_embedding: list[float],
) -> list[dict]:
    """
    pgvector cosine-distance search. Returns list of result dicts.
    Raises if pgvector is not available.
    """
    if not HAS_PGVECTOR:
        raise ImportError("pgvector is not installed")

    chunks = (
        AIChatbotChunk.all_objects
        .filter(tenant_id=tenant_id, chatbot_id=chatbot_id)
        .select_related('knowledge')
        .annotate(distance=CosineDistance('embedding', query_embedding))
        .filter(distance__lt=SIMILARITY_THRESHOLD)
        .order_by('distance')[:TOP_K]
    )

    return [
        {
            "content": chunk.content,
            "title": chunk.knowledge.title,
            "page_number": chunk.page_number,
            "heading": chunk.heading,
            "snippet": chunk.content[:200],
            "score": round(1 - chunk.distance, 4),
            "is_auto": chunk.knowledge.is_auto,
            "_pk": chunk.pk,
        }
        for chunk in chunks
    ]


def _keyword_search(
    chatbot_id: str,
    tenant_id: str,
    user_message: str,
    exclude_pks: set,
    limit: int,
) -> list[dict]:
    """
    PostgreSQL full-text keyword search using SearchVector / SearchQuery / SearchRank.
    Always available (no pgvector dependency).
    """
    if limit <= 0:
        return []

    search_vector = SearchVector('content')
    search_query = SearchQuery(user_message, search_type='websearch')

    chunks = (
        AIChatbotChunk.all_objects
        .filter(tenant_id=tenant_id, chatbot_id=chatbot_id)
        .exclude(pk__in=exclude_pks)
        .select_related('knowledge')
        .annotate(rank=SearchRank(search_vector, search_query))
        .filter(rank__gt=0)
        .order_by('-rank')[:limit]
    )

    return [
        {
            "content": chunk.content,
            "title": chunk.knowledge.title,
            "page_number": chunk.page_number,
            "heading": chunk.heading,
            "snippet": chunk.content[:200],
            "score": round(float(chunk.rank), 4),
            "is_auto": chunk.knowledge.is_auto,
            "_pk": chunk.pk,
        }
        for chunk in chunks
    ]


def retrieve_context(
    chatbot_id: str,
    tenant_id: str,
    query_embedding: list[float],
    user_message: str = "",
) -> list[dict]:
    """
    Hybrid search: pgvector similarity + PostgreSQL full-text keyword search.
    Returns list of {content, title, page_number, heading, snippet, score, is_auto} dicts.

    Strategy:
    - Try vector search first (requires pgvector).
    - If vector search returns fewer than TOP_K results, supplement with keyword search.
    - If pgvector is unavailable, fall back to keyword-only search.
    - Results are deduplicated and capped at TOP_K.
    """
    vector_results = []

    # --- Vector search (pgvector) ---
    try:
        vector_results = _vector_search(chatbot_id, tenant_id, query_embedding)
    except Exception:
        logger.debug(
            "pgvector search unavailable or failed; falling back to keyword-only search",
            exc_info=True,
        )

    # --- Keyword search to fill remaining slots ---
    remaining = TOP_K - len(vector_results)
    seen_pks = {r["_pk"] for r in vector_results}

    keyword_results = []
    if remaining > 0 and user_message:
        try:
            keyword_results = _keyword_search(
                chatbot_id, tenant_id, user_message, seen_pks, remaining,
            )
        except Exception:
            logger.debug("Keyword search failed", exc_info=True)

    # --- Combine and strip internal _pk field ---
    combined = vector_results + keyword_results
    for item in combined:
        item.pop("_pk", None)

    return combined[:TOP_K]


def stream_chat_response(
    chatbot,
    conversation_messages: list[dict],
    user_message: str,
    ai_config,
) -> Generator[str, None, dict]:
    """
    Full RAG chat pipeline. Yields SSE-formatted strings.
    Returns final dict with {content, sources} after streaming completes.

    Usage:
        gen = stream_chat_response(chatbot, messages, query, config)
        for chunk in gen:
            yield chunk  # SSE data
        # After generator exhausts, result is in gen's return value
    """
    api_key = ai_config.get_llm_api_key()
    if not api_key:
        yield f"data: {json.dumps({'type': 'error', 'error': 'AI provider is not configured. Please contact your administrator.'})}\n\n"
        return {"content": "", "sources": []}

    base_url = ai_config.llm_base_url or ""

    # Step 1: Embed query (skip if pgvector unavailable — saves API cost)
    query_embedding = []
    if _has_embedding_column():
        try:
            query_embedding = _embed_query(user_message, api_key, base_url)
        except Exception:
            logger.warning("Embedding query failed; falling back to keyword search", exc_info=True)

    # Step 2: Retrieve context (hybrid search)
    context_chunks = retrieve_context(
        chatbot_id=str(chatbot.id),
        tenant_id=str(chatbot.tenant_id),
        query_embedding=query_embedding,
        user_message=user_message,
    )

    sources = [
        {
            "title": c["title"],
            "page": c.get("page_number"),
            "heading": c.get("heading", ""),
            "snippet": c.get("snippet", ""),
        }
        for c in context_chunks
        if c.get("title")
    ]

    # Step 3: Build system prompt with guardrails + context
    system_prompt = build_system_prompt(chatbot, context_chunks)

    # Step 4: Build messages array
    llm_messages = [{"role": "system", "content": system_prompt}]
    # Add conversation history with token budget to avoid exceeding context window.
    # Iterate backward through the last 20 messages, keeping only those that fit.
    enc = _get_encoding()
    recent_messages = conversation_messages[-20:]
    budget_remaining = HISTORY_TOKEN_BUDGET
    trimmed_history = []
    for msg in reversed(recent_messages):
        msg_tokens = len(enc.encode(msg["content"]))
        if msg_tokens > budget_remaining:
            break
        budget_remaining -= msg_tokens
        trimmed_history.append({"role": msg["role"], "content": msg["content"]})
    trimmed_history.reverse()
    llm_messages.extend(trimmed_history)
    llm_messages.append({"role": "user", "content": user_message})

    # Step 5: Stream LLM response
    url = _normalize_base_url(base_url) + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": ai_config.llm_model,  # Full model ID (e.g. openai/gpt-4o-mini for OpenRouter)
        "messages": llm_messages,
        "stream": True,
        "temperature": 0.7,
        "max_tokens": 2048,
    }

    full_content = ""

    # Retry the initial connection (2 attempts), then stream with proper cleanup
    resp = None
    last_exc = None
    for attempt in range(2):
        try:
            resp = http_requests.post(
                url, headers=headers, json=payload, stream=True, timeout=120,
            )
            resp.raise_for_status()
            break  # connection succeeded
        except http_requests.RequestException as exc:
            last_exc = exc
            if resp is not None:
                resp.close()
                resp = None
            if attempt < 1:
                time.sleep(1)

    if resp is None:
        logger.exception("LLM streaming failed after retries", exc_info=last_exc)
        yield f"data: {json.dumps({'type': 'error', 'error': 'An error occurred while generating the response.'})}\n\n"
    else:
        try:
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full_content += content
                        yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
                except (json.JSONDecodeError, IndexError, KeyError):
                    continue
        except http_requests.RequestException:
            logger.exception("LLM streaming failed mid-stream")
            yield f"data: {json.dumps({'type': 'error', 'error': 'An error occurred while generating the response.'})}\n\n"
        finally:
            resp.close()

    # Send sources at the end
    if sources:
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return {"content": full_content, "sources": sources}
