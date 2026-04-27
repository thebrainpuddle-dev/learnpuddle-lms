"""Celery tasks for TASK-058 — Auto-Translation Service.

Tasks are idempotent: a re-run for an unchanged source produces zero new
``ContentTranslation`` rows. Staleness / invalidation is handled by the
signals module — source-field edits delete existing translations so the
admin can explicitly re-run.
"""

from __future__ import annotations

import logging
import uuid
from typing import Iterable, List, Sequence, Tuple

from celery import shared_task
from django.utils import timezone

from apps.courses.models import Content, Course, Module
from apps.tenants.models import Tenant
from utils.audit import log_audit

from .models import (
    ContentTranslation,
    SOURCE_TYPE_CONTENT,
    SOURCE_TYPE_COURSE,
    SOURCE_TYPE_MODULE,
    TranslationJobRun,
)
from .providers import (
    TranslationProviderError,
    get_translator,
    looks_like_injection,
)
from .services import (
    compute_source_hash,
    extract_content_fields,
    extract_course_fields,
    extract_module_fields,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_source_language(tenant: Tenant) -> str:
    return getattr(tenant, "default_language", None) or "en"


def _translate_source_row(
    *,
    translator,
    tenant: Tenant,
    source_type: str,
    source_id: uuid.UUID,
    pairs: Sequence[Tuple[str, str]],
    target_languages: Sequence[str],
) -> int:
    """Translate one row's fields across multiple target languages.

    Returns the number of newly-inserted ``ContentTranslation`` rows.
    """
    source_language = _resolve_source_language(tenant)
    new_rows = 0

    for field, text in pairs:
        # Empty fields: skip — nothing to translate.
        if not text:
            continue

        # Prompt-injection heuristics — log but do not block.
        if looks_like_injection(text):
            logger.info(
                "translation.injection_heuristic_matched tenant=%s source=%s:%s field=%s",
                tenant.id, source_type, source_id, field,
            )

        for lang in target_languages:
            src_hash = compute_source_hash(
                text, source_language, lang, getattr(translator, "model", "")
            )

            # Idempotency: skip if an identical row already exists.
            existing = (
                ContentTranslation.objects.all_tenants()
                .filter(
                    tenant=tenant,
                    source_type=source_type,
                    source_id=source_id,
                    field=field,
                    target_language=lang,
                )
                .first()
            )
            if existing and existing.source_hash == src_hash:
                continue

            translated = translator.translate_texts([text], lang, source_language)[0]
            defaults = {
                "translated_text": translated,
                "provider": getattr(translator, "name", ""),
                "model": getattr(translator, "model", ""),
                "source_hash": src_hash,
            }
            _, created = ContentTranslation.objects.all_tenants().update_or_create(
                tenant=tenant,
                source_type=source_type,
                source_id=source_id,
                field=field,
                target_language=lang,
                defaults=defaults,
            )
            if created:
                new_rows += 1

    return new_rows


def _finish_job(job: TranslationJobRun, *, status: str, error: str = "") -> None:
    job.status = status
    job.finished_at = timezone.now()
    if error:
        job.error = error[:5000]
    job.save(
        update_fields=[
            "status",
            "finished_at",
            "error",
            "fields_translated",
        ]
    )


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@shared_task(name="translations.translate_content")
def translate_content(content_id: str, target_languages: List[str], job_id: str | None = None) -> dict:
    """Translate all translatable fields on a Content row.

    Runs in-process for tests (CELERY_TASK_ALWAYS_EAGER) and as a
    background worker in production. On provider outage the job row is
    marked ``failed`` and an audit ``TRANSLATION_FAILED`` is recorded;
    the teacher read path then correctly returns 404.
    """
    job = _get_or_create_job(job_id)
    try:
        content = Content.all_objects.get(id=content_id)
    except Content.DoesNotExist:
        if job is not None:
            _finish_job(job, status=TranslationJobRun.STATUS_FAILED, error="content_not_found")
        return {"status": "failed", "error": "content_not_found"}

    tenant = content.module.course.tenant
    if job is not None:
        job.status = TranslationJobRun.STATUS_RUNNING
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at"])
        log_audit(
            action="TRANSLATION_STARTED",
            target_type="Content",
            target_id=str(content.id),
            target_repr=str(content),
            tenant=tenant,
            changes={"languages": list(target_languages), "job_id": str(job.id)},
        )

    try:
        translator = get_translator()
    except TranslationProviderError as exc:
        if job is not None:
            _finish_job(
                job,
                status=TranslationJobRun.STATUS_FAILED,
                error=f"provider_outage: {exc}",
            )
            log_audit(
                action="TRANSLATION_FAILED",
                target_type="Content",
                target_id=str(content.id),
                target_repr=str(content),
                tenant=tenant,
                changes={"error": str(exc)[:500], "job_id": str(job.id)},
            )
        return {"status": "failed", "error": str(exc)}

    try:
        new_rows = _translate_source_row(
            translator=translator,
            tenant=tenant,
            source_type=SOURCE_TYPE_CONTENT,
            source_id=content.id,
            pairs=extract_content_fields(content),
            target_languages=target_languages,
        )
    except TranslationProviderError as exc:
        if job is not None:
            _finish_job(
                job,
                status=TranslationJobRun.STATUS_FAILED,
                error=f"provider_error: {exc}",
            )
            log_audit(
                action="TRANSLATION_FAILED",
                target_type="Content",
                target_id=str(content.id),
                target_repr=str(content),
                tenant=tenant,
                changes={"error": str(exc)[:500], "job_id": str(job.id)},
            )
        return {"status": "failed", "error": str(exc)}

    if job is not None:
        job.fields_translated = new_rows
        _finish_job(job, status=TranslationJobRun.STATUS_SUCCESS)
        log_audit(
            action="TRANSLATION_FINISHED",
            target_type="Content",
            target_id=str(content.id),
            target_repr=str(content),
            tenant=tenant,
            changes={
                "languages": list(target_languages),
                "new_rows": new_rows,
                "job_id": str(job.id),
            },
        )
    return {"status": "success", "new_rows": new_rows}


@shared_task(name="translations.translate_course")
def translate_course(course_id: str, target_languages: List[str], job_id: str | None = None) -> dict:
    """Translate Course + all Modules + all Contents for target_languages."""
    job = _get_or_create_job(job_id)
    try:
        course = Course.all_objects.get(id=course_id)
    except Course.DoesNotExist:
        if job is not None:
            _finish_job(job, status=TranslationJobRun.STATUS_FAILED, error="course_not_found")
        return {"status": "failed", "error": "course_not_found"}

    tenant = course.tenant

    if job is not None:
        job.status = TranslationJobRun.STATUS_RUNNING
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at"])
        log_audit(
            action="TRANSLATION_STARTED",
            target_type="Course",
            target_id=str(course.id),
            target_repr=str(course),
            tenant=tenant,
            changes={"languages": list(target_languages), "job_id": str(job.id)},
        )

    try:
        translator = get_translator()
    except TranslationProviderError as exc:
        if job is not None:
            _finish_job(
                job,
                status=TranslationJobRun.STATUS_FAILED,
                error=f"provider_outage: {exc}",
            )
            log_audit(
                action="TRANSLATION_FAILED",
                target_type="Course",
                target_id=str(course.id),
                target_repr=str(course),
                tenant=tenant,
                changes={"error": str(exc)[:500], "job_id": str(job.id)},
            )
        return {"status": "failed", "error": str(exc)}

    total_new = 0
    try:
        total_new += _translate_source_row(
            translator=translator,
            tenant=tenant,
            source_type=SOURCE_TYPE_COURSE,
            source_id=course.id,
            pairs=extract_course_fields(course),
            target_languages=target_languages,
        )
        for module in course.modules.all():
            total_new += _translate_source_row(
                translator=translator,
                tenant=tenant,
                source_type=SOURCE_TYPE_MODULE,
                source_id=module.id,
                pairs=extract_module_fields(module),
                target_languages=target_languages,
            )
            for content in module.contents.all():
                total_new += _translate_source_row(
                    translator=translator,
                    tenant=tenant,
                    source_type=SOURCE_TYPE_CONTENT,
                    source_id=content.id,
                    pairs=extract_content_fields(content),
                    target_languages=target_languages,
                )
    except TranslationProviderError as exc:
        if job is not None:
            _finish_job(
                job,
                status=TranslationJobRun.STATUS_FAILED,
                error=f"provider_error: {exc}",
            )
            log_audit(
                action="TRANSLATION_FAILED",
                target_type="Course",
                target_id=str(course.id),
                target_repr=str(course),
                tenant=tenant,
                changes={"error": str(exc)[:500], "job_id": str(job.id)},
            )
        return {"status": "failed", "error": str(exc)}

    if job is not None:
        job.fields_translated = total_new
        _finish_job(job, status=TranslationJobRun.STATUS_SUCCESS)
        log_audit(
            action="TRANSLATION_FINISHED",
            target_type="Course",
            target_id=str(course.id),
            target_repr=str(course),
            tenant=tenant,
            changes={
                "languages": list(target_languages),
                "new_rows": total_new,
                "job_id": str(job.id),
            },
        )
    return {"status": "success", "new_rows": total_new}


def _get_or_create_job(job_id: str | None) -> TranslationJobRun | None:
    if not job_id:
        return None
    try:
        return TranslationJobRun.objects.all_tenants().get(id=job_id)
    except TranslationJobRun.DoesNotExist:
        return None
