"""Tests for `apps.maic.generation.pipeline_runner` (MAIC-420).

Coverage:
  - create_generation_session shape lock
  - run_generation_pipeline happy path with stub provider
  - Stage 1 failure → result.success=False + error message
  - Callback invocations: onProgress / onStageComplete / onError
  - Stage 2 STUB returns empty scenes list (will flip to real call
    when MAIC-422.x ships — explicit test pin so the regression is
    caught when the stub is removed)
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from apps.maic.generation.pipeline_runner import (
    create_generation_session,
    run_generation_pipeline,
)


# ── create_generation_session ─────────────────────────────────────


class TestCreateGenerationSession:
    def test_returns_session_with_required_keys(self):
        session = create_generation_session({"requirement": "x"})
        assert "id" in session
        assert "requirements" in session
        assert "progress" in session
        assert "sceneOutlines" in session
        assert "scenes" in session
        assert "startedAt" in session
        assert "completedAt" not in session  # only set after completion

    def test_session_id_is_unique(self):
        a = create_generation_session({"requirement": "x"})
        b = create_generation_session({"requirement": "x"})
        assert a["id"] != b["id"]

    def test_progress_starts_at_stage_1(self):
        session = create_generation_session({"requirement": "x"})
        assert session["progress"]["stage"] == 1
        assert session["progress"]["completed"] == 0
        assert session["progress"]["total"] == 0

    def test_started_at_is_iso8601(self):
        session = create_generation_session({"requirement": "x"})
        # YYYY-MM-DDTHH:MM:SS.ffffff+00:00 — at minimum has 'T'
        assert "T" in session["startedAt"]


# ── run_generation_pipeline ───────────────────────────────────────


@pytest.mark.asyncio
async def test_pipeline_runs_stage_1_against_stub_provider():
    """End-to-end pipeline against stub. The stub provider returns
    a JSON array which Stage 1 treats as the legacy outline format
    → Stage 2 stub returns []. Pipeline returns success."""
    session = create_generation_session({
        "requirement": "teach photosynthesis",
        "language": "English",
    })
    result = await run_generation_pipeline(session, language_model_id="stub")
    assert result["success"] is True
    assert "data" in result
    # Stage 1 populated outlines (stub provider yields a list)
    assert isinstance(result["data"]["sceneOutlines"], list)
    # Stage 2 STUB returns empty
    assert result["data"]["scenes"] == []
    # Completion timestamp set
    assert "completedAt" in result["data"]


@pytest.mark.asyncio
async def test_pipeline_populates_session_dict_in_place():
    """The session dict passed in is mutated to include stage outputs.
    Mirrors upstream's behavior — same session reference flows."""
    session = create_generation_session({"requirement": "x"})
    result = await run_generation_pipeline(session, language_model_id="stub")
    # The same session reference is in result.data
    assert result["data"] is session


@pytest.mark.asyncio
async def test_stage_1_failure_returns_error_envelope():
    """Stage 1 schema regression → pipeline returns success=False
    with the upstream error message preserved."""
    async def _fake_outline_call(*args, **kwargs):
        return {"success": False, "error": "schema regression test"}

    with patch(
        "apps.maic.generation.pipeline_runner."
        "generate_scene_outlines_from_requirements",
        new=_fake_outline_call,
    ):
        session = create_generation_session({"requirement": "x"})
        result = await run_generation_pipeline(session)
    assert result["success"] is False
    assert "schema regression test" in result["error"]
    # Errors accumulate on the session
    assert "schema regression test" in session.get("errors", [])


@pytest.mark.asyncio
async def test_callbacks_fire_in_expected_order():
    """onProgress fires multiple times; onStageComplete fires for
    stages 1 and 2 in order; onError does NOT fire on success."""
    progress_events = []
    stage_completes = []
    errors = []

    callbacks = {
        "onProgress": lambda p: progress_events.append(p),
        "onStageComplete": lambda s, d: stage_completes.append(s),
        "onError": lambda e: errors.append(e),
    }

    session = create_generation_session({"requirement": "x"})
    result = await run_generation_pipeline(
        session, language_model_id="stub", callbacks=callbacks
    )

    assert result["success"]
    # onStageComplete fires for stage 1 then stage 2 (in that order)
    assert stage_completes == [1, 2]
    # onError must NOT fire on success
    assert errors == []
    # onProgress fired at least: once at pipeline start, once at
    # outline generator start, once at outline generator end, once
    # at stage 2 start. So >= 4 events.
    assert len(progress_events) >= 4


@pytest.mark.asyncio
async def test_on_error_callback_fires_on_failure():
    """Stage 1 failure also fires onError if the callback is set."""
    errors = []
    callbacks = {"onError": lambda e: errors.append(e)}

    async def _fake(*args, **kwargs):
        return {"success": False, "error": "boom"}

    with patch(
        "apps.maic.generation.pipeline_runner."
        "generate_scene_outlines_from_requirements",
        new=_fake,
    ):
        session = create_generation_session({"requirement": "x"})
        result = await run_generation_pipeline(session, callbacks=callbacks)
    assert not result["success"]
    assert errors == ["boom"]


@pytest.mark.asyncio
async def test_stage_2_stub_returns_empty_scenes():
    """REGRESSION PIN — Stage 2 is currently a stub that returns [].
    When MAIC-422.x ships the real generate_full_scenes, this test
    flips to expect populated scenes (and the test name should be
    renamed too)."""
    session = create_generation_session({"requirement": "x"})
    result = await run_generation_pipeline(session, language_model_id="stub")
    assert result["data"]["scenes"] == [], (
        "Stage 2 should be a stub returning [] until MAIC-422.x lands. "
        "If MAIC-422.x has shipped, update this test to expect populated "
        "scenes and remove the stub assertion."
    )


@pytest.mark.asyncio
async def test_language_directive_propagates_from_stage_1():
    """The Stage 1 outline result includes a languageDirective; it
    must land on the session and (eventually) be passed to Stage 2."""
    response = json.dumps({
        "languageDirective": "Speak only Mandarin Chinese.",
        "outlines": [{"type": "slide", "title": "T"}],
    })

    async def _fake_text(*args, **kwargs):
        return response

    with patch(
        "apps.maic.generation.outline_generator.generate_text", new=_fake_text
    ):
        session = create_generation_session({"requirement": "x"})
        result = await run_generation_pipeline(session, language_model_id="stub")
    assert result["success"]
    assert session["languageDirective"] == "Speak only Mandarin Chinese."


@pytest.mark.asyncio
async def test_progress_message_at_completion_is_complete():
    session = create_generation_session({"requirement": "x"})
    await run_generation_pipeline(session, language_model_id="stub")
    final_progress = session["progress"]
    assert final_progress["stage"] == 2
    assert "complete" in final_progress.get("message", "").lower()
