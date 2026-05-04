"""Parity runner — load fixtures, compute drift, fail on threshold.

Per ADR-005 (the gating Phase 4 spec):
    - 5 fixed-input topics (Numerator/Denominator + 4 others)
    - 3 metrics: scene-outline structure, action-count distribution,
      action-type histograms
    - Drift threshold: 15% on each metric

This module ships the reusable bits — fixture loader, drift compute,
threshold check. The actual fixtures + the test functions that call
into the pipeline land at MAIC-430.A (Session 5) and MAIC-430.B
(Session 7).

Fixture layout (per fixture sub-dir under `fixtures/`):
    fixtures/numerator-denominator/
        input.json          — {topic, agent_count, language, level}
        golden_outline.json — upstream Stage-1 reference output
        golden_scenes.json  — upstream Stage-2 reference scenes
        notes.md            — provenance + any caveats

The runner does NOT call upstream live — it reads pre-recorded golden
outputs. This keeps parity tests deterministic + free (no live
TS-pipeline dependency, no per-run OpenAI cost).
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ── Fixture loading ───────────────────────────────────────────────


# `fixtures/` directory lives next to this file.
_FIXTURES_DIR = Path(__file__).parent / "fixtures"


class FixtureNotFound(Exception):
    """Raised when a parity fixture is requested but its directory
    or one of the required files is missing."""


@dataclass(frozen=True)
class ParityFixture:
    """A loaded parity fixture — the input + the golden outputs."""

    name: str
    input: dict[str, Any]
    golden_outline: dict[str, Any]
    golden_scenes: list[dict[str, Any]]


def list_fixtures() -> list[str]:
    """Return all fixture names (sub-directory names under `fixtures/`).

    A directory counts as a fixture only if it contains at least
    `input.json` — empty placeholder dirs are filtered out so the
    skeleton ships without false-positive "fixture found" results.
    """
    if not _FIXTURES_DIR.exists():
        return []
    return sorted(
        d.name
        for d in _FIXTURES_DIR.iterdir()
        if d.is_dir() and (d / "input.json").exists()
    )


def load_fixture(name: str) -> ParityFixture:
    """Load a fixture by directory name.

    Raises:
        FixtureNotFound: directory missing or any required file missing.
    """
    fixture_dir = _FIXTURES_DIR / name
    if not fixture_dir.is_dir():
        raise FixtureNotFound(
            f"parity fixture {name!r} not found at {fixture_dir}"
        )

    paths = {
        "input": fixture_dir / "input.json",
        "golden_outline": fixture_dir / "golden_outline.json",
        "golden_scenes": fixture_dir / "golden_scenes.json",
    }
    for key, path in paths.items():
        if not path.is_file():
            raise FixtureNotFound(
                f"parity fixture {name!r}: missing {path.name} "
                f"(expected at {path})"
            )

    with paths["input"].open("r") as f:
        input_data = json.load(f)
    with paths["golden_outline"].open("r") as f:
        golden_outline = json.load(f)
    with paths["golden_scenes"].open("r") as f:
        golden_scenes = json.load(f)

    return ParityFixture(
        name=name,
        input=input_data,
        golden_outline=golden_outline,
        golden_scenes=golden_scenes,
    )


# ── Drift compute ──────────────────────────────────────────────────


@dataclass(frozen=True)
class DriftMetrics:
    """Per-metric drift between an actual run and a golden output.

    Each value is in [0, 1] — interpret as a fraction (0.15 = 15%).
    The ADR-005 gate fails if ANY value exceeds 0.15.
    """

    outline_structure_drift: float
    action_count_drift: float
    action_type_histogram_drift: float

    @property
    def max_drift(self) -> float:
        """Worst-case drift across the three metrics."""
        return max(
            self.outline_structure_drift,
            self.action_count_drift,
            self.action_type_histogram_drift,
        )

    def passes(self, threshold: float = 0.15) -> bool:
        """ADR-005: any metric over threshold fails the gate."""
        return self.max_drift <= threshold


def _outline_structure_signature(scenes: list[dict[str, Any]]) -> tuple[str, ...]:
    """The ordered tuple of scene types — the structural signature
    Stage 1's outline produces. Two outlines that differ only in a
    single scene's `type` will produce different signatures.
    """
    return tuple(s.get("type", "unknown") for s in scenes)


def _hamming_drift(a: tuple[str, ...], b: tuple[str, ...]) -> float:
    """Hamming distance normalised to [0, 1]. Returns 1.0 when the
    tuples have different lengths (treat length mismatch as max drift
    on the structural axis).
    """
    if len(a) != len(b):
        return 1.0
    if not a:
        return 0.0
    diffs = sum(1 for x, y in zip(a, b) if x != y)
    return diffs / len(a)


def _action_count_drift(
    actual: list[list[Any]], golden: list[list[Any]]
) -> float:
    """Mean absolute percentage difference in per-scene action counts.

    Both args are lists-of-action-lists, one per scene. Returns the
    average per-scene drift; if scene counts differ, returns 1.0.
    """
    if len(actual) != len(golden):
        return 1.0
    if not golden:
        return 0.0
    diffs: list[float] = []
    for a_scene, g_scene in zip(actual, golden):
        a_count = len(a_scene)
        g_count = len(g_scene)
        if g_count == 0 and a_count == 0:
            diffs.append(0.0)
        elif g_count == 0:
            diffs.append(1.0)  # divide-by-zero protection
        else:
            diffs.append(abs(a_count - g_count) / g_count)
    return sum(diffs) / len(diffs)


def _histogram_drift(
    actual_actions: list[dict[str, Any]],
    golden_actions: list[dict[str, Any]],
) -> float:
    """Total-variation distance between two action-type histograms.

    Flatten both lists into per-type counts, normalise to probability
    distributions, return half the L1 distance — bounded in [0, 1].
    """
    if not actual_actions and not golden_actions:
        return 0.0

    a_hist: Counter[str] = Counter(
        a.get("type", a.get("name", "unknown")) for a in actual_actions
    )
    g_hist: Counter[str] = Counter(
        a.get("type", a.get("name", "unknown")) for a in golden_actions
    )
    a_total = sum(a_hist.values()) or 1
    g_total = sum(g_hist.values()) or 1
    keys = set(a_hist) | set(g_hist)
    l1 = sum(
        abs(a_hist[k] / a_total - g_hist[k] / g_total)
        for k in keys
    )
    return l1 / 2.0


def compute_drift(
    actual_scenes: list[dict[str, Any]],
    golden_scenes: list[dict[str, Any]],
) -> DriftMetrics:
    """Compute all 3 ADR-005 drift metrics for a generated-vs-golden
    scene pair.

    Each scene is expected to have:
        - `type`: scene type ('slide' | 'quiz' | 'pbl' | 'interactive')
        - `actions`: list of action dicts (each with at least `type` or `name`)

    Args:
        actual_scenes: output of our pipeline (port).
        golden_scenes: pre-recorded upstream output.

    Returns:
        DriftMetrics with per-metric values in [0, 1].
    """
    structure_drift = _hamming_drift(
        _outline_structure_signature(actual_scenes),
        _outline_structure_signature(golden_scenes),
    )
    action_count = _action_count_drift(
        [s.get("actions") or [] for s in actual_scenes],
        [s.get("actions") or [] for s in golden_scenes],
    )
    flat_actual = [a for s in actual_scenes for a in (s.get("actions") or [])]
    flat_golden = [a for s in golden_scenes for a in (s.get("actions") or [])]
    histogram = _histogram_drift(flat_actual, flat_golden)
    return DriftMetrics(
        outline_structure_drift=structure_drift,
        action_count_drift=action_count,
        action_type_histogram_drift=histogram,
    )
