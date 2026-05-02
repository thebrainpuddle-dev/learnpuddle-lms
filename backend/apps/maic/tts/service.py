"""TTS service — provider-agnostic synthesis entry point.

Used by the agent_generate node (MAIC-501.2) — when the LLM stream
emits a complete `text` item, the node calls `synthesize_speech(text)`
and emits a `speech_audio` frame containing base64-encoded MP3 bytes
keyed by `audio_id`.

Provider:
  Phase 1 default — edge_tts (Microsoft public WebSocket; free; no key).
  Phase 5 swaps for VoxCPM2 (self-hosted, voice-clonable).

Errors:
  Wrapped in `SpeechSynthesisError` (alias for MaicProviderError) so
  the caller can distinguish TTS failures from other provider errors.
  Empty text → empty bytes (no provider call); short-circuit avoids a
  futile network round-trip for filler text items.
"""
from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass
from typing import Final

from apps.maic.exceptions import MaicProviderError

logger = logging.getLogger(__name__)


# ── Public types ──────────────────────────────────────────────────────


# Re-export under a TTS-specific name for clarity at call sites.
SpeechSynthesisError = MaicProviderError


@dataclass(frozen=True)
class SpeechAudio:
    """Result of one synthesis call. Maps 1:1 to a `speech_audio`
    StatelessEvent frame on the wire."""

    audio_id: str
    audio_b64: str
    format: str  # MIME-ish family identifier, e.g. "mp3"


# ── Configuration ─────────────────────────────────────────────────────


# Default voice when caller doesn't specify. en-US Aria is a clean,
# neutral female voice — same default V1 used in
# apps/courses/tts_service.py.
_DEFAULT_EDGE_VOICE: Final = "en-US-AriaNeural"

# Provider selection. Future providers (voxcpm, minimax, azure, openai)
# slot in by branching here; each must respect the same async
# signature `(text, voice, speed, audio_id) -> SpeechAudio`.
_PROVIDER_ENV: Final = "MAIC_TTS_PROVIDER"
_PROVIDER_EDGE: Final = "edge"


def _provider() -> str:
    """Resolve the configured provider; defaults to 'edge'."""
    return os.environ.get(_PROVIDER_ENV, _PROVIDER_EDGE).strip().lower()


# ── Public API ────────────────────────────────────────────────────────


async def synthesize_speech(
    text: str,
    *,
    audio_id: str,
    voice: str | None = None,
    speed: float = 1.0,
) -> SpeechAudio:
    """Synthesize one text item into MP3 bytes wrapped in a SpeechAudio.

    Args:
        text:     The agent's spoken text. Empty → returns an empty
                  SpeechAudio (no provider call) so the caller can still
                  emit a frame with the audioId for client-side bookkeeping.
        audio_id: Stable identifier the client uses to correlate the
                  speech_audio frame with the originating text item.
        voice:    Provider voice id; falls back to _DEFAULT_EDGE_VOICE
                  for the edge provider when None.
        speed:    Multiplicative speed (1.0 = normal). Edge accepts
                  ±50% as `+N%`/`-N%` rate strings.

    Raises:
        SpeechSynthesisError: Provider call failed (network, auth,
            quota, or library missing).  Caller emits an `error` frame
            and may continue without audio for this text item.
    """
    if not text:
        return SpeechAudio(audio_id=audio_id, audio_b64="", format="mp3")

    provider = _provider()
    if provider == _PROVIDER_EDGE:
        audio_bytes = await _edge_tts_synthesize(text, voice or _DEFAULT_EDGE_VOICE, speed)
        return SpeechAudio(
            audio_id=audio_id,
            audio_b64=base64.b64encode(audio_bytes).decode("ascii"),
            format="mp3",
        )

    raise SpeechSynthesisError(
        f"unknown TTS provider {provider!r}; "
        f"set {_PROVIDER_ENV}=edge (default) or wait for Phase 5 providers"
    )


# ── Edge TTS provider ─────────────────────────────────────────────────


def _speed_to_edge_rate(speed: float) -> str:
    """Edge TTS rate is a string like '+0%', '-10%', '+25%'.

    Speed 1.0 → "+0%". 1.25 → "+25%". 0.9 → "-10%".  Edge clamps
    sensibly for out-of-range values.
    """
    if abs(speed - 1.0) < 0.005:
        return "+0%"
    pct = int(round((speed - 1.0) * 100))
    return f"{pct:+d}%"


async def _edge_tts_synthesize(text: str, voice: str, speed: float) -> bytes:
    """Stream from Microsoft Edge's TTS WebSocket, accumulate audio chunks.

    Pattern mirrors V1's apps/courses/tts_service.py::_run_edge_tts:
        async for chunk in Communicate(...).stream():
            if chunk['type'] == 'audio': accumulate
    """
    try:
        import edge_tts  # type: ignore[import-untyped]
    except ImportError as exc:  # noqa: BLE001
        raise SpeechSynthesisError(
            "edge_tts not installed; pip install -r requirements.txt"
        ) from exc

    rate_str = _speed_to_edge_rate(speed)
    audio_chunks: list[bytes] = []

    try:
        communicate = edge_tts.Communicate(text, voice, rate=rate_str)
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                audio_chunks.append(chunk["data"])
    except Exception as exc:  # noqa: BLE001 — wraps any provider error
        logger.warning("edge_tts: synthesis failed", exc_info=True)
        raise SpeechSynthesisError(f"edge_tts synthesis failed: {exc}") from exc

    if not audio_chunks:
        # Empty result is suspicious — log + raise so the caller doesn't
        # silently emit a zero-byte frame. Real edge_tts always returns
        # ≥ a few KB for any non-empty input.
        raise SpeechSynthesisError("edge_tts returned no audio data")

    return b"".join(audio_chunks)
