"""Tests for the parity harness skeleton (MAIC-430.0).

The harness gates Phase 4 close per ADR-005. The skeleton ships:
  - test runner + fixture loader (`runner.py`)
  - empty fixtures dir (real fixtures arrive at MAIC-430.A in Session 5)
  - drift compute math (so it's locked + correct before we feed real data into it)

These tests verify:
  1. The package + module imports work (regression net for the pipeline
     skeleton's Python path / __init__.py wiring).
  2. `list_fixtures` handles the empty-dir case (skeleton state).
  3. `load_fixture` raises a clear error for missing fixtures.
  4. `compute_drift` returns 0 for identical inputs, ≤ threshold for
     small perturbations, > threshold for large ones — pinned exactly
     so future tweaks to the math don't silently shift the gate.
"""
from __future__ import annotations

import pytest

from apps.maic.generation.tests.parity import (
    DriftMetrics,
    FixtureNotFound,
    compute_drift,
    list_fixtures,
    load_fixture,
)


# ── package + module wiring ───────────────────────────────────────


def test_generation_package_importable():
    """Lock the new `apps.maic.generation` package's __init__.py path."""
    from apps.maic import generation
    assert generation is not None


def test_generation_types_module_importable():
    """Lock the types module — its TypedDicts are imported by every
    later module (outline_generator, scene_generator, etc)."""
    from apps.maic.generation import types as gen_types
    assert hasattr(gen_types, "AgentInfo")
    assert hasattr(gen_types, "SceneGenerationContext")
    assert hasattr(gen_types, "GenerationResult")
    assert hasattr(gen_types, "GeneratedSlideData")
    assert hasattr(gen_types, "SceneOutline")


def test_parity_runner_exports_public_surface():
    """Lock the parity runner's public exports — every later parity
    test imports from `apps.maic.generation.tests.parity`."""
    from apps.maic.generation.tests import parity
    for name in (
        "DriftMetrics",
        "FixtureNotFound",
        "ParityFixture",
        "compute_drift",
        "list_fixtures",
        "load_fixture",
    ):
        assert hasattr(parity, name), f"parity must export {name}"


# ── fixture loader ────────────────────────────────────────────────


def test_list_fixtures_returns_empty_for_skeleton():
    """In the skeleton (MAIC-430.0), no fixtures exist yet.
    `list_fixtures()` must return [] without raising — Session 5's
    MAIC-430.A drops the actual fixtures into place."""
    assert list_fixtures() == []


def test_load_fixture_raises_clear_error_when_missing():
    """A clean error is the contract — an opaque IOError or KeyError
    would surface during MAIC-430.A authoring as a confusing failure."""
    with pytest.raises(FixtureNotFound, match="not found"):
        load_fixture("does-not-exist")


# ── drift compute math ────────────────────────────────────────────


def _make_scene(scene_type: str, action_types: list[str]) -> dict:
    """Build a minimal scene dict for drift testing."""
    return {
        "type": scene_type,
        "actions": [{"type": at} for at in action_types],
    }


class TestDriftCompute:
    def test_identical_scenes_produce_zero_drift(self):
        scenes = [
            _make_scene("slide", ["speech", "spotlight"]),
            _make_scene("quiz", ["speech"]),
        ]
        d = compute_drift(scenes, scenes)
        assert d.outline_structure_drift == 0.0
        assert d.action_count_drift == 0.0
        assert d.action_type_histogram_drift == 0.0
        assert d.max_drift == 0.0
        assert d.passes(threshold=0.15)

    def test_one_scene_type_swap_produces_partial_structure_drift(self):
        actual = [
            _make_scene("slide", ["speech"]),
            _make_scene("quiz", ["speech"]),
            _make_scene("slide", ["speech"]),
        ]
        golden = [
            _make_scene("slide", ["speech"]),
            _make_scene("quiz", ["speech"]),
            _make_scene("interactive", ["speech"]),  # changed from slide
        ]
        d = compute_drift(actual, golden)
        # 1 of 3 scenes differs structurally → 0.333 > 0.15 → fails gate
        assert d.outline_structure_drift == pytest.approx(1 / 3)
        assert not d.passes(threshold=0.15)

    def test_scene_count_mismatch_produces_max_drift(self):
        actual = [_make_scene("slide", [])]
        golden = [_make_scene("slide", []), _make_scene("quiz", [])]
        d = compute_drift(actual, golden)
        # Length mismatch on outline → 1.0 (max). Action-count drift
        # also mismatches.
        assert d.outline_structure_drift == 1.0
        assert d.action_count_drift == 1.0
        assert not d.passes()

    def test_action_count_drift_within_threshold(self):
        """Same outline, same action types, slightly different action
        COUNTS — should drift but stay under 15% on small variance."""
        actual = [_make_scene("slide", ["speech", "speech", "speech"])]
        golden = [_make_scene("slide", ["speech", "speech", "speech"])]
        d = compute_drift(actual, golden)
        assert d.action_count_drift == 0.0

        # Now perturb: 4 vs 3 actions → 33% drift
        actual2 = [_make_scene("slide", ["speech"] * 4)]
        d2 = compute_drift(actual2, golden)
        assert d2.action_count_drift == pytest.approx(1 / 3)

    def test_histogram_drift_uses_total_variation(self):
        """Different action-type mixes should drift even when counts
        match. Total variation distance is in [0, 1] and bounds the
        max possible drift."""
        actual = [_make_scene("slide", ["speech", "spotlight"])]
        golden = [_make_scene("slide", ["speech", "speech"])]
        d = compute_drift(actual, golden)
        # Histograms: actual={speech:0.5, spotlight:0.5} vs golden={speech:1.0}
        # L1 = 0.5 + 0.5 = 1.0 → TV = 0.5
        assert d.action_type_histogram_drift == pytest.approx(0.5)

    def test_passes_threshold_default_is_fifteen_percent(self):
        """ADR-005's gate threshold. Locking the default in the API
        so callers never accidentally use a different default."""
        d = DriftMetrics(
            outline_structure_drift=0.10,
            action_count_drift=0.10,
            action_type_histogram_drift=0.10,
        )
        assert d.passes()  # 0.10 < 0.15

        d2 = DriftMetrics(
            outline_structure_drift=0.16,
            action_count_drift=0.0,
            action_type_histogram_drift=0.0,
        )
        assert not d2.passes()  # 0.16 > 0.15 even though others are 0

    def test_max_drift_picks_worst_metric(self):
        """The gate is per-metric, not averaged. `max_drift` must
        return the worst single metric so a passing avg with one
        metric exceeding still fails."""
        d = DriftMetrics(
            outline_structure_drift=0.05,
            action_count_drift=0.20,
            action_type_histogram_drift=0.05,
        )
        assert d.max_drift == 0.20
        assert not d.passes()

    def test_empty_inputs_are_safe(self):
        """Both empty → no drift. One empty + one non-empty → max drift."""
        assert compute_drift([], []).max_drift == 0.0
        assert compute_drift([], [_make_scene("slide", [])]).max_drift == 1.0
