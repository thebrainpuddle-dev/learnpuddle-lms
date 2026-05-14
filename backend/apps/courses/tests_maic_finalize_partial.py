"""Unit tests for the partial-classroom finalizer (CG-P0-8).

When the wizard's browser tab reloads/closes mid-generation, the row gets
stranded on ``status=GENERATING`` with content_scenes already partially
populated by the per-scene persistPartial PATCH (CG-P0-4). This finalizer
flips that row to READY so the user can play through the scenes that DID
get saved instead of having to delete and start over.

Pure-helper test: takes a classroom-like object, returns a result dict.
View wrapper layered on top calls the helper and returns DRF Response.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.courses.maic_views import finalize_partial_classroom, _maic_response_status


def _make_classroom(
    *,
    status: str = "GENERATING",
    content_scenes=None,
    content_agents=None,
    content_meta=None,
):
    """Minimal MAICClassroom-like mock — we only need attribute access +
    a `save` method that records what was written."""
    classroom = MagicMock()
    classroom.status = status
    classroom.content = {}
    classroom.content_scenes = content_scenes if content_scenes is not None else []
    classroom.content_agents = content_agents if content_agents is not None else []
    classroom.content_meta = content_meta if content_meta is not None else {}
    classroom.scenes_ready = 0
    classroom.scene_count = 0
    classroom.error_message = ""
    return classroom


def test_finalize_flips_generating_to_ready_when_scenes_saved():
    """GENERATING + non-empty content_scenes → READY + scenes_ready=N."""
    scenes = [
        {"id": "s0", "title": "Intro", "actions": [{"type": "speech"}]},
        {"id": "s1", "title": "Body", "actions": [{"type": "speech"}, {"type": "speech"}]},
        {"id": "s2", "title": "Wrap", "actions": []},
    ]
    classroom = _make_classroom(content_scenes=scenes)

    result = finalize_partial_classroom(classroom)

    assert result["ok"] is True
    assert classroom.status == "READY"
    assert classroom.scenes_ready == 3
    assert classroom.scene_count == 3
    classroom.save.assert_called_once()


def test_finalize_rejects_when_no_scenes_saved():
    """GENERATING + empty content_scenes → ok=False, status untouched.

    There's nothing to finalize — caller should delete and restart instead.
    """
    classroom = _make_classroom(content_scenes=[])

    result = finalize_partial_classroom(classroom)

    assert result["ok"] is False
    assert "no scenes" in result["error"].lower()
    assert classroom.status == "GENERATING"  # unchanged
    classroom.save.assert_not_called()


def test_finalize_rejects_prompt_placeholder_content():
    """A syntactically valid scene is not READY if it copied prompt examples."""
    classroom = _make_classroom(
        content_scenes=[
            {
                "id": "s0",
                "title": "Quadratics",
                "content": {
                    "type": "slide",
                    "elements": [
                        {"type": "text", "content": "Main Title Text"},
                    ],
                },
                "actions": [{"type": "speech"}],
            }
        ],
        content_meta={
            "slides": [
                {
                    "id": "slide-1",
                    "elements": [
                        {"type": "text", "content": "A compelling subtitle or tagline"},
                    ],
                }
            ],
        },
    )

    result = finalize_partial_classroom(classroom)

    assert result["ok"] is False
    assert "placeholder" in result["error"].lower()
    assert "Main Title Text" in result["placeholders"]
    assert classroom.status == "GENERATING"
    classroom.save.assert_not_called()


def test_finalize_is_idempotent_for_already_ready():
    """READY + non-empty content_scenes → ok=True, no save (already done)."""
    scenes = [{"id": "s0", "title": "Intro", "actions": []}]
    classroom = _make_classroom(status="READY", content_scenes=scenes)

    result = finalize_partial_classroom(classroom)

    assert result["ok"] is True
    assert classroom.status == "READY"
    classroom.save.assert_not_called()


def test_finalize_rejects_failed_classrooms():
    """FAILED rows should NOT be silently revived — caller must explicitly delete."""
    scenes = [{"id": "s0", "title": "Intro", "actions": []}]
    classroom = _make_classroom(status="FAILED", content_scenes=scenes)

    result = finalize_partial_classroom(classroom)

    assert result["ok"] is False
    assert classroom.status == "FAILED"
    classroom.save.assert_not_called()


def test_finalize_rejects_archived_classrooms():
    """ARCHIVED rows must not be silently un-archived."""
    scenes = [{"id": "s0", "title": "Intro", "actions": []}]
    classroom = _make_classroom(status="ARCHIVED", content_scenes=scenes)

    result = finalize_partial_classroom(classroom)

    assert result["ok"] is False
    assert classroom.status == "ARCHIVED"
    classroom.save.assert_not_called()


def test_finalize_clears_stale_error_message_on_revive():
    """If a previous attempt left an error_message, clear it on successful finalize."""
    scenes = [{"id": "s0", "title": "Intro", "actions": []}]
    classroom = _make_classroom(content_scenes=scenes)
    classroom.error_message = "old transient failure"

    finalize_partial_classroom(classroom)

    assert classroom.error_message == ""


def test_ready_response_status_rejects_legacy_placeholder_content():
    """Already-saved bad rows must not keep rendering as playable READY."""
    classroom = _make_classroom(
        status="READY",
        content_scenes=[
            {
                "id": "s0",
                "content": {
                    "elements": [{"type": "text", "content": "Main Title Text"}],
                },
            }
        ],
        content_meta={"slides": [{"elements": [{"content": "Main Title Text"}]}]},
    )
    classroom.error_message = ""

    response_status, response_error = _maic_response_status(classroom)

    assert response_status == "FAILED"
    assert "placeholder" in response_error.lower()
