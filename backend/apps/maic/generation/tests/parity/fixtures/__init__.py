"""Parity fixtures for ADR-005.

Each sub-directory under here is a fixture:

    fixtures/
        numerator-denominator/
            input.json
            golden_outline.json
            golden_scenes.json
            notes.md

The 5 ADR-005 fixtures land in MAIC-430.A (Session 5) once the
synchronous in-process pipeline is feature-complete (Sessions 3-5).

Skeleton (this file) ships zero fixtures — `list_fixtures()` returns
an empty list. The runner + tests handle that gracefully so the
skeleton commit doesn't fail CI.
"""
