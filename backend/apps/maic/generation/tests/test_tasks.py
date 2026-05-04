"""Tests for `apps.maic.generation.tasks` (MAIC-428.1).

Celery tasks run synchronously in tests via CELERY_TASK_ALWAYS_EAGER
(set in pytest fixtures). The chain entry point + each task is covered:

  - create_job_session → row inserted with the right shape.
  - outline_task → marks in_progress, emits outline_done, returns the
    chain payload.
  - scene_dispatch_task → runs Stage 2 against a stubbed pipeline,
    persists scenes-in-progress.
  - finalize_task → marks succeeded, fills result, completed_at set.
  - mark_job_failed → flips status=failed, persists error message.

Production-real (no mocks of Django ORM, no Celery mocking — only the
LLM call is mocked because real OpenRouter is gated by env var).
"""
from __future__ import annotations

from unittest.mock import patch

import json
import pytest
from django.contrib.auth import get_user_model

from apps.maic.generation.tasks import (
    create_job_session,
    enqueue_generation_chain,
    finalize_task,
    mark_job_failed,
    outline_task,
    scene_dispatch_task,
)
from apps.maic.generation.tests.parity.llm_router import PromptRoutedStub
from apps.maic.models import MaicGenerationJob
from apps.tenants.models import Tenant


@pytest.fixture
def tenant(db):
    """A bare Tenant row for the FK on MaicGenerationJob."""
    return Tenant.objects.create(name="test-tenant", slug="test-tenant")


@pytest.fixture
def user(db, tenant):
    User = get_user_model()
    return User.objects.create_user(
        email="test@example.com",
        password="x",
    )


@pytest.fixture
def parity_responses():
    """Re-use the numerator-denominator parity fixture's LLM responses
    so the chain has realistic shape-correct inputs for every prompt
    template the pipeline calls into."""
    from pathlib import Path
    fp = (
        Path(__file__).parent
        / "parity" / "fixtures" / "numerator-denominator" / "llm_responses.json"
    )
    return json.loads(fp.read_text())


# ── create_job_session ────────────────────────────────────────────


def test_create_job_session_inserts_row(db, tenant, user):
    requirements = {"topic": "fractions", "agentCount": 4, "language": "English"}
    job = create_job_session(
        tenant_id=tenant.id,
        user_id=user.id,
        requirements=requirements,
    )
    # Reload to ensure row is committed.
    saved = MaicGenerationJob.objects.get(pk=job.id)
    assert saved.tenant_id == tenant.id
    assert saved.created_by_id == user.id
    assert saved.requirements == requirements
    assert saved.status == MaicGenerationJob.STATUS_PENDING
    assert saved.progress["stage"] == 0


def test_create_job_session_tolerates_no_user(db, tenant):
    """user_id=None is allowed — internal/dev jobs may not have a
    bound user."""
    job = create_job_session(
        tenant_id=tenant.id,
        user_id=None,
        requirements={"topic": "x"},
    )
    saved = MaicGenerationJob.objects.get(pk=job.id)
    assert saved.created_by_id is None


def test_job_id_is_short_and_url_safe(db, tenant):
    job = create_job_session(
        tenant_id=tenant.id, user_id=None, requirements={}
    )
    # nanoid up to 12 chars per pipeline_runner._generate_session_id
    # (token_urlsafe(9) yields 12 chars before stripping `-` / `_`,
    # so the alphanumeric output may land at 10-12).
    assert 8 <= len(job.id) <= 12
    assert all(c.isalnum() for c in job.id)


# ── outline_task ──────────────────────────────────────────────────


def test_outline_task_marks_in_progress_and_returns_payload(
    db, tenant, parity_responses
):
    job = create_job_session(
        tenant_id=tenant.id,
        user_id=None,
        requirements={
            "topic": "Numerator and Denominator",
            "agentCount": 4,
            "language": "English",
            "level": "beginner",
            "languageModelId": "stub",
        },
    )
    router = PromptRoutedStub(parity_responses)

    with patch(
        "apps.maic.generation.outline_generator.generate_text", new=router
    ):
        payload = outline_task(job_id=job.id)

    saved = MaicGenerationJob.objects.get(pk=job.id)
    assert saved.status == MaicGenerationJob.STATUS_IN_PROGRESS
    assert saved.progress["stage"] == 1
    assert saved.result["outlines"]
    assert saved.result["languageDirective"]
    assert payload["job_id"] == job.id
    assert len(payload["outlines"]) == 10
    assert payload["languageDirective"]


def test_outline_task_raises_on_pipeline_error(db, tenant):
    job = create_job_session(
        tenant_id=tenant.id,
        user_id=None,
        requirements={"topic": "T", "languageModelId": "stub"},
    )

    async def _broken(*args, **kwargs):
        return "nope no JSON anywhere"

    with patch(
        "apps.maic.generation.outline_generator.generate_text",
        new=_broken,
    ):
        with pytest.raises(RuntimeError):
            outline_task(job_id=job.id)


# ── scene_dispatch_task ───────────────────────────────────────────


def test_scene_dispatch_task_runs_stage2_inline(
    db, tenant, parity_responses
):
    job = create_job_session(
        tenant_id=tenant.id,
        user_id=None,
        requirements={
            "topic": "Numerator and Denominator",
            "agentCount": 4,
            "language": "English",
            "languageModelId": "stub",
        },
    )
    router = PromptRoutedStub(parity_responses)

    with patch(
        "apps.maic.generation.outline_generator.generate_text", new=router
    ):
        stage1_payload = outline_task(job_id=job.id)

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=router
    ):
        stage2_payload = scene_dispatch_task(stage1_payload)

    assert stage2_payload["job_id"] == job.id
    assert len(stage2_payload["scenes"]) == 10


# ── finalize_task ─────────────────────────────────────────────────


def test_finalize_task_marks_succeeded(db, tenant):
    job = create_job_session(
        tenant_id=tenant.id, user_id=None, requirements={}
    )
    job.result = {"outlines": [{"order": 1}], "languageDirective": "x"}
    job.save()

    finalize_task({"job_id": job.id, "scenes": [{"id": "s1"}, {"id": "s2"}]})

    saved = MaicGenerationJob.objects.get(pk=job.id)
    assert saved.status == MaicGenerationJob.STATUS_SUCCEEDED
    assert saved.result["scenes"] == [{"id": "s1"}, {"id": "s2"}]
    assert saved.result["outlines"]  # preserved from earlier stage
    assert saved.completed_at is not None
    assert saved.progress["stage"] == 3


# ── mark_job_failed ───────────────────────────────────────────────


def test_mark_job_failed_records_status(db, tenant):
    job = create_job_session(
        tenant_id=tenant.id, user_id=None, requirements={}
    )
    exc = RuntimeError("boom")
    mark_job_failed(request=None, exc=exc, traceback=None, job_id=job.id)

    saved = MaicGenerationJob.objects.get(pk=job.id)
    assert saved.status == MaicGenerationJob.STATUS_FAILED
    assert "boom" in saved.error
    assert saved.completed_at is not None


def test_mark_job_failed_tolerates_missing_job(db):
    """Idempotent — if the job row was already deleted (e.g. tenant
    purge), the failure handler logs + returns rather than raising."""
    mark_job_failed(
        request=None,
        exc=RuntimeError("ignored"),
        traceback=None,
        job_id="does-not-exist",
    )


# ── Chain integration (eager mode) ────────────────────────────────


def test_enqueue_generation_chain_runs_end_to_end(
    db, settings, tenant, parity_responses
):
    """Eager-mode chain: outline_task → scene_dispatch → finalize all
    run in-process. Verifies that the chain plumbing is wired end-to-end."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True

    job = create_job_session(
        tenant_id=tenant.id,
        user_id=None,
        requirements={
            "topic": "Numerator and Denominator",
            "agentCount": 4,
            "language": "English",
            "languageModelId": "stub",
        },
    )

    router = PromptRoutedStub(parity_responses)

    with patch(
        "apps.maic.generation.outline_generator.generate_text", new=router
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=router
        ):
            enqueue_generation_chain(job.id)

    saved = MaicGenerationJob.objects.get(pk=job.id)
    assert saved.status == MaicGenerationJob.STATUS_SUCCEEDED
    assert len(saved.result["scenes"]) == 10
    assert saved.completed_at is not None
