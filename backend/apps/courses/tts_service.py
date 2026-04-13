"""
Text-to-Speech service with multi-provider support and automatic fallback.

Providers (in priority order):
    1. ElevenLabs  — Highest quality, requires API key (ELEVENLABS_API_KEY)
    2. Edge TTS    — Free Microsoft TTS via edge-tts package, good quality
    3. gTTS        — Google Translate TTS, always available fallback

Usage:
    from apps.courses.tts_service import synthesize_speech, synthesize_podcast_audio

    # Single utterance
    path = synthesize_speech("Hello world", provider="auto")

    # Multi-speaker podcast
    script = [
        {"speaker": "host_a", "text": "Welcome to the show!", "speaker_name": "Alex"},
        {"speaker": "host_b", "text": "Thanks for having me.", "speaker_name": "Sam"},
    ]
    path = synthesize_podcast_audio(script, "/tmp/podcast.mp3")
"""

import asyncio
import logging
import os
import tempfile

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"
_ELEVENLABS_TIMEOUT = 60  # seconds

# Default ElevenLabs voices
_DEFAULT_ELEVENLABS_VOICE_HOST_A = "TX3LPaxmHKxFdv7VOQHJ"  # Liam
_DEFAULT_ELEVENLABS_VOICE_HOST_B = "EXAVITQu4vr4xnSDxMaL"  # Sarah

# Default Edge TTS voices
_DEFAULT_EDGE_VOICE_MALE = "en-US-GuyNeural"
_DEFAULT_EDGE_VOICE_FEMALE = "en-US-JennyNeural"

# Default gTTS language
_DEFAULT_GTTS_LANG = "en"

# Silence duration between podcast segments (milliseconds)
_PODCAST_PAUSE_MS = 400

# Provider names
PROVIDER_ELEVENLABS = "elevenlabs"
PROVIDER_EDGE_TTS = "edge_tts"
PROVIDER_GTTS = "gtts"
PROVIDER_AUTO = "auto"

_PROVIDER_PRIORITY = [PROVIDER_ELEVENLABS, PROVIDER_EDGE_TTS, PROVIDER_GTTS]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def synthesize_speech(
    text: str,
    voice_id: str = "",
    provider: str = "auto",
    output_path: str = "",
    speed: float = 1.0,
) -> str | None:
    """
    Synthesize speech from text.

    Returns the absolute file path of the generated audio (MP3), or None
    on failure.

    Args:
        text: The text to convert to speech.
        voice_id: Provider-specific voice identifier. If empty, a sensible
            default is used for the chosen provider.
        provider: One of ``"elevenlabs"``, ``"edge_tts"``, ``"gtts"``, or
            ``"auto"`` (tries all providers in priority order until one
            succeeds).
        output_path: Absolute path where the audio file should be saved.
            If empty, a named temporary file is created (caller is
            responsible for cleanup).
        speed: Playback speed multiplier (1.0 = normal). Supported by
            Edge TTS and gTTS; ignored for ElevenLabs (use voice settings
            on the ElevenLabs dashboard instead).

    Returns:
        Absolute path to the generated MP3 file, or ``None`` if every
        provider failed.
    """
    text = (text or "").strip()
    if not text:
        logger.warning("synthesize_speech: empty text, nothing to synthesize")
        return None

    if provider == PROVIDER_AUTO:
        return _synthesize_with_fallback(text, voice_id, output_path, speed)

    audio_bytes = _dispatch_provider(provider, text, voice_id, speed)
    if audio_bytes is None:
        logger.warning(
            "synthesize_speech: provider '%s' returned no audio", provider
        )
        return None

    return _write_audio(audio_bytes, output_path)


def synthesize_podcast_audio(
    script: list[dict],
    output_path: str,
    host_a_voice: str = "",
    host_b_voice: str = "",
) -> str | None:
    """
    Synthesize a multi-speaker podcast from a script.

    Each entry in *script* is a dict with at least::

        {"speaker": "host_a"|"host_b", "text": "..."}

    An optional ``"speaker_name"`` key can be included for logging.

    All individual segments are concatenated into a single MP3 file with
    brief pauses between speakers.

    Args:
        script: Ordered list of speaker segments.
        output_path: Where to save the final concatenated audio file.
        host_a_voice: Voice ID for host_a (provider default if empty).
        host_b_voice: Voice ID for host_b (provider default if empty).

    Returns:
        Absolute path to the final podcast MP3, or ``None`` on failure.
    """
    if not script:
        logger.warning("synthesize_podcast_audio: empty script")
        return None

    try:
        from pydub import AudioSegment
    except ImportError:
        logger.error(
            "synthesize_podcast_audio: pydub is not installed. "
            "Install it with: pip install pydub"
        )
        return None

    # Resolve default voices per provider — we try ElevenLabs voices first,
    # but the fallback chain will pick appropriate defaults when needed.
    voice_a = host_a_voice or _DEFAULT_ELEVENLABS_VOICE_HOST_A
    voice_b = host_b_voice or _DEFAULT_ELEVENLABS_VOICE_HOST_B

    # Build a short silence segment for pauses between speakers
    pause = AudioSegment.silent(duration=_PODCAST_PAUSE_MS)

    combined = AudioSegment.empty()
    segments_ok = 0
    segments_total = len(script)

    for idx, entry in enumerate(script):
        speaker = entry.get("speaker", "host_a")
        text = (entry.get("text") or "").strip()
        speaker_name = entry.get("speaker_name", speaker)

        if not text:
            logger.debug(
                "synthesize_podcast_audio: skipping empty segment %d (%s)",
                idx,
                speaker_name,
            )
            continue

        voice = voice_a if speaker == "host_a" else voice_b

        # Synthesize this segment to a temp file
        segment_path = synthesize_speech(
            text=text,
            voice_id=voice,
            provider=PROVIDER_AUTO,
        )

        if segment_path is None:
            logger.warning(
                "synthesize_podcast_audio: failed segment %d/%d (%s): '%s'",
                idx + 1,
                segments_total,
                speaker_name,
                text[:80],
            )
            continue

        try:
            segment_audio = AudioSegment.from_file(segment_path, format="mp3")
            if combined.duration_seconds > 0:
                combined += pause
            combined += segment_audio
            segments_ok += 1
        except Exception as e:
            logger.warning(
                "synthesize_podcast_audio: could not load segment %d audio: %s",
                idx,
                e,
            )
        finally:
            # Clean up temp segment file
            try:
                os.remove(segment_path)
            except OSError:
                pass

    if segments_ok == 0:
        logger.error(
            "synthesize_podcast_audio: no segments synthesized successfully"
        )
        return None

    # Export concatenated audio
    try:
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        combined.export(output_path, format="mp3", bitrate="192k")
        logger.info(
            "synthesize_podcast_audio: exported %d/%d segments, "
            "duration=%.1fs, path=%s",
            segments_ok,
            segments_total,
            combined.duration_seconds,
            output_path,
        )
        return os.path.abspath(output_path)
    except Exception as e:
        logger.error("synthesize_podcast_audio: export failed: %s", e)
        return None


def get_available_voices(provider: str = "elevenlabs") -> list[dict]:
    """
    Return a list of available voices for the given provider.

    Each voice is returned as a dict with at least ``name`` and ``voice_id``
    keys. Additional metadata may be included depending on the provider.

    Args:
        provider: ``"elevenlabs"``, ``"edge_tts"``, or ``"gtts"``.

    Returns:
        List of voice dicts. Returns an empty list on error or if the
        provider is not available.
    """
    if provider == PROVIDER_ELEVENLABS:
        return _get_elevenlabs_voices()
    if provider == PROVIDER_EDGE_TTS:
        return _get_edge_tts_voices()
    if provider == PROVIDER_GTTS:
        return _get_gtts_voices()

    logger.warning("get_available_voices: unknown provider '%s'", provider)
    return []


# ---------------------------------------------------------------------------
# Internal: Fallback orchestration
# ---------------------------------------------------------------------------


def _synthesize_with_fallback(
    text: str,
    voice_id: str,
    output_path: str,
    speed: float,
) -> str | None:
    """
    Try each provider in priority order until one succeeds.

    Returns the file path on success, or None if all providers fail.
    """
    for provider in _PROVIDER_PRIORITY:
        audio_bytes = _dispatch_provider(provider, text, voice_id, speed)
        if audio_bytes:
            path = _write_audio(audio_bytes, output_path)
            if path:
                logger.info(
                    "synthesize_speech: success with provider '%s'", provider
                )
                return path
        logger.debug(
            "synthesize_speech: provider '%s' failed, trying next", provider
        )

    logger.error("synthesize_speech: all providers failed for text: '%.80s...'", text)
    return None


def _dispatch_provider(
    provider: str,
    text: str,
    voice_id: str,
    speed: float,
) -> bytes | None:
    """
    Dispatch synthesis to the specified provider.

    Returns raw audio bytes (MP3), or None on failure.
    """
    try:
        if provider == PROVIDER_ELEVENLABS:
            return _run_elevenlabs(text, voice_id)
        if provider == PROVIDER_EDGE_TTS:
            return _run_edge_tts(text, voice_id, speed)
        if provider == PROVIDER_GTTS:
            return _run_gtts(text, voice_id, speed)
        logger.warning("_dispatch_provider: unknown provider '%s'", provider)
    except Exception as e:
        logger.warning("_dispatch_provider(%s) error: %s", provider, e)
    return None


# ---------------------------------------------------------------------------
# Internal: ElevenLabs
# ---------------------------------------------------------------------------


def _get_elevenlabs_api_key() -> str:
    """Retrieve the ElevenLabs API key from Django settings."""
    key = getattr(settings, "ELEVENLABS_API_KEY", "") or ""
    return key.strip()


def _run_elevenlabs(text: str, voice_id: str) -> bytes | None:
    """
    Synthesize speech via the ElevenLabs REST API.

    Returns MP3 audio bytes, or None on failure.
    """
    api_key = _get_elevenlabs_api_key()
    if not api_key:
        logger.debug("ElevenLabs: no API key configured, skipping")
        return None

    voice_id = voice_id or _DEFAULT_ELEVENLABS_VOICE_HOST_A

    try:
        resp = requests.post(
            f"{_ELEVENLABS_API_BASE}/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "style": 0.0,
                    "use_speaker_boost": True,
                },
            },
            timeout=_ELEVENLABS_TIMEOUT,
        )

        if resp.status_code == 200:
            content = resp.content
            if content and len(content) > 100:
                logger.info(
                    "ElevenLabs: synthesized %d bytes (voice=%s)",
                    len(content),
                    voice_id,
                )
                return content
            logger.warning(
                "ElevenLabs: response too small (%d bytes)",
                len(content) if content else 0,
            )
            return None

        logger.warning(
            "ElevenLabs: HTTP %d — %s",
            resp.status_code,
            resp.text[:300],
        )
        return None
    except requests.exceptions.Timeout:
        logger.warning("ElevenLabs: request timed out after %ds", _ELEVENLABS_TIMEOUT)
        return None
    except requests.exceptions.ConnectionError as e:
        logger.warning("ElevenLabs: connection error: %s", e)
        return None
    except Exception as e:
        logger.warning("ElevenLabs: unexpected error: %s", e)
        return None


def _get_elevenlabs_voices() -> list[dict]:
    """Fetch available voices from the ElevenLabs API."""
    api_key = _get_elevenlabs_api_key()
    if not api_key:
        logger.debug("ElevenLabs: no API key, returning empty voice list")
        return []

    try:
        resp = requests.get(
            f"{_ELEVENLABS_API_BASE}/voices",
            headers={"xi-api-key": api_key},
            timeout=15,
        )
        if resp.status_code == 200:
            voices_data = resp.json().get("voices", [])
            return [
                {
                    "voice_id": v.get("voice_id", ""),
                    "name": v.get("name", ""),
                    "category": v.get("category", ""),
                    "labels": v.get("labels", {}),
                    "preview_url": v.get("preview_url", ""),
                    "provider": PROVIDER_ELEVENLABS,
                }
                for v in voices_data
            ]
        logger.warning(
            "ElevenLabs voices: HTTP %d — %s",
            resp.status_code,
            resp.text[:200],
        )
    except Exception as e:
        logger.warning("ElevenLabs voices: error: %s", e)

    return []


# ---------------------------------------------------------------------------
# Internal: Edge TTS (Microsoft)
# ---------------------------------------------------------------------------


def _run_edge_tts(text: str, voice_id: str, speed: float = 1.0) -> bytes | None:
    """
    Synthesize speech using the edge-tts package (async, wrapped with
    asyncio).

    Returns MP3 audio bytes, or None on failure.
    """
    try:
        import edge_tts
    except ImportError:
        logger.debug("edge-tts: package not installed, skipping")
        return None

    voice = voice_id or _DEFAULT_EDGE_VOICE_MALE

    # Edge TTS accepts a rate string like "+20%" or "-10%"
    rate_str = _speed_to_edge_rate(speed)

    async def _synthesize() -> bytes:
        communicate = edge_tts.Communicate(text, voice, rate=rate_str)
        audio_chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
        return b"".join(audio_chunks)

    try:
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(_synthesize())
        finally:
            loop.close()

        if result and len(result) > 100:
            logger.info(
                "Edge TTS: synthesized %d bytes (voice=%s)", len(result), voice
            )
            return result
        logger.warning("Edge TTS: empty or too-small result")
        return None
    except Exception as e:
        logger.warning("Edge TTS: synthesis failed: %s", e)
        return None


def _speed_to_edge_rate(speed: float) -> str:
    """Convert a numeric speed multiplier to an Edge TTS rate string."""
    if abs(speed - 1.0) < 0.01:
        return "+0%"
    pct = int((speed - 1.0) * 100)
    return f"{pct:+d}%"


def _get_edge_tts_voices() -> list[dict]:
    """Fetch available voices from Edge TTS."""
    try:
        import edge_tts
    except ImportError:
        logger.debug("edge-tts: package not installed")
        return []

    async def _list_voices():
        return await edge_tts.list_voices()

    try:
        loop = asyncio.new_event_loop()
        try:
            voices_raw = loop.run_until_complete(_list_voices())
        finally:
            loop.close()

        return [
            {
                "voice_id": v.get("ShortName", ""),
                "name": v.get("FriendlyName", v.get("ShortName", "")),
                "gender": v.get("Gender", ""),
                "locale": v.get("Locale", ""),
                "provider": PROVIDER_EDGE_TTS,
            }
            for v in voices_raw
        ]
    except Exception as e:
        logger.warning("Edge TTS voices: error: %s", e)
        return []


# ---------------------------------------------------------------------------
# Internal: gTTS (Google Translate TTS)
# ---------------------------------------------------------------------------


def _run_gtts(text: str, voice_id: str, speed: float = 1.0) -> bytes | None:
    """
    Synthesize speech using the gTTS (Google Translate TTS) package.

    The *voice_id* parameter is interpreted as the language code (e.g.
    ``"en"``, ``"es"``). Defaults to English.

    Returns MP3 audio bytes, or None on failure.
    """
    try:
        from gtts import gTTS
    except ImportError:
        logger.debug("gTTS: package not installed, skipping")
        return None

    lang = voice_id if voice_id and len(voice_id) <= 5 else _DEFAULT_GTTS_LANG
    slow = speed < 0.8

    try:
        tts = gTTS(text=text, lang=lang, slow=slow)

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
            tts.save(tmp_path)

        try:
            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

        if audio_bytes and len(audio_bytes) > 100:
            logger.info(
                "gTTS: synthesized %d bytes (lang=%s)", len(audio_bytes), lang
            )
            return audio_bytes
        logger.warning("gTTS: empty or too-small result")
        return None
    except Exception as e:
        logger.warning("gTTS: synthesis failed: %s", e)
        return None


def _get_gtts_voices() -> list[dict]:
    """Return a curated list of commonly used gTTS languages as voices."""
    # gTTS doesn't have a real "voice list" — it supports language codes.
    # Return a useful subset for educational content.
    languages = [
        ("en", "English"),
        ("es", "Spanish"),
        ("fr", "French"),
        ("de", "German"),
        ("pt", "Portuguese"),
        ("it", "Italian"),
        ("ja", "Japanese"),
        ("ko", "Korean"),
        ("zh-CN", "Chinese (Simplified)"),
        ("hi", "Hindi"),
        ("ar", "Arabic"),
        ("ru", "Russian"),
        ("nl", "Dutch"),
        ("pl", "Polish"),
        ("tr", "Turkish"),
    ]
    return [
        {
            "voice_id": code,
            "name": name,
            "provider": PROVIDER_GTTS,
        }
        for code, name in languages
    ]


# ---------------------------------------------------------------------------
# Internal: File I/O helpers
# ---------------------------------------------------------------------------


def _write_audio(audio_bytes: bytes, output_path: str) -> str | None:
    """
    Write audio bytes to *output_path* (or a temp file if empty).

    Returns the absolute path to the written file, or None on failure.
    """
    if not audio_bytes:
        return None

    try:
        if output_path:
            out_dir = os.path.dirname(output_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(audio_bytes)
            return os.path.abspath(output_path)

        # No output path specified — use a named temp file
        with tempfile.NamedTemporaryFile(
            suffix=".mp3", delete=False, prefix="tts_"
        ) as tmp:
            tmp.write(audio_bytes)
            return os.path.abspath(tmp.name)
    except Exception as e:
        logger.error("_write_audio: failed to write audio file: %s", e)
        return None
