"""Unit tests for the _student_can_view_classroom visibility helper.

TDD — tests written BEFORE the helper was extracted from the duplicated
inline logic in ``student_maic_classroom_detail`` and ``student_maic_chat``.

The helper must be the single canonical gate for student classroom
visibility so the two callers cannot diverge (BE-SEC-002 m1/m2 follow-up).
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.courses.maic_views import _student_can_view_classroom


# ─── Helpers ────────────────────────────────────────────────────────────────


class _SectionQueryset(list):
    """Minimal queryset substitute supporting ``.exists()`` and the ``in`` operator.

    Inherits from ``list`` so Python's native ``__contains__`` handles the
    ``section in qs`` check without any magic method wiring on a MagicMock
    (dunder methods on MagicMock instances are looked up on the class, not
    the instance, which can cause surprising behaviour in tests).
    """

    def exists(self) -> bool:
        return bool(self)


def _make_classroom(
    *,
    status: str = "READY",
    is_public: bool = False,
    sections=(),
    manifest_status: str = "ready",
):
    """Return a minimal MAICClassroom-like mock for unit tests.

    Uses ``MagicMock`` for the classroom itself (simple attribute access) and
    a real ``_SectionQueryset`` for ``assigned_sections.all()`` so that the
    ``in`` operator and ``.exists()`` behave like a real queryset.

    PERF-P0-4 cutover: the helper now reads audioManifest from
    ``composed_content`` (shards). We set ``content_meta`` directly and
    seed ``composed_content`` with the same dict so the mock matches what
    the real ``MAICClassroom.composed_content`` property would return.
    """
    audio = {"audioManifest": {"status": manifest_status}}
    classroom = MagicMock()
    classroom.status = status
    classroom.is_public = is_public
    classroom.content = audio
    classroom.content_meta = audio
    classroom.composed_content = dict(audio)
    classroom.assigned_sections.all.return_value = _SectionQueryset(sections)
    return classroom


def _make_user(section=None):
    """Return a minimal user-like namespace with an optional ``section_fk``."""
    return SimpleNamespace(section_fk=section)


# ─── Tests ──────────────────────────────────────────────────────────────────


class TestStudentCanViewClassroom:
    """Behaviour contract for ``_student_can_view_classroom(user, classroom)``."""

    # --- Status gate --------------------------------------------------------

    def test_returns_false_when_classroom_is_draft(self):
        c = _make_classroom(status="DRAFT")
        assert _student_can_view_classroom(_make_user(), c) is False

    def test_returns_false_when_classroom_is_generating(self):
        c = _make_classroom(status="GENERATING")
        assert _student_can_view_classroom(_make_user(), c) is False

    def test_returns_false_when_classroom_is_failed(self):
        c = _make_classroom(status="FAILED")
        assert _student_can_view_classroom(_make_user(), c) is False

    def test_returns_false_when_classroom_is_archived(self):
        c = _make_classroom(status="ARCHIVED")
        assert _student_can_view_classroom(_make_user(), c) is False

    # --- Audio manifest gate ------------------------------------------------

    def test_returns_false_when_audio_manifest_is_generating(self):
        c = _make_classroom(manifest_status="generating", is_public=True)
        assert _student_can_view_classroom(_make_user(), c) is False

    def test_returns_false_when_audio_manifest_is_pending(self):
        c = _make_classroom(manifest_status="pending", is_public=True)
        assert _student_can_view_classroom(_make_user(), c) is False

    def test_returns_false_when_audio_manifest_is_missing(self):
        """Content dict with no audioManifest key must be treated as not ready."""
        classroom = MagicMock()
        classroom.status = "READY"
        classroom.is_public = True
        classroom.content = {}  # no audioManifest key at all
        classroom.content_meta = {}
        classroom.composed_content = {}
        classroom.assigned_sections.all.return_value = _SectionQueryset()
        assert _student_can_view_classroom(_make_user(), classroom) is False

    def test_returns_true_for_ready_audio_manifest(self):
        c = _make_classroom(manifest_status="ready", is_public=True)
        assert _student_can_view_classroom(_make_user(), c) is True

    def test_returns_true_for_partial_audio_manifest(self):
        """Partial manifest (still encoding) is accessible — matches list endpoint."""
        c = _make_classroom(manifest_status="partial", is_public=True)
        assert _student_can_view_classroom(_make_user(), c) is True

    # --- Section assignment gate --------------------------------------------

    def test_returns_false_when_assigned_and_student_has_no_section(self):
        """Student without a section cannot access an assigned classroom."""
        section = object()
        c = _make_classroom(sections=[section])
        assert _student_can_view_classroom(_make_user(section=None), c) is False

    def test_returns_false_when_assigned_and_student_section_does_not_match(self):
        """Student in the wrong section cannot access the classroom."""
        section_a = object()
        section_b = object()
        c = _make_classroom(sections=[section_b])
        assert _student_can_view_classroom(_make_user(section=section_a), c) is False

    def test_returns_true_when_assigned_and_student_section_matches(self):
        """Student in the correct section can access the classroom."""
        section = object()
        c = _make_classroom(sections=[section])
        assert _student_can_view_classroom(_make_user(section=section), c) is True

    # --- Public / private gate ----------------------------------------------

    def test_returns_false_for_private_unassigned_classroom(self):
        """Private classroom with no sections is not visible to students."""
        c = _make_classroom(sections=[], is_public=False)
        assert _student_can_view_classroom(_make_user(), c) is False

    def test_returns_true_for_public_unassigned_classroom(self):
        """Public classroom with no sections is visible to every student."""
        c = _make_classroom(sections=[], is_public=True)
        assert _student_can_view_classroom(_make_user(), c) is True
