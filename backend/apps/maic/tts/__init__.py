"""Text-to-Speech service — agent text items → audio bytes.

Phase 1 ships an edge_tts-backed default provider:

  - edge_tts (Microsoft Edge's free TTS over a public WebSocket) is
    already in our requirements.txt at >=7.2.8 — see
    /Volumes/CrucialX9/learnpuddle-lms/backend/requirements.txt:83
  - Returns MP3 bytes; pure-async, no API key.
  - Used as the default for MAIC v2 in Phase 1; Phase 5 swaps for
    VoxCPM2 (self-hosted, voice-clonable, much higher quality).

The module exports a single high-level function `synthesize_speech`
that the agent_generate node (MAIC-501.2) calls per text item from the
LLM stream. It returns a `SpeechAudio` result the consumer turns into
a `speech_audio` event frame.

Provider selection is env-driven — `MAIC_TTS_PROVIDER` defaults to
`edge`. When new providers land in Phase 5 (`voxcpm`, `minimax`, etc.)
they slot in here behind the same call signature.
"""
from .service import (
    SpeechAudio,
    SpeechSynthesisError,
    synthesize_speech,
)

__all__ = [
    "SpeechAudio",
    "SpeechSynthesisError",
    "synthesize_speech",
]
