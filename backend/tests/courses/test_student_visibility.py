"""PERF-P0-4 cutover (2026-04-26) — ``_student_can_view_classroom`` reads
audioManifest from ``composed_content`` (shards) only.

Originally these tests guarded the AUDIT-2026-04-25-9 per-key legacy
fallback that reached past a partially-populated ``content_meta`` shard
to the legacy ``content.audioManifest``. After the PERF-P0-4 cutover the
dual-write was retired — every writer (publish handler, chord callback,
fill-images task) now writes ``audioManifest`` to ``content_meta``
exclusively, and migration 0043 backfilled every existing row. So the
helper no longer needs to fall back per key inside the legacy field.

Behaviour after cutover:
- If the row has ANY shard populated (the 100% case post-backfill), the
  helper reads ``audioManifest`` from ``content_meta`` only.
- If the row has NO shards populated (legacy-only — should not happen
  in practice), ``composed_content`` falls back to the legacy ``content``
  field as a courtesy belt-and-suspenders.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.courses.maic_views import _student_can_view_classroom


class _SectionQueryset(list):
    def exists(self) -> bool:
        return bool(self)


def _make_user(section=None):
    return SimpleNamespace(section_fk=section)


def _compose(content_meta, content):
    """Replicate ``MAICClassroom.composed_content`` for the test mocks.

    Mirrors the property in ``maic_models.py`` (PERF-P0-4 cutover behaviour):
    if ANY shard is populated, return shard data only; otherwise fall back
    to the legacy ``content`` field. We only model the keys this test
    cares about (``audioManifest``).
    """
    content_meta = content_meta or {}
    if content_meta:
        out: dict = {}
        out.update(content_meta)
        return out
    return content or {}


def _make_classroom(*, content_meta=None, content=None, sections=()):
    """Build a MagicMock classroom with explicit shard + legacy values.

    ``composed_content`` is set to the value the real property would
    return for this combination of shard + legacy data, so the helper's
    shard-only read path is exercised exactly as it would be in production.
    """
    classroom = MagicMock()
    classroom.status = "READY"
    classroom.is_public = True
    classroom.content_meta = content_meta
    classroom.content = content
    classroom.composed_content = _compose(content_meta, content)
    classroom.assigned_sections.all.return_value = _SectionQueryset(sections)
    return classroom


# ---------------------------------------------------------------------------
# (a) Shard-only manifest: content_meta carries audioManifest, legacy empty.
# ---------------------------------------------------------------------------


def test_visibility_with_shard_only_manifest_ready():
    """``content_meta`` populated with ready manifest; legacy empty.
    Visibility must be True — the shard is the source of truth."""
    classroom = _make_classroom(
        content_meta={"audioManifest": {"status": "ready"}},
        content={},  # legacy empty
    )
    assert _student_can_view_classroom(_make_user(), classroom) is True


# ---------------------------------------------------------------------------
# (b) Legacy-only manifest: content_meta empty/missing key, legacy has it.
# ---------------------------------------------------------------------------


def test_visibility_with_legacy_only_manifest_ready():
    """``content_meta`` missing ``audioManifest``; legacy ``content.audioManifest``
    is ready. Visibility must be True (legacy fallback honoured per BATCH-6
    partial-shard contract)."""
    classroom = _make_classroom(
        content_meta={},  # truthy outer dict possible too (see (c))
        content={"audioManifest": {"status": "ready"}},
    )
    assert _student_can_view_classroom(_make_user(), classroom) is True


# ---------------------------------------------------------------------------
# (c) PERF-P0-4 cutover (2026-04-26) — legacy mirror removed.
#     The AUDIT-2026-04-25-9 per-key fallback inside _student_can_view_classroom
#     is no longer reachable: every writer post-cutover stamps audioManifest
#     into content_meta, and migration 0043 backfilled every existing row.
#     When content_meta is populated but missing/None for audioManifest, the
#     helper now blocks visibility — the legacy field is intentionally NOT
#     consulted as a per-key fallback.
# ---------------------------------------------------------------------------


def test_visibility_blocks_when_meta_has_none_manifest_even_if_legacy_ready():
    """PERF-P0-4 cutover: ``content_meta = {"audioManifest": None, ...}``
    (any other shard key truthy) blocks visibility, even when the legacy
    ``content.audioManifest`` is still ``ready``. Pre-cutover this fell
    back to legacy via AUDIT-2026-04-25-9; post-cutover the legacy is
    treated as stale — content_meta is the source of truth."""
    classroom = _make_classroom(
        content_meta={"audioManifest": None, "otherShardKey": "x"},
        content={"audioManifest": {"status": "ready"}},
    )
    assert _student_can_view_classroom(_make_user(), classroom) is False


def test_visibility_blocks_when_meta_truthy_without_manifest_even_if_legacy_ready():
    """PERF-P0-4 cutover variant: ``content_meta`` truthy but no
    ``audioManifest`` key. Legacy has ready manifest. Visibility blocked."""
    classroom = _make_classroom(
        content_meta={"someUnrelatedKey": "value"},
        content={"audioManifest": {"status": "ready"}},
    )
    assert _student_can_view_classroom(_make_user(), classroom) is False


# ---------------------------------------------------------------------------
# Negative case: both sources missing/not-ready → visibility False
# ---------------------------------------------------------------------------


def test_visibility_blocks_when_neither_source_has_ready_manifest():
    classroom = _make_classroom(
        content_meta={"audioManifest": {"status": "generating"}},
        content={"audioManifest": {"status": "generating"}},
    )
    assert _student_can_view_classroom(_make_user(), classroom) is False


def test_visibility_blocks_when_both_sources_missing_manifest():
    classroom = _make_classroom(content_meta={}, content={})
    assert _student_can_view_classroom(_make_user(), classroom) is False
