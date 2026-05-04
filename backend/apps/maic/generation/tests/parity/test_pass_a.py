"""Pass-A parity test (MAIC-430.A) — Phase 4 Session 5 HARD GATE.

Per ADR-005:
    - 5 fixed-input topics (numerator-denominator + 4 covering STEM,
      humanities, languages, mixed)
    - 3 metrics: scene-outline structure, action-count distribution,
      action-type histograms
    - Drift threshold: 15% on each metric

This module runs the full **module-level synchronous in-process**
pipeline (no Celery + no WS — those are Session 6 wrappers) against
each fixture and asserts drift below the threshold. If this fails,
**do NOT proceed to Session 6** — debug + fix in Sessions 3-5 first.

Fixtures missing `golden_outline.json` or `golden_scenes.json` SKIP
with a clear marker. The named fixture (numerator-denominator) MUST
have goldens — it's the named ADR-005 fixture and the gate's primary
guard. The other 4 ship as input-only skeletons until MAIC-430.B
(Pass B, Session 7) records real-OpenRouter goldens.

Determinism: fixtures with `llm_responses.json` use a
`PromptRoutedStub` that replaces `generate_text` — no real LLM call,
no temperature, no provider non-determinism. The test passing locks
"current pipeline produces what the fixture expects".
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from apps.maic.generation.pipeline_runner import (
    create_generation_session,
    run_generation_pipeline,
)
from apps.maic.generation.tests.parity import (
    DriftMetrics,
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


# ── Sanity: fixture inventory matches plan ────────────────────────


_EXPECTED_FIXTURES = {
    "numerator-denominator",  # ADR-005 named
    "photosynthesis-stem",
    "french-revolution-humanities",
    "spanish-greetings-languages",
    "data-types-mixed",
}


def test_fixture_inventory_matches_plan():
    """Lock the 5-fixture set per ADR-005 + Phase-4 plan."""
    actual = set(list_fixtures())
    missing = _EXPECTED_FIXTURES - actual
    extra = actual - _EXPECTED_FIXTURES
    assert not missing, f"missing fixtures: {sorted(missing)}"
    assert not extra, f"unexpected fixtures: {sorted(extra)}"


def test_named_fixture_must_have_goldens():
    """numerator-denominator is the ADR-005 named fixture — its
    goldens MUST exist. The other 4 may skip (input-only) until
    MAIC-430.B records real-LLM goldens."""
    assert _has_goldens("numerator-denominator"), (
        "numerator-denominator goldens are required for the Phase-4 "
        "Session-5 hard gate. Re-record via the script in MAIC-430.A "
        "if accidentally deleted."
    )


# ── Pass-A drift gate ──────────────────────────────────────────────


@pytest.mark.parametrize("fixture_name", sorted(_EXPECTED_FIXTURES))
def test_pass_a_drift_under_threshold(fixture_name):
    """The hard gate: each fixture's pipeline output must drift less
    than 15% from its golden on every ADR-005 metric.

    Fixtures missing goldens skip — the named fixture is asserted
    above to have goldens, so this skip path only affects the 4
    skeleton fixtures awaiting MAIC-430.B."""
    if not _has_goldens(fixture_name):
        pytest.skip(
            f"{fixture_name}: goldens not yet recorded "
            "(see notes.md — activated by MAIC-430.B)"
        )
    if not _has_responses(fixture_name):
        pytest.skip(
            f"{fixture_name}: llm_responses.json not present — "
            "the synthetic-LLM path requires it. Real-LLM Pass-B "
            "(MAIC-430.B) reads goldens against live OpenRouter "
            "instead."
        )

    fixture = load_fixture(fixture_name)
    responses = json.loads(
        (_fixture_dir(fixture_name) / "llm_responses.json").read_text()
    )
    router = PromptRoutedStub(responses)

    import asyncio

    async def _run() -> list[dict]:
        session = create_generation_session(fixture.input)
        with patch(
            "apps.maic.generation.scene_generator.generate_text",
            new=router,
        ):
            with patch(
                "apps.maic.generation.outline_generator.generate_text",
                new=router,
            ):
                result = await run_generation_pipeline(
                    session, language_model_id="stub"
                )
        assert result.get("success"), (
            f"pipeline failed: {result.get('error')}"
        )
        return session["scenes"]

    actual_scenes = asyncio.get_event_loop().run_until_complete(_run())

    drift = compute_drift(actual_scenes, fixture.golden_scenes)
    assert drift.passes(_DRIFT_THRESHOLD), (
        f"{fixture_name} parity drift exceeds {_DRIFT_THRESHOLD * 100:.0f}%:\n"
        f"  outline_structure_drift = {drift.outline_structure_drift:.3f}\n"
        f"  action_count_drift      = {drift.action_count_drift:.3f}\n"
        f"  action_type_histogram   = {drift.action_type_histogram_drift:.3f}\n"
        f"  max                     = {drift.max_drift:.3f}\n"
        f"\nIf this is a deliberate change, re-record goldens; "
        f"otherwise debug the pipeline regression first."
    )


def test_pass_a_drift_metrics_lock_baseline():
    """Lock the named fixture's drift to ~0 (deterministic stub
    pipeline) — catches a regression that splits scenes incorrectly
    OR drops actions silently. This is a stronger assertion than the
    15% threshold; it verifies the pipeline produces BIT-IDENTICAL
    structure to what the goldens captured."""
    if not _has_goldens("numerator-denominator"):
        pytest.skip("named fixture missing goldens (see test above)")

    fixture = load_fixture("numerator-denominator")
    responses = json.loads(
        (_fixture_dir("numerator-denominator") / "llm_responses.json")
        .read_text()
    )
    router = PromptRoutedStub(responses)

    import asyncio

    async def _run() -> list[dict]:
        session = create_generation_session(fixture.input)
        with patch(
            "apps.maic.generation.scene_generator.generate_text",
            new=router,
        ):
            with patch(
                "apps.maic.generation.outline_generator.generate_text",
                new=router,
            ):
                await run_generation_pipeline(
                    session, language_model_id="stub"
                )
        return session["scenes"]

    actual = asyncio.get_event_loop().run_until_complete(_run())
    drift = compute_drift(actual, fixture.golden_scenes)

    # Outline structure + action counts MUST be exact (same fixture,
    # same pipeline, same router → bit-identical scene shapes).
    assert drift.outline_structure_drift == 0.0, (
        f"outline structure drift on the named fixture should be 0 "
        f"under deterministic stub; got {drift.outline_structure_drift}"
    )
    assert drift.action_count_drift == 0.0, (
        f"action count drift on the named fixture should be 0 "
        f"under deterministic stub; got {drift.action_count_drift}"
    )
    # Action-type histogram should be 0 too — same actions per scene.
    assert drift.action_type_histogram_drift == 0.0, (
        f"action-type histogram drift on the named fixture should be 0 "
        f"under deterministic stub; got "
        f"{drift.action_type_histogram_drift}"
    )


# ── DriftMetrics unit tests ───────────────────────────────────────


def test_drift_metrics_pass_when_under_threshold():
    metrics = DriftMetrics(
        outline_structure_drift=0.10,
        action_count_drift=0.05,
        action_type_histogram_drift=0.12,
    )
    assert metrics.passes(0.15)
    assert not metrics.passes(0.05)


def test_drift_metrics_max_drift():
    metrics = DriftMetrics(
        outline_structure_drift=0.10,
        action_count_drift=0.20,
        action_type_histogram_drift=0.05,
    )
    assert metrics.max_drift == 0.20
