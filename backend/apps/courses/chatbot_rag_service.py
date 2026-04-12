# apps/courses/chatbot_rag_service.py
"""
RAG pipeline for AI Chatbot:
1. Embed student query
2. pgvector similarity search (filtered by tenant + chatbot)
3. Assemble context + system prompt
4. Stream LLM response via SSE
"""
import json
import logging
from typing import Generator

import requests as http_requests
from pgvector.django import CosineDistance

from apps.courses.chatbot_models import AIChatbotChunk, EMBEDDING_MODEL
from apps.courses.chatbot_guardrails import build_system_prompt

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.4  # cosine distance threshold
TOP_K = 5                    # number of chunks to retrieve


def _embed_query(query: str, api_key: str, base_url: str = "") -> list[float]:
    """Embed a single query string."""
    url = (base_url.rstrip("/") if base_url else "https://api.openai.com") + "/v1/embeddings"
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


def retrieve_context(
    chatbot_id: str,
    tenant_id: str,
    query_embedding: list[float],
) -> list[dict]:
    """
    Search pgvector for relevant chunks.
    Returns list of {content, title, page_number, score} dicts.
    """
    chunks = (
        AIChatbotChunk.all_objects
        .filter(tenant_id=tenant_id, chatbot_id=chatbot_id)
        .annotate(distance=CosineDistance('embedding', query_embedding))
        .filter(distance__lt=SIMILARITY_THRESHOLD)
        .order_by('distance')[:TOP_K]
        .select_related('knowledge')
    )

    return [
        {
            "content": chunk.content,
            "title": chunk.knowledge.title,
            "page_number": chunk.page_number,
            "score": round(1 - chunk.distance, 4),
        }
        for chunk in chunks
    ]


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
    base_url = ai_config.llm_base_url or ""

    # Step 1: Embed query
    query_embedding = _embed_query(user_message, api_key, base_url)

    # Step 2: Retrieve context
    context_chunks = retrieve_context(
        chatbot_id=str(chatbot.id),
        tenant_id=str(chatbot.tenant_id),
        query_embedding=query_embedding,
    )

    sources = [
        {"title": c["title"], "page": c.get("page_number")}
        for c in context_chunks
        if c.get("title")
    ]

    # Step 3: Build system prompt with guardrails + context
    system_prompt = build_system_prompt(chatbot, context_chunks)

    # Step 4: Build messages array
    llm_messages = [{"role": "system", "content": system_prompt}]
    # Add conversation history (last 20 messages for context window management)
    for msg in conversation_messages[-20:]:
        llm_messages.append({
            "role": msg["role"],
            "content": msg["content"],
        })
    llm_messages.append({"role": "user", "content": user_message})

    # Step 5: Stream LLM response
    url = (base_url.rstrip("/") if base_url else "https://api.openai.com") + "/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": ai_config.llm_model.split("/")[-1],  # Strip provider prefix
        "messages": llm_messages,
        "stream": True,
        "temperature": 0.7,
        "max_tokens": 2048,
    }

    full_content = ""

    try:
        resp = http_requests.post(
            url, headers=headers, json=payload, stream=True, timeout=120,
        )
        resp.raise_for_status()

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

    except http_requests.RequestException as exc:
        logger.exception("LLM streaming failed")
        yield f"data: {json.dumps({'type': 'error', 'error': 'An error occurred while generating the response.'})}\n\n"

    # Send sources at the end
    if sources:
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return {"content": full_content, "sources": sources}
