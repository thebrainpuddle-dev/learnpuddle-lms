"""Pass-B parity test (MAIC-430.B) — Phase 4 Session 7 GATE.

Per ADR-005 + the Phase-4 plan: Pass B runs the same 5 fixtures
through the **Celery chain + WS plumbing** that lands in Session 6
(MAIC-428.x). Same 3 drift metrics, same 15% threshold. The point of
Pass B is to catch regressions introduced by the orchestration layer
that wouldn't surface in Pass A's in-process pipeline.

  Pass A (MAIC-430.A): module-level synchronous pipeline directly
                       (no Celery, no WS). Locks the in-process
                       behavior.

  Pass B (this module): same fixtures end-to-end through
                        enqueue_generation_chain + the eager-mode
                        chord. Asserts the orchestration layer
                        doesn't drop or reorder scenes / actions.

Test environment:
  - CELERY_TASK_ALWAYS_EAGER=True so the chain runs in-process
    during the test (no Celery broker needed).
  - PromptRoutedStub replaces generate_text in both outline_generator
    and scene_generator scopes — same canned LLM responses Pass A
    uses.
  - The job row state + final result is read back from the DB after
    enqueue_generation_chain completes synchronously.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from apps.maic.generation.tests.parity import (
    compute_drift,
    list_fixtures,
    load_fixture,
)
from apps.maic.generation.tests.parity.llm_router import PromptRoutedStub


_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_DRIFT_THRESHOLD: float = 0.15  # ADR-005


def _fixture_dir(name: str) -> Path:
    return _FIXTURES_DIR / name


def _has_goldens(name: str) -> bool:
    d = _fixture_dir(name)
    return (
        (d / "golden_outline.json").is_file()
        and (d / "golden_scenes.json").is_file()
    )


def _has_responses(name: str) -> bool:
    return (_fixture_dir(name) / "llm_responses.json").is_file()


_EXPECTED_FIXTURES = {
    "numerator-denominator",
    "photosynthesis-stem",
    "french-revolution-humanities",
    "spanish-greetings-languages",
    "data-types-mixed",
}


@pytest.fixture
def tenant(db):
    from apps.tenants.models import Tenant
    return Tenant.objects.create(name="parity-tenant", slug="parity-tenant")


@pytest.mark.parametrize("fixture_name", sorted(_EXPECTED_FIXTURES))
def test_pass_b_drift_under_threshold(
    fixture_name, db, settings, tenant
):
    """End-to-end through Celery: enqueue the chain in eager mode +
    verify the resulting MaicGenerationJob.result.scenes drifts <15%
    from the fixture's golden."""
    if not _has_goldens(fixture_name):
        pytest.skip(
            f"{fixture_name}: goldens not yet recorded "
            "(see notes.md — activated by MAIC-430.B)"
        )
    if not _has_responses(fixture_name):
        pytest.skip(
            f"{fixture_name}: llm_responses.json not present"
        )

    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True

    fixture = load_fixture(fixture_name)
    responses = json.loads(
        (_fixture_dir(fixture_name) / "llm_responses.json").read_text()
    )
    router = PromptRoutedStub(responses)

    from apps.maic.generation.tasks import (
        create_job_session,
        enqueue_generation_chain,
    )
    from apps.maic.models import MaicGenerationJob

    job = create_job_session(
        tenant_id=tenant.id,
        user_id=None,
        requirements={
            **fixture.input,
            "languageModelId": "stub",
        },
    )

    with patch(
        "apps.maic.generation.outline_generator.generate_text", new=router
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=router
        ):
            enqueue_generation_chain(job.id)

    saved = MaicGenerationJob.objects.all_tenants().get(pk=job.id)
    assert saved.status == MaicGenerationJob.STATUS_SUCCEEDED, (
        f"chain failed for {fixture_name}: status={saved.status}, "
        f"error={saved.error}"
    )
    actual_scenes = saved.result.get("scenes", [])

    drift = compute_drift(actual_scenes, fixture.golden_scenes)
    assert drift.passes(_DRIFT_THRESHOLD), (
        f"{fixture_name} Pass-B drift exceeds {_DRIFT_THRESHOLD * 100:.0f}%:\n"
        f"  outline_structure_drift = {drift.outline_structure_drift:.3f}\n"
        f"  action_count_drift      = {drift.action_count_drift:.3f}\n"
        f"  action_type_histogram   = {drift.action_type_histogram_drift:.3f}\n"
        f"  max                     = {drift.max_drift:.3f}\n"
    )


def test_pass_b_named_fixture_bit_identical_to_pass_a(
    db, settings, tenant
):
    """The Celery orchestration layer must not change output: Pass-B
    drift on the named fixture must be exactly 0.0 (same fixture
    that locks Pass-A at 0.0). If this fails, MAIC-428.x introduced
    a behavior diff vs the in-process path — block Phase 4 close."""
    if not _has_goldens("numerator-denominator"):
        pytest.skip("named fixture missing goldens")

    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True

    fixture = load_fixture("numerator-denominator")
    responses = json.loads(
        (_fixture_dir("numerator-denominator") / "llm_responses.json")
        .read_text()
    )
    router = PromptRoutedStub(responses)

    from apps.maic.generation.tasks import (
        create_job_session,
        enqueue_generation_chain,
    )
    from apps.maic.models import MaicGenerationJob

    job = create_job_session(
        tenant_id=tenant.id,
        user_id=None,
        requirements={**fixture.input, "languageModelId": "stub"},
    )

    with patch(
        "apps.maic.generation.outline_generator.generate_text", new=router
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=router
        ):
            enqueue_generation_chain(job.id)

    saved = MaicGenerationJob.objects.all_tenants().get(pk=job.id)
    assert saved.status == MaicGenerationJob.STATUS_SUCCEEDED
    actual = saved.result["scenes"]

    drift = compute_drift(actual, fixture.golden_scenes)
    assert drift.outline_structure_drift == 0.0
    assert drift.action_count_drift == 0.0
    assert drift.action_type_histogram_drift == 0.0
