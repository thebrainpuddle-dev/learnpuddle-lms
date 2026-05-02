"""Integration tests for the TTS path in _agent_generate_node (MAIC-501.2).

Asserts that a complete agent turn (stub LLM) produces a speech_audio
frame BEFORE agent_end, with the correct shape — and that TTS failures
degrade gracefully (text still streams, no agent_end skip, no error
frame for the user).

Uses the same fake-edge_tts module fixture pattern as
tests_tts_service.py (no network)."""
from __future__ import annotations

import base64
import sys
import types
from typing import Any

import pytest

from apps.maic.orchestration.director_graph import (
    build_initial_state,
    stream_classroom,
)


# ── Fake edge_tts (deterministic; no network) ─────────────────────────


class _FakeCommunicate:
    """Yields a fixed audio payload so tests can assert exact b64."""

    AUDIO_PAYLOAD = b"\xff\xfb\x90fake-mp3-bytes-for-test"

    def __init__(self, text: str, voice: str, rate: str = "+0%"):
        _FakeCommunicate.last_args = {"text": text, "voice": voice, "rate": rate}

    last_args: dict[str, Any] = {}

    async def stream(self):
        yield {"type": "audio", "data": self.AUDIO_PAYLOAD}


class _RaisingCommunicate:
    def __init__(self, *_a, **_kw):
        pass

    async def stream(self):
        yield {"type": "audio", "data": b"first"}
        raise ConnectionError("simulated TTS network drop")


@pytest.fixture
def fake_edge_tts(monkeypatch):
    fake = types.ModuleType("edge_tts")
    fake.Communicate = _FakeCommunicate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "edge_tts", fake)
    _FakeCommunicate.last_args = {}
    yield fake


@pytest.fixture
def failing_edge_tts(monkeypatch):
    fake = types.ModuleType("edge_tts")
    fake.Communicate = _RaisingCommunicate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "edge_tts", fake)
    yield fake


# ── Tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_speech_audio_frame_emitted_after_text_before_agent_end(fake_edge_tts):
    """Phase-1 contract: one speech_audio per agent turn, positioned
    AFTER all text/action events but BEFORE agent_end. Frontend
    playback engine queues audio by audioId."""
    events = []
    async for event in stream_classroom(build_initial_state()):
        events.append(event)

    types_seq = [e["type"] for e in events]

    # speech_audio appears exactly once
    assert types_seq.count("speech_audio") == 1, types_seq

    # Order: every text_delta and action precedes speech_audio;
    # speech_audio precedes agent_end.
    speech_idx = types_seq.index("speech_audio")
    end_idx = types_seq.index("agent_end")
    assert speech_idx < end_idx, types_seq
    last_text_idx = max(i for i, t in enumerate(types_seq) if t == "text_delta")
    last_action_idx = max(
        (i for i, t in enumerate(types_seq) if t == "action"),
        default=-1,
    )
    assert last_text_idx < speech_idx, types_seq
    assert last_action_idx < speech_idx, types_seq


@pytest.mark.asyncio
async def test_speech_audio_frame_payload_shape(fake_edge_tts):
    """Validate every field on the speech_audio frame — frontend will
    rely on each."""
    events = [e async for e in stream_classroom(build_initial_state())]
    speech = next(e for e in events if e["type"] == "speech_audio")
    data = speech["data"]
    assert set(data.keys()) >= {"audioId", "audioB64", "format", "messageId", "agentId"}
    assert data["format"] == "mp3"
    assert data["agentId"] == "default-1"
    # audioB64 decodes to the fake-edge_tts payload
    assert base64.b64decode(data["audioB64"]) == _FakeCommunicate.AUDIO_PAYLOAD
    # audioId is a stable, prefixed identifier (speech-<hex>)
    assert data["audioId"].startswith("speech-")
    # messageId matches the surrounding agent_start/agent_end
    starts = [e for e in events if e["type"] == "agent_start"]
    assert data["messageId"] == starts[0]["data"]["messageId"]


@pytest.mark.asyncio
async def test_tts_called_with_concatenated_text(fake_edge_tts):
    """One TTS call per agent turn — text passed in equals the full
    concatenated stub LLM text."""
    [_ async for _ in stream_classroom(build_initial_state())]
    expected = "Hello students. Today we will learn about the topic at hand."
    assert _FakeCommunicate.last_args["text"] == expected


@pytest.mark.asyncio
async def test_tts_uses_default_voice_when_agent_has_none(fake_edge_tts):
    """default-1 (teacher) has no voiceConfig, so TTS falls back to
    edge service's default voice."""
    [_ async for _ in stream_classroom(build_initial_state())]
    assert _FakeCommunicate.last_args["voice"] == "en-US-AriaNeural"


@pytest.mark.asyncio
async def test_tts_failure_degrades_gracefully(failing_edge_tts):
    """TTS provider failure must NOT kill the turn. Expected:
       - All text_delta + action events still emitted
       - NO speech_audio frame
       - agent_end still emitted (so the director can advance and end)
       - NO error frame surfaced (TTS failure is a partial-degradation,
         not a turn-terminating error)
    """
    events = [e async for e in stream_classroom(build_initial_state())]
    types_seq = [e["type"] for e in events]
    assert "speech_audio" not in types_seq
    assert "agent_end" in types_seq
    assert "text_delta" in types_seq
    # No `error` frame from the TTS branch (provider error is degraded
    # to a logger.warning — the user-facing stream stays clean).
    error_frames = [e for e in events if e["type"] == "error"]
    assert error_frames == [], f"unexpected error frames: {error_frames}"


@pytest.mark.asyncio
async def test_no_speech_audio_when_text_is_empty(monkeypatch):
    """If the agent emits zero spoken text (only actions), no
    speech_audio frame is emitted (the empty-text short-circuit in
    synthesize_speech kicks in OR the `full_text.strip()` guard skips
    the call entirely)."""
    # Override the stub to emit only an action, no text item.
    monkeypatch.setattr(
        "apps.maic.orchestration.ai_adapter.STUB_OUTPUT",
        '[{"type":"action","name":"wb_open","params":{}}]',
    )
    events = [e async for e in stream_classroom(build_initial_state())]
    types_seq = [e["type"] for e in events]
    assert "speech_audio" not in types_seq
    assert "action" in types_seq
    assert "agent_end" in types_seq
