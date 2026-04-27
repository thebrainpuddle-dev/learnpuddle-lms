"""Celery tasks for TASK-060 — AI Course Generator.

Pipeline:
  pending → extracting → llm_outlining → materialising → succeeded
  (any step can transition to failed with an error message)
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from utils.audit import log_audit

logger = logging.getLogger(__name__)

TEXT_CAP = 100_000  # Characters; must match extractor constants


@shared_task(bind=True, max_retries=0, name="course_generator.generate_course_from_source")
def generate_course_from_source(self, job_id: str) -> None:
    """Drive the full AI course generation pipeline for a CourseGenerationJob.

    Steps:
      1. Mark job as extracting.
      2. Extract text from source (file or URL).
      3. Mark job as llm_outlining; call LLM.
      4. Mark job as materialising; create draft Course.
      5. Mark job as succeeded.

    Any exception transitions the job to failed.
    """
    from apps.course_generator.models import CourseGenerationJob
    from apps.course_generator.outline_service import generate_outline, looks_like_injection, OutlineProviderError
    from apps.course_generator.materialiser import materialise_course

    try:
        job = CourseGenerationJob.all_objects.get(id=job_id)
    except CourseGenerationJob.DoesNotExist:
        logger.error("CourseGenerationJob %s does not exist", job_id)
        return

    tenant = job.tenant
    created_by = job.created_by

    try:
        # ── Step 1: extracting ────────────────────────────────────────────────
        job.mark_started()  # Sets status = extracting

        log_audit(
            action="COURSE_GENERATION_STARTED",
            target_type="CourseGenerationJob",
            target_id=str(job.id),
            target_repr=str(job),
            actor=created_by,
            tenant=tenant,
        )

        extracted_text = _extract_text(job)

        # Truncate to cap
        truncated = len(extracted_text) > TEXT_CAP
        if truncated:
            # Truncate at a sentence boundary
            extracted_text = _truncate_at_sentence(extracted_text, TEXT_CAP)

        # Save extracted text + metadata
        job.extracted_text_truncated = extracted_text
        job.extracted_char_count = len(extracted_text)
        meta = job.source_metadata or {}
        meta["truncated"] = truncated
        job.source_metadata = meta
        job.save(update_fields=["extracted_text_truncated", "extracted_char_count", "source_metadata", "updated_at"])

        # Check for prompt injection (log, don't block)
        if looks_like_injection(extracted_text):
            logger.warning(
                "Prompt-injection pattern in source for job %s. Flagging in audit.",
                job.id,
            )
            log_audit(
                action="COURSE_GENERATION_FLAGGED",
                target_type="CourseGenerationJob",
                target_id=str(job.id),
                target_repr="PROMPT_INJECTION_DETECTED",
                changes={"warning": "Prompt injection pattern detected in source text"},
                actor=created_by,
                tenant=tenant,
            )

        # ── Step 2: llm_outlining ─────────────────────────────────────────────
        job.set_status(CourseGenerationJob.STATUS_LLM_OUTLINING)

        title_hint = (job.source_metadata or {}).get("title_hint")
        target_module_count = int((job.source_metadata or {}).get("target_module_count", 5))

        blueprint = generate_outline(
            extracted_text=extracted_text,
            title_hint=title_hint,
            target_module_count=target_module_count,
        )

        # Persist outline + provider metadata
        job.outline_json = {
            "title": blueprint.title,
            "description": blueprint.description,
            "modules": [
                {
                    "title": m.title,
                    "contents": [
                        {"type": c.type, "title": c.title, "description": c.description}
                        for c in m.contents
                    ],
                }
                for m in blueprint.modules
            ],
        }
        job.provider = blueprint.provider
        job.model = blueprint.model
        job.tokens_prompt = blueprint.tokens_prompt
        job.tokens_completion = blueprint.tokens_completion
        job.save(
            update_fields=[
                "outline_json", "provider", "model",
                "tokens_prompt", "tokens_completion", "updated_at",
            ]
        )

        # ── Step 3: succeeded (materialise is separate explicit step) ─────────
        job.set_status(CourseGenerationJob.STATUS_SUCCEEDED)

        log_audit(
            action="COURSE_GENERATION_SUCCEEDED",
            target_type="CourseGenerationJob",
            target_id=str(job.id),
            target_repr=str(job),
            changes={
                "provider": blueprint.provider,
                "model": blueprint.model,
                "tokens_prompt": blueprint.tokens_prompt,
                "tokens_completion": blueprint.tokens_completion,
            },
            actor=created_by,
            tenant=tenant,
        )

    except ValueError as exc:
        # Cost limit / validation errors
        _fail_job(job, str(exc), created_by, tenant)
    except OutlineProviderError as exc:
        _fail_job(job, f"LLM error: {exc}", created_by, tenant)
    except Exception as exc:
        logger.exception("Unexpected error in generate_course_from_source for job %s", job_id)
        _fail_job(job, f"Unexpected error: {exc}", created_by, tenant)


def _fail_job(job, error: str, actor, tenant) -> None:
    from apps.course_generator.models import CourseGenerationJob

    job.set_status(CourseGenerationJob.STATUS_FAILED, error=error)
    log_audit(
        action="COURSE_GENERATION_FAILED",
        target_type="CourseGenerationJob",
        target_id=str(job.id),
        target_repr=str(job),
        changes={"error": error},
        actor=actor,
        tenant=tenant,
    )


def _extract_text(job) -> str:
    """Dispatch to the correct extractor based on job.source_type."""
    source_type = job.source_type
    metadata = job.source_metadata or {}

    if source_type == "pdf":
        return _extract_file(job, "pdf")
    elif source_type == "docx":
        return _extract_file(job, "docx")
    elif source_type == "text":
        return _extract_file(job, "text")
    elif source_type == "youtube":
        url = metadata.get("url", "")
        from apps.course_generator.extractors.youtube import YouTubeExtractor
        return YouTubeExtractor().extract(url)
    elif source_type == "vimeo":
        url = metadata.get("url", "")
        from apps.course_generator.extractors.vimeo import VimeoExtractor
        return VimeoExtractor().extract(url)
    else:
        raise ValueError(f"Unknown source_type: {source_type!r}")


def _extract_file(job, file_type: str) -> str:
    """Read the temp file stored during the upload and extract text."""
    import io

    metadata = job.source_metadata or {}
    file_content_b64 = metadata.get("_file_b64")
    if not file_content_b64:
        raise ValueError(
            f"No file content in job metadata for source_type={file_type!r}"
        )

    import base64

    raw = base64.b64decode(file_content_b64)
    file_obj = io.BytesIO(raw)

    if file_type == "pdf":
        from apps.course_generator.extractors.pdf import PDFExtractor
        return PDFExtractor().extract(file_obj)
    elif file_type == "docx":
        from apps.course_generator.extractors.docx import DOCXExtractor
        return DOCXExtractor().extract(file_obj)
    elif file_type == "text":
        from apps.course_generator.extractors.text import TextExtractor
        return TextExtractor().extract(file_obj)
    else:
        raise ValueError(f"Unknown file_type: {file_type!r}")


def _truncate_at_sentence(text: str, cap: int) -> str:
    """Truncate text at cap chars, trying to end at a sentence boundary."""
    if len(text) <= cap:
        return text
    # Find the last sentence-ending punctuation before cap
    chunk = text[:cap]
    for punct in (".\n", ".\r\n", ". ", ".\t", "\n\n"):
        idx = chunk.rfind(punct)
        if idx > cap * 0.8:  # Must be in the last 20% to be worth it
            return chunk[: idx + len(punct)].rstrip()
    return chunk
