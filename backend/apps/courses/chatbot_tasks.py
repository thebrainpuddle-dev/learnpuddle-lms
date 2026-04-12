# apps/courses/chatbot_tasks.py
"""
Celery tasks for AI Chatbot knowledge ingestion pipeline:
PDF/text -> chunks -> embeddings -> pgvector bulk insert.
"""
import hashlib
import logging
import os
import tempfile
from typing import Optional

import tiktoken
from celery import shared_task
from django.db import transaction

from apps.courses.chatbot_models import (
    AIChatbotChunk,
    AIChatbotKnowledge,
    EMBEDDING_MODEL,
)
from utils.tenant_middleware import set_current_tenant, clear_current_tenant

logger = logging.getLogger(__name__)

# Chunking config
CHUNK_SIZE = 512       # tokens per chunk
CHUNK_OVERLAP = 50     # token overlap between chunks
EMBEDDING_DIMS = 1536
BATCH_SIZE = 16        # embeddings per API call


def _get_encoding():
    """Get tiktoken encoding for token counting."""
    return tiktoken.encoding_for_model("gpt-4o")


def _extract_text_from_pdf(file_path: str) -> list[dict]:
    """Extract text from PDF, returning list of {page, text} dicts."""
    import fitz  # PyMuPDF

    pages = []
    with fitz.open(file_path) as doc:
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if text:
                pages.append({"page": page_num, "text": text})
    return pages


def _chunk_text(
    text: str,
    page_number: Optional[int] = None,
    heading: str = "",
) -> list[dict]:
    """
    Split text into token-sized chunks with overlap.
    Returns list of dicts with content, token_count, page_number, heading.
    """
    enc = _get_encoding()
    tokens = enc.encode(text)

    if len(tokens) <= CHUNK_SIZE:
        return [{
            "content": text,
            "token_count": len(tokens),
            "page_number": page_number,
            "heading": heading,
        }]

    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + CHUNK_SIZE, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text = enc.decode(chunk_tokens)
        chunks.append({
            "content": chunk_text,
            "token_count": len(chunk_tokens),
            "page_number": page_number,
            "heading": heading,
        })
        start += CHUNK_SIZE - CHUNK_OVERLAP

    return chunks


def _get_embeddings(texts: list[str], api_key: str, base_url: str = "") -> list[list[float]]:
    """
    Call OpenAI-compatible embeddings API in batches.
    Returns list of embedding vectors (1536-dim float lists).
    """
    import requests as http_requests

    url = (base_url.rstrip("/") if base_url else "https://api.openai.com") + "/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    all_embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        resp = http_requests.post(
            url,
            headers=headers,
            json={"model": EMBEDDING_MODEL, "input": batch},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        batch_embeddings = [item["embedding"] for item in data["data"]]
        all_embeddings.extend(batch_embeddings)

    return all_embeddings


@shared_task(bind=True, max_retries=2)
def ingest_chatbot_knowledge(self, knowledge_id: str):
    """
    Main ingestion pipeline:
    1. Load knowledge source
    2. Extract text (PDF or raw)
    3. Chunk into 512-token segments
    4. Batch-embed via OpenAI API
    5. Bulk-insert AIChatbotChunk rows
    6. Update knowledge status
    """
    try:
        knowledge = AIChatbotKnowledge.all_objects.select_related(
            'chatbot', 'chatbot__tenant', 'chatbot__tenant__ai_config',
        ).get(pk=knowledge_id)
    except AIChatbotKnowledge.DoesNotExist:
        logger.error(f"Knowledge source {knowledge_id} not found")
        return

    chatbot = knowledge.chatbot
    tenant = chatbot.tenant

    # Set tenant context for TenantManager
    set_current_tenant(tenant)

    try:
        # Update status
        knowledge.embedding_status = 'processing'
        knowledge.save(update_fields=['embedding_status', 'updated_at'])

        # Step 1: Extract text
        # Use default_storage.open() instead of default_storage.path()
        # so this works with both local and remote (S3) storage backends.
        raw_chunks = []
        if knowledge.source_type == 'pdf' and knowledge.file_url:
            from django.core.files.storage import default_storage
            with default_storage.open(knowledge.file_url, 'rb') as remote_file:
                with tempfile.NamedTemporaryFile(suffix='.pdf', delete=True) as tmp:
                    for chunk in remote_file.chunks():
                        tmp.write(chunk)
                    tmp.flush()
                    pages = _extract_text_from_pdf(tmp.name)
            for page_data in pages:
                raw_chunks.extend(
                    _chunk_text(page_data["text"], page_number=page_data["page"])
                )
        elif knowledge.source_type == 'text' and knowledge.raw_text:
            raw_chunks = _chunk_text(knowledge.raw_text)
        elif knowledge.source_type == 'document' and knowledge.file_url:
            from django.core.files.storage import default_storage
            with default_storage.open(knowledge.file_url, 'rb') as remote_file:
                with tempfile.NamedTemporaryFile(suffix=os.path.splitext(knowledge.file_url)[1] or '.bin', delete=True) as tmp:
                    for chunk in remote_file.chunks():
                        tmp.write(chunk)
                    tmp.flush()
                    if tmp.name.endswith('.pdf'):
                        pages = _extract_text_from_pdf(tmp.name)
                        for page_data in pages:
                            raw_chunks.extend(
                                _chunk_text(page_data["text"], page_number=page_data["page"])
                            )
                    else:
                        tmp.seek(0)
                        text = tmp.read().decode('utf-8', errors='replace')
                        raw_chunks = _chunk_text(text)
        else:
            raise ValueError(f"Unsupported source_type: {knowledge.source_type}")

        if not raw_chunks:
            knowledge.embedding_status = 'failed'
            knowledge.error_message = 'No text could be extracted from the source.'
            knowledge.save(update_fields=['embedding_status', 'error_message', 'updated_at'])
            return

        # Step 2: Get embeddings
        try:
            ai_config = tenant.ai_config
        except Exception:
            raise ValueError("AI provider not configured for this school.")

        api_key = ai_config.get_llm_api_key()
        base_url = ai_config.llm_base_url or ""
        if not api_key:
            raise ValueError("No API key configured for AI provider.")

        chunk_texts = [c["content"] for c in raw_chunks]
        embeddings = _get_embeddings(chunk_texts, api_key, base_url)

        # Step 3: Bulk insert chunks
        total_tokens = 0
        chunk_objects = []
        for idx, (chunk_data, embedding) in enumerate(zip(raw_chunks, embeddings)):
            total_tokens += chunk_data["token_count"]
            chunk_objects.append(
                AIChatbotChunk(
                    knowledge=knowledge,
                    tenant=tenant,
                    chatbot=chatbot,
                    chunk_index=idx,
                    content=chunk_data["content"],
                    token_count=chunk_data["token_count"],
                    heading=chunk_data.get("heading", ""),
                    page_number=chunk_data.get("page_number"),
                    embedding=embedding,
                )
            )

        with transaction.atomic():
            # Delete existing chunks for this knowledge source (re-ingestion)
            AIChatbotChunk.all_objects.filter(knowledge=knowledge).delete()
            AIChatbotChunk.all_objects.bulk_create(chunk_objects, batch_size=500)

            knowledge.chunk_count = len(chunk_objects)
            knowledge.total_token_count = total_tokens
            knowledge.embedding_status = 'ready'
            knowledge.error_message = ''
            knowledge.save(update_fields=[
                'chunk_count', 'total_token_count',
                'embedding_status', 'error_message', 'updated_at',
            ])

        logger.info(
            f"Ingested {len(chunk_objects)} chunks for knowledge {knowledge_id} "
            f"({total_tokens} tokens)"
        )

    except Exception as exc:
        logger.exception(f"Knowledge ingestion failed for {knowledge_id}")
        try:
            knowledge.embedding_status = 'failed'
            knowledge.error_message = str(exc)[:1000]
            knowledge.save(update_fields=['embedding_status', 'error_message', 'updated_at'])
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=120)
    finally:
        clear_current_tenant()
