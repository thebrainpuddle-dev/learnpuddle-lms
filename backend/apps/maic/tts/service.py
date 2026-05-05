"""TTS service — provider-agnostic synthesis entry point.

Used by the agent_generate node (MAIC-501.2) — when the LLM stream
emits a complete `text` item, the node calls `synthesize_speech(text)`
and emits a `speech_audio` frame containing base64-encoded MP3 bytes
keyed by `audio_id`.

Providers:
  Phase 1 default — edge_tts (Microsoft public WebSocket; free; no key).
  Phase 5 (MAIC-501) — Minimax cloud (requires api_key) for production.
  Phase 9 — VoxCPM2 self-host adds back via the same _provider() branch
  (deferred per ADR-004a; the M4 mini does not have CUDA).

Per-tenant credentials:
  Cloud providers accept `api_key`, `base_url`, and `model` as kwargs.
  The director resolves these from `TenantAIConfig` and passes them in
  (MAIC-502). When called without them, providers fall back to env-var
  defaults (MINIMAX_API_KEY) for server-wide configuration.

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

# Minimax defaults — match upstream OpenMAIC lib/audio/constants.ts:
# 'minimax-tts' defaultBaseUrl + defaultModelId + DEFAULT_VOICES_BY_PROVIDER.
# language_boost: 'auto' in the payload means a single voice covers
# en/zh/etc. without re-keying per language.
_DEFAULT_MINIMAX_BASE_URL: Final = "https://api.minimaxi.com"
_DEFAULT_MINIMAX_MODEL: Final = "speech-2.8-hd"
_DEFAULT_MINIMAX_VOICE: Final = "female-yujie"

# ElevenLabs defaults — match upstream constants.ts:'elevenlabs-tts'.
# defaultBaseUrl = "https://api.elevenlabs.io/v1"; default voice is
# Sarah (warm female, English) — same id as DEFAULT_VOICES_BY_PROVIDER.
_DEFAULT_ELEVENLABS_BASE_URL: Final = "https://api.elevenlabs.io/v1"
_DEFAULT_ELEVENLABS_MODEL: Final = "eleven_multilingual_v2"
_DEFAULT_ELEVENLABS_VOICE: Final = "EXAVITQu4vr4xnSDxMaL"

# Provider selection. Each provider slots in by branching in
# synthesize_speech; each respects the same async signature
# (text, voice, speed, …) -> bytes (raw audio).
_PROVIDER_ENV: Final = "MAIC_TTS_PROVIDER"
_FALLBACK_CHAIN_ENV: Final = "MAIC_TTS_FALLBACK_CHAIN"
_PROVIDER_EDGE: Final = "edge"
_PROVIDER_MINIMAX: Final = "minimax"
_PROVIDER_ELEVENLABS: Final = "elevenlabs"


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
    provider: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> SpeechAudio:
    """Synthesize one text item into MP3 bytes wrapped in a SpeechAudio.

    Args:
        text:     The agent's spoken text. Empty → returns an empty
                  SpeechAudio (no provider call) so the caller can still
                  emit a frame with the audioId for client-side bookkeeping.
        audio_id: Stable identifier the client uses to correlate the
                  speech_audio frame with the originating text item.
        voice:    Provider voice id; provider-specific default applies
                  when None (Aria for edge, female-yujie for minimax).
        speed:    Multiplicative speed (1.0 = normal). Edge accepts
                  ±50% as `+N%`/`-N%` rate strings.
        provider: Per-call override of MAIC_TTS_PROVIDER. Used by the
                  director when a tenant's TenantAIConfig pins a
                  different provider than the server default.
        api_key:  Per-tenant API key for cloud providers. Cloud
                  providers fall back to env-var (e.g. MINIMAX_API_KEY)
                  when None for server-wide deployments.
        base_url: Override the provider's default endpoint (used by
                  custom Minimax deployments and Phase 9 VoxCPM2).
        model:    Override the provider's default model id.

    Raises:
        SpeechSynthesisError: Provider call failed (network, auth,
            quota, or library missing).  Caller emits an `error` frame
            and may continue without audio for this text item.
    """
    if not text:
        return SpeechAudio(audio_id=audio_id, audio_b64="", format="mp3")

    primary = (provider or _provider()).strip().lower()
    try:
        return await _synthesize_with_provider(
            primary, text,
            audio_id=audio_id,
            voice=voice, speed=speed,
            api_key=api_key, base_url=base_url, model=model,
        )
    except SpeechSynthesisError as primary_exc:
        # Walk the fallback chain. Fallbacks use server-wide env-var
        # keys (MINIMAX_API_KEY, ELEVENLABS_API_KEY) — NOT the tenant's
        # primary api_key, which only applies to their pinned provider.
        # `voice` is also dropped on fallback because a voice id from
        # provider A (e.g. ElevenLabs UUID) is meaningless to provider
        # B (Minimax slug). Each fallback uses its own default voice
        # via the rotation-or-default ladder.
        chain = _fallback_chain(exclude=primary)
        if not chain:
            raise

        last_exc = primary_exc
        for fb in chain:
            try:
                logger.warning(
                    "tts: primary %r failed (%s); falling back to %r",
                    primary, primary_exc, fb,
                )
                return await _synthesize_with_provider(
                    fb, text,
                    audio_id=audio_id,
                    voice=None, speed=speed,
                    api_key=None, base_url=None, model=None,
                )
            except SpeechSynthesisError as fb_exc:
                logger.warning("tts: fallback %r also failed: %s", fb, fb_exc)
                last_exc = fb_exc
                continue

        # All fallbacks exhausted — raise the LAST error so the caller
        # sees what the bottom of the chain reported (usually edge_tts
        # when it's the only one without keys).
        raise last_exc


# ── Provider dispatch helpers ─────────────────────────────────────────


def _fallback_chain(exclude: str) -> list[str]:
    """Parse MAIC_TTS_FALLBACK_CHAIN into a deduplicated, lowercased
    provider list with the primary already removed.

    Empty or unset env var → empty list (no fallback). Whitespace and
    blank entries are tolerated so an admin can comment-style edit.
    """
    raw = os.environ.get(_FALLBACK_CHAIN_ENV, "")
    seen: set[str] = {exclude}
    chain: list[str] = []
    for item in raw.split(","):
        token = item.strip().lower()
        if token and token not in seen:
            seen.add(token)
            chain.append(token)
    return chain


async def _synthesize_with_provider(
    provider: str,
    text: str,
    *,
    audio_id: str,
    voice: str | None,
    speed: float,
    api_key: str | None,
    base_url: str | None,
    model: str | None,
) -> SpeechAudio:
    """Single-provider synthesis. Raises SpeechSynthesisError on any
    provider-specific failure so the fallback-chain caller can decide
    whether to try the next provider."""
    if provider == _PROVIDER_EDGE:
        audio_bytes = await _edge_tts_synthesize(text, voice or _DEFAULT_EDGE_VOICE, speed)
        return SpeechAudio(
            audio_id=audio_id,
            audio_b64=base64.b64encode(audio_bytes).decode("ascii"),
            format="mp3",
        )
    if provider == _PROVIDER_MINIMAX:
        audio_bytes = await _minimax_synthesize(
            text,
            voice=voice or _DEFAULT_MINIMAX_VOICE,
            speed=speed,
            api_key=api_key or os.environ.get("MINIMAX_API_KEY", ""),
            base_url=base_url or _DEFAULT_MINIMAX_BASE_URL,
            model=model or _DEFAULT_MINIMAX_MODEL,
        )
        return SpeechAudio(
            audio_id=audio_id,
            audio_b64=base64.b64encode(audio_bytes).decode("ascii"),
            format="mp3",
        )
    if provider == _PROVIDER_ELEVENLABS:
        audio_bytes = await _elevenlabs_synthesize(
            text,
            voice=voice or _DEFAULT_ELEVENLABS_VOICE,
            speed=speed,
            api_key=api_key or os.environ.get("ELEVENLABS_API_KEY", ""),
            base_url=base_url or _DEFAULT_ELEVENLABS_BASE_URL,
            model=model or _DEFAULT_ELEVENLABS_MODEL,
        )
        return SpeechAudio(
            audio_id=audio_id,
            audio_b64=base64.b64encode(audio_bytes).decode("ascii"),
            format="mp3",
        )

    raise SpeechSynthesisError(
        f"unknown TTS provider {provider!r}; "
        f"set {_PROVIDER_ENV}=edge|minimax|elevenlabs (or pass provider=)"
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


# ── Minimax TTS provider ──────────────────────────────────────────────
# Mirrors upstream OpenMAIC lib/audio/tts-providers.ts:generateMiniMaxTTS.
# POST {base_url}/v1/t2a_v2, Bearer auth, hex-encoded MP3 in
# data.data.audio. ADR-004a (2026-05-04) makes this the primary Phase 5
# provider after the VoxCPM2 spike (MAIC-500) failed both gates on Apple
# Silicon.


async def _minimax_synthesize(
    text: str,
    *,
    voice: str,
    speed: float,
    api_key: str,
    base_url: str,
    model: str,
) -> bytes:
    if not api_key:
        raise SpeechSynthesisError(
            "minimax: api_key required (set MINIMAX_API_KEY or pass per-tenant key)"
        )

    try:
        import aiohttp  # type: ignore[import-untyped]
    except ImportError as exc:
        raise SpeechSynthesisError(
            "aiohttp not installed; pip install -r requirements.txt"
        ) from exc

    url = f"{base_url.rstrip('/')}/v1/t2a_v2"
    payload = {
        "model": model,
        "text": text,
        "stream": False,
        "output_format": "hex",
        "voice_setting": {
            "voice_id": voice,
            "speed": float(speed),
            "vol": 1,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
        "language_boost": "auto",
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json; charset=utf-8",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise SpeechSynthesisError(
                        f"minimax: HTTP {resp.status}: {body[:200]}"
                    )
                data = await resp.json()
    except aiohttp.ClientError as exc:
        logger.warning("minimax: network error", exc_info=True)
        raise SpeechSynthesisError(f"minimax synthesis failed: {exc}") from exc

    # Minimax wraps business-logic errors in a 200 response with a
    # `base_resp` envelope. Surface the status_code + status_msg so
    # production debugging is one log line, not a diff against upstream.
    # Common codes:
    #   1008 — insufficient balance (account has no credits left)
    #   2049 — invalid api key (key not recognized for this region)
    #   2013 — invalid voice_id (voice doesn't exist for this provider)
    # Three regional endpoints exist: api.minimaxi.com (international),
    # api.minimax.chat (CN), api.minimax.io. A key issued in one region
    # returns 2049 against the others — set tts_base_url on the tenant
    # to override the default in TenantAIConfig.
    if isinstance(data, dict):
        base_resp = data.get("base_resp") or {}
        if isinstance(base_resp, dict):
            err_code = base_resp.get("status_code")
            if err_code not in (None, 0):
                err_msg = base_resp.get("status_msg") or "unknown"
                raise SpeechSynthesisError(
                    f"minimax error {err_code}: {err_msg}"
                )

    hex_audio = (data.get("data") or {}).get("audio") if isinstance(data, dict) else None
    if not isinstance(hex_audio, str) or not hex_audio.strip():
        raise SpeechSynthesisError(
            f"minimax: no audio in response (keys={list(data.keys()) if isinstance(data, dict) else type(data).__name__})"
        )

    cleaned = hex_audio.strip()
    if len(cleaned) % 2 != 0:
        raise SpeechSynthesisError("minimax: invalid hex audio payload length")
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise SpeechSynthesisError(f"minimax: hex decode failed: {exc}") from exc


# ── ElevenLabs TTS provider ───────────────────────────────────────────
# Mirrors upstream OpenMAIC lib/audio/tts-providers.ts:generateElevenLabsTTS.
# Differences from Minimax (so the test of the abstraction is real):
#   - Auth header is `xi-api-key` (NOT Bearer)
#   - voice_id goes in the URL path: /text-to-speech/{voice}
#   - output_format goes in the query string (not the body)
#   - Response is RAW MP3 bytes (not hex-encoded JSON)
#   - HTTP errors come back as text, no `base_resp` envelope
# Speed is clamped to [0.7, 1.2] per upstream's documented voice_settings
# range; out-of-range values are silently corrected rather than raising.


_ELEVENLABS_OUTPUT_FORMAT: Final[dict[str, str]] = {
    "mp3": "mp3_44100_128",
    "opus": "opus_48000_96",
    "pcm": "pcm_44100",
    "wav": "wav_44100",
    "ulaw": "ulaw_8000",
    "alaw": "alaw_8000",
}


async def _elevenlabs_synthesize(
    text: str,
    *,
    voice: str,
    speed: float,
    api_key: str,
    base_url: str,
    model: str,
) -> bytes:
    if not api_key:
        raise SpeechSynthesisError(
            "elevenlabs: api_key required (set ELEVENLABS_API_KEY or pass per-tenant key)"
        )

    try:
        import aiohttp  # type: ignore[import-untyped]
    except ImportError as exc:
        raise SpeechSynthesisError(
            "aiohttp not installed; pip install -r requirements.txt"
        ) from exc

    from urllib.parse import quote

    clamped_speed = max(0.7, min(1.2, float(speed)))
    output_format = _ELEVENLABS_OUTPUT_FORMAT["mp3"]
    url = (
        f"{base_url.rstrip('/')}/text-to-speech/{quote(voice, safe='')}"
        f"?output_format={output_format}"
    )
    payload = {
        "text": text,
        "model_id": model,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "speed": clamped_speed,
        },
    }
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json; charset=utf-8",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise SpeechSynthesisError(
                        f"elevenlabs: HTTP {resp.status}: {body[:200]}"
                    )
                audio_bytes = await resp.read()
    except aiohttp.ClientError as exc:
        logger.warning("elevenlabs: network error", exc_info=True)
        raise SpeechSynthesisError(f"elevenlabs synthesis failed: {exc}") from exc

    if not audio_bytes:
        raise SpeechSynthesisError("elevenlabs: empty audio body")
    return audio_bytes
