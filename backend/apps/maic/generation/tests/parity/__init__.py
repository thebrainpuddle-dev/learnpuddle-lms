"""Parity test harness — gates Phase 4 close per ADR-005.

Compares our Python port against upstream's reference outputs across
5 fixed-input topics. Drift > 15% on any of the 3 metrics fails the
gate.

Metrics (per ADR-005):
    1. scene-outline structure   (count + ordering of scene types)
    2. action-count distribution (per-scene action totals)
    3. action-type histograms    (slide vs quiz vs interactive vs ...)

Two passes:
    - Pass A — module-level synchronous in-process pipeline (Session 5
      gate; catches drift before Celery wraps the call).
    - Pass B — end-to-end through Celery + WS (Session 7 gate).

Fixtures live in `fixtures/` — one sub-directory per topic, each
holding the input + golden output JSON. The "Numerator/Denominator"
fixture is the named one in ADR-005; the other 4 cover STEM,
humanities, languages, and a mixed topic.

This skeleton (MAIC-430.0) ships the runner + fixture loader; the
fixtures + drift assertions land at MAIC-430.A (Pass A, Session 5)
and MAIC-430.B (Pass B, Session 7).
"""

from apps.maic.generation.tests.parity.runner import (
    DriftMetrics,
    FixtureNotFound,
    ParityFixture,
    compute_drift,
    list_fixtures,
    load_fixture,
)

__all__ = [
    "DriftMetrics",
    "FixtureNotFound",
    "ParityFixture",
    "compute_drift",
    "list_fixtures",
    "load_fixture",
]
