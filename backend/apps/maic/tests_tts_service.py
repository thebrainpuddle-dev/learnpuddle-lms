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


# ── Minimax TTS provider (MAIC-501) ───────────────────────────────────
# Pattern mirrors _FakeCommunicate above: an injected fake stands in for
# the real network client (aiohttp.ClientSession). We don't mock the
# function under test — we replace the IO boundary with a deterministic
# stub, exactly as the no-mocks rule requires (production code path
# runs end-to-end; only the network is faked).


# Fixed MP3 payload encoded as hex (matches Minimax's wire format).
_FAKE_MINIMAX_MP3 = b"\xff\xfb\x90minimax-fake-mp3-bytes"
_FAKE_MINIMAX_HEX = _FAKE_MINIMAX_MP3.hex()


class _FakeMinimaxResponse:
    """Async context-managed response object used by _FakeMinimaxSession."""

    def __init__(self, status: int, payload: dict | None = None, body: str = ""):
        self.status = status
        self._payload = payload or {}
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return None

    async def json(self):
        return self._payload

    async def text(self):
        return self._body


class _FakeMinimaxSession:
    """Mock aiohttp.ClientSession. Captures the last request so tests
    can assert URL/headers/payload, returns a configurable response."""

    last_request: dict[str, Any] = {}
    response_factory = staticmethod(
        lambda: _FakeMinimaxResponse(
            200,
            payload={"data": {"audio": _FAKE_MINIMAX_HEX}, "extra_info": {"audio_format": "mp3"}},
        )
    )

    def __init__(self, *_a, **_kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return None

    def post(self, url: str, *, json: dict, headers: dict):
        _FakeMinimaxSession.last_request = {"url": url, "json": json, "headers": headers}
        return type(self).response_factory()


def _install_fake_aiohttp(monkeypatch, session_cls=_FakeMinimaxSession):
    """Inject a fake aiohttp module that exposes ClientSession + ClientError."""
    import sys
    import types

    fake = types.ModuleType("aiohttp")
    fake.ClientSession = session_cls  # type: ignore[attr-defined]
    fake.ClientError = ConnectionError  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "aiohttp", fake)
    _FakeMinimaxSession.last_request = {}
    return fake


@pytest.fixture
def fake_aiohttp(monkeypatch: pytest.MonkeyPatch):
    return _install_fake_aiohttp(monkeypatch)


@pytest.fixture
def minimax_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MAIC_TTS_PROVIDER", "minimax")
    monkeypatch.setenv("MINIMAX_API_KEY", "test-server-default-key")


@pytest.mark.asyncio
async def test_minimax_happy_path_decodes_hex(fake_aiohttp, minimax_env):
    """Minimax returns hex-encoded MP3; service decodes to raw bytes,
    then base64-encodes for the wire frame."""
    result = await synthesize_speech("hello world", audio_id="aud-mm-1")
    assert result.audio_id == "aud-mm-1"
    assert result.format == "mp3"
    assert base64.b64decode(result.audio_b64) == _FAKE_MINIMAX_MP3


@pytest.mark.asyncio
async def test_minimax_request_shape_matches_upstream(fake_aiohttp, minimax_env):
    """Payload mirrors upstream lib/audio/tts-providers.ts:generateMiniMaxTTS
    exactly — model, voice_setting, audio_setting, output_format hex."""
    await synthesize_speech("welcome", audio_id="aud-mm-2", voice="male-qn-qingse", speed=1.1)
    req = _FakeMinimaxSession.last_request
    assert req["url"] == "https://api.minimaxi.com/v1/t2a_v2"
    assert req["headers"]["Authorization"] == "Bearer test-server-default-key"
    assert req["headers"]["Content-Type"].startswith("application/json")
    body = req["json"]
    assert body["text"] == "welcome"
    assert body["model"] == "speech-2.8-hd"
    assert body["output_format"] == "hex"
    assert body["stream"] is False
    assert body["language_boost"] == "auto"
    assert body["voice_setting"]["voice_id"] == "male-qn-qingse"
    assert body["voice_setting"]["speed"] == 1.1
    assert body["audio_setting"]["format"] == "mp3"


@pytest.mark.asyncio
async def test_minimax_per_tenant_kwargs_override_env(fake_aiohttp, minimax_env):
    """Per-tenant api_key / base_url / model passed at call time
    override env defaults — this is the path the director uses with
    TenantAIConfig.resolve_tts_config()."""
    await synthesize_speech(
        "hi",
        audio_id="aud-mm-3",
        api_key="tenant-specific-key",
        base_url="https://custom-minimax.example.com/",
        model="speech-2.5-turbo",
    )
    req = _FakeMinimaxSession.last_request
    assert req["url"] == "https://custom-minimax.example.com/v1/t2a_v2"
    assert req["headers"]["Authorization"] == "Bearer tenant-specific-key"
    assert req["json"]["model"] == "speech-2.5-turbo"


@pytest.mark.asyncio
async def test_minimax_provider_arg_overrides_env(fake_aiohttp, monkeypatch):
    """provider= kwarg overrides MAIC_TTS_PROVIDER even when the env says edge."""
    monkeypatch.setenv("MAIC_TTS_PROVIDER", "edge")
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    result = await synthesize_speech("x", audio_id="aud-mm-4", provider="minimax")
    assert base64.b64decode(result.audio_b64) == _FAKE_MINIMAX_MP3


@pytest.mark.asyncio
async def test_minimax_missing_api_key_raises(fake_aiohttp, monkeypatch):
    """No api_key (kwarg or env) → SpeechSynthesisError, no HTTP call."""
    monkeypatch.setenv("MAIC_TTS_PROVIDER", "minimax")
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    with pytest.raises(SpeechSynthesisError, match="api_key required"):
        await synthesize_speech("x", audio_id="aud-mm-5")
    assert _FakeMinimaxSession.last_request == {}


@pytest.mark.asyncio
async def test_minimax_http_error_wrapped(monkeypatch, minimax_env):
    """Non-200 status → SpeechSynthesisError with the body as context."""

    class _Err500Session(_FakeMinimaxSession):
        response_factory = staticmethod(
            lambda: _FakeMinimaxResponse(500, body="Internal upstream failure")
        )

    _install_fake_aiohttp(monkeypatch, session_cls=_Err500Session)
    with pytest.raises(SpeechSynthesisError, match="HTTP 500"):
        await synthesize_speech("x", audio_id="aud-mm-6")


@pytest.mark.asyncio
async def test_minimax_no_audio_in_response_raises(monkeypatch, minimax_env):
    """200 but `data.audio` missing → SpeechSynthesisError, not silent zero-byte frame."""

    class _NoAudioSession(_FakeMinimaxSession):
        response_factory = staticmethod(
            lambda: _FakeMinimaxResponse(200, payload={"data": {}})
        )

    _install_fake_aiohttp(monkeypatch, session_cls=_NoAudioSession)
    with pytest.raises(SpeechSynthesisError, match="no audio"):
        await synthesize_speech("x", audio_id="aud-mm-7")


@pytest.mark.asyncio
async def test_minimax_invalid_hex_raises(monkeypatch, minimax_env):
    """Odd-length hex → SpeechSynthesisError, not ValueError leak."""

    class _OddHexSession(_FakeMinimaxSession):
        response_factory = staticmethod(
            lambda: _FakeMinimaxResponse(200, payload={"data": {"audio": "abc"}})
        )

    _install_fake_aiohttp(monkeypatch, session_cls=_OddHexSession)
    with pytest.raises(SpeechSynthesisError, match="invalid hex"):
        await synthesize_speech("x", audio_id="aud-mm-8")


@pytest.mark.asyncio
async def test_minimax_network_error_wrapped(monkeypatch, minimax_env):
    """aiohttp.ClientError (e.g. DNS failure) → SpeechSynthesisError."""

    class _NetworkErrorSession(_FakeMinimaxSession):
        def post(self, *_a, **_kw):
            raise ConnectionError("simulated DNS resolve failure")

    _install_fake_aiohttp(monkeypatch, session_cls=_NetworkErrorSession)
    with pytest.raises(SpeechSynthesisError, match="minimax synthesis failed"):
        await synthesize_speech("x", audio_id="aud-mm-9")


@pytest.mark.asyncio
async def test_minimax_default_voice_when_unset(fake_aiohttp, minimax_env):
    """When voice= is not passed, falls back to upstream's
    DEFAULT_VOICES_BY_PROVIDER['minimax-tts'] = 'female-yujie'."""
    await synthesize_speech("x", audio_id="aud-mm-10")
    req = _FakeMinimaxSession.last_request
    assert req["json"]["voice_setting"]["voice_id"] == "female-yujie"


@pytest.mark.asyncio
async def test_minimax_empty_text_short_circuits(fake_aiohttp, minimax_env):
    """Empty text — no HTTP call, no api_key check; mirrors edge path."""
    result = await synthesize_speech("", audio_id="aud-mm-11")
    assert result.audio_b64 == ""
    assert _FakeMinimaxSession.last_request == {}


# ── Manual / live Minimax smoke (gated by env flag) ──────────────────


@pytest.mark.skipif(
    os.environ.get("MAIC_MINIMAX_LIVE_SMOKE") != "1"
    or not os.environ.get("MINIMAX_API_KEY"),
    reason=(
        "live minimax smoke disabled (set MAIC_MINIMAX_LIVE_SMOKE=1 and "
        "MINIMAX_API_KEY=<your key> to enable — calls api.minimaxi.com "
        "with real auth, costs a few cents per run)"
    ),
)
@pytest.mark.asyncio
async def test_live_minimax_smoke_returns_real_mp3(monkeypatch):
    """Manual cert: actually hits the real Minimax /v1/t2a_v2 endpoint.

    Validates that the upstream-derived payload shape (model, voice_setting,
    audio_setting, output_format=hex, language_boost=auto) is accepted
    by a live Minimax account, and that the hex→bytes decoding produces
    a real MP3 frame.

    Run with:
        MAIC_MINIMAX_LIVE_SMOKE=1 MINIMAX_API_KEY=<key> \\
            pytest apps/maic/tests_tts_service.py -k live_minimax \\
                --no-migrations
    """
    monkeypatch.setenv("MAIC_TTS_PROVIDER", "minimax")
    result = await synthesize_speech(
        "Welcome to today's lesson on photosynthesis.",
        audio_id="live-minimax-smoke-1",
    )
    decoded = base64.b64decode(result.audio_b64)
    assert len(decoded) > 1000, f"smoke audio too short: {len(decoded)} bytes"
    # MP3 frame header: ID3v2 tag (b"ID3") OR MPEG sync (0xFF 0xFB / 0xFA / etc.)
    assert decoded[:3] == b"ID3" or decoded[:1] == b"\xff", (
        f"unexpected MP3 header: {decoded[:4]!r}"
    )
