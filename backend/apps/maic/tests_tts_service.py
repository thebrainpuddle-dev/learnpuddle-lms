"""Tests for apps.maic.tts.service.

We DO NOT make real edge_tts calls in unit tests — they would (a) hit
Microsoft's public WebSocket from CI (slow + flaky), (b) require
network in test environments. Instead we monkey-patch the `edge_tts`
module's `Communicate` class with a deterministic fake.

Real-call coverage is a manual smoke test included at the bottom,
gated by an env flag so CI never executes it.
"""
from __future__ import annotations

import asyncio
import base64
import os
from typing import Any

import pytest

from apps.maic.exceptions import MaicProviderError
from apps.maic.tts import (
    SpeechAudio,
    SpeechSynthesisError,
    synthesize_speech,
)
from apps.maic.tts import service as tts_service


# ── Helper: a fake edge_tts.Communicate that yields pre-canned audio ──


class _FakeCommunicate:
    """Stand-in for edge_tts.Communicate. Records constructor args so
    tests can assert voice/rate/etc., yields a fixed audio payload."""

    def __init__(self, text: str, voice: str, rate: str = "+0%"):
        self.text = text
        self.voice = voice
        self.rate = rate
        # Captured by the test fixture
        _FakeCommunicate.last_args = {"text": text, "voice": voice, "rate": rate}

    last_args: dict[str, Any] = {}

    async def stream(self):
        # Mirror real edge_tts payload shape
        yield {"type": "audio", "data": b"\xff\xfb\x90hello-mp3"}
        yield {"type": "metadata", "data": b""}  # ignored by service
        yield {"type": "audio", "data": b"-bytes-here"}


@pytest.fixture
def fake_edge_tts(monkeypatch: pytest.MonkeyPatch):
    """Inject a fake `edge_tts` module into sys.modules so the service's
    `import edge_tts` picks it up. Resets between tests."""
    import sys
    import types

    fake = types.ModuleType("edge_tts")
    fake.Communicate = _FakeCommunicate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "edge_tts", fake)
    _FakeCommunicate.last_args = {}
    yield fake


# ── synthesize_speech happy path ──────────────────────────────────────


@pytest.mark.asyncio
async def test_synthesize_returns_b64_mp3(fake_edge_tts):
    result = await synthesize_speech("hello", audio_id="aud-1")
    assert isinstance(result, SpeechAudio)
    assert result.audio_id == "aud-1"
    assert result.format == "mp3"
    decoded = base64.b64decode(result.audio_b64)
    # Concatenated audio chunks from _FakeCommunicate
    assert decoded == b"\xff\xfb\x90hello-mp3-bytes-here"


@pytest.mark.asyncio
async def test_synthesize_uses_default_voice(fake_edge_tts):
    await synthesize_speech("hi", audio_id="aud-2")
    assert _FakeCommunicate.last_args["voice"] == "en-US-AriaNeural"


@pytest.mark.asyncio
async def test_synthesize_passes_explicit_voice(fake_edge_tts):
    await synthesize_speech("hi", audio_id="aud-3", voice="en-GB-RyanNeural")
    assert _FakeCommunicate.last_args["voice"] == "en-GB-RyanNeural"


@pytest.mark.asyncio
@pytest.mark.parametrize("speed,expected_rate", [
    (1.0, "+0%"),
    (1.25, "+25%"),
    (0.9, "-10%"),
    (0.5, "-50%"),
    (2.0, "+100%"),
    (1.005, "+0%"),  # within tolerance
])
async def test_speed_maps_to_edge_rate(fake_edge_tts, speed, expected_rate):
    await synthesize_speech("hi", audio_id="aud-x", speed=speed)
    assert _FakeCommunicate.last_args["rate"] == expected_rate


# ── synthesize_speech edge cases ──────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_text_returns_empty_audio_no_provider_call(fake_edge_tts):
    """Empty text MUST short-circuit — no need to bother edge_tts for
    nothing, and the caller's audio_id correlation still works."""
    result = await synthesize_speech("", audio_id="aud-empty")
    assert result.audio_id == "aud-empty"
    assert result.audio_b64 == ""
    assert result.format == "mp3"
    # Verified no Communicate constructor was invoked
    assert _FakeCommunicate.last_args == {}


@pytest.mark.asyncio
async def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("MAIC_TTS_PROVIDER", "totally-fictional-provider")
    with pytest.raises(SpeechSynthesisError, match="unknown TTS provider"):
        await synthesize_speech("hi", audio_id="x")


# ── Provider failure paths ────────────────────────────────────────────


class _StreamRaisesCommunicate:
    """Fake Communicate whose .stream() raises mid-iteration."""

    def __init__(self, text: str, voice: str, rate: str = "+0%"):
        pass

    async def stream(self):
        yield {"type": "audio", "data": b"first-chunk"}
        raise ConnectionError("simulated network drop")


@pytest.mark.asyncio
async def test_synthesis_provider_error_is_wrapped(monkeypatch):
    """Any exception from edge_tts must surface as SpeechSynthesisError
    so the caller can branch cleanly without a try/except chasing
    library-specific types."""
    import sys
    import types
    fake = types.ModuleType("edge_tts")
    fake.Communicate = _StreamRaisesCommunicate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "edge_tts", fake)

    with pytest.raises(SpeechSynthesisError, match="edge_tts synthesis failed"):
        await synthesize_speech("hi", audio_id="x")


class _EmptyStreamCommunicate:
    def __init__(self, *_args, **_kwargs):
        pass

    async def stream(self):
        # Yield only metadata — no audio chunks
        yield {"type": "metadata", "data": b""}


@pytest.mark.asyncio
async def test_synthesis_no_audio_chunks_raises(monkeypatch):
    """Suspicious empty result → loud failure rather than zero-byte frame."""
    import sys
    import types
    fake = types.ModuleType("edge_tts")
    fake.Communicate = _EmptyStreamCommunicate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "edge_tts", fake)

    with pytest.raises(SpeechSynthesisError, match="no audio data"):
        await synthesize_speech("hi", audio_id="x")


@pytest.mark.asyncio
async def test_missing_edge_tts_install_surfaced(monkeypatch):
    """If the edge_tts package isn't installed, the call must raise
    SpeechSynthesisError with an actionable hint, not a bare ImportError."""
    import sys
    monkeypatch.delitem(sys.modules, "edge_tts", raising=False)
    # Force an ImportError on `import edge_tts` by inserting a finder
    # that raises. Simpler approach: monkey-patch builtins.__import__.
    import builtins
    real_import = builtins.__import__

    def _no_edge(name, *a, **kw):
        if name == "edge_tts":
            raise ImportError("simulated missing")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", _no_edge)

    with pytest.raises(SpeechSynthesisError, match="edge_tts not installed"):
        await synthesize_speech("hi", audio_id="x")


# ── Type re-export ────────────────────────────────────────────────────


def test_speech_synthesis_error_is_alias_of_provider_error():
    """Callers can `except MaicProviderError` and catch TTS failures
    along with other provider errors. The alias is just for clarity at
    TTS call sites."""
    assert SpeechSynthesisError is MaicProviderError


# ── Manual / live edge_tts smoke (gated by env flag) ──────────────────


@pytest.mark.skipif(
    os.environ.get("MAIC_TTS_LIVE_SMOKE") != "1",
    reason="live smoke disabled (set MAIC_TTS_LIVE_SMOKE=1 to enable)",
)
@pytest.mark.asyncio
async def test_live_edge_tts_smoke_returns_real_mp3():
    """Manual cert: actually hits Microsoft's edge_tts WebSocket.
    Only runs when MAIC_TTS_LIVE_SMOKE=1."""
    result = await synthesize_speech(
        "Hello from the MAIC v2 TTS smoke test.",
        audio_id="live-smoke-1",
    )
    decoded = base64.b64decode(result.audio_b64)
    # Real MP3 frame header starts with ID3 or 0xFF 0xFB / 0xFA / 0xF3 / 0xF2
    assert len(decoded) > 1000, f"smoke audio too short: {len(decoded)} bytes"
    assert decoded[:3] in (b"ID3",) or decoded[:1] == b"\xff", (
        f"unexpected MP3 header: {decoded[:4]!r}"
    )
