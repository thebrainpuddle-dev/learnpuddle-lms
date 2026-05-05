"""Voice resolver — pick (provider, voice_id, model) for an agent.

Source: THU-MAIC/OpenMAIC lib/audio/voice-resolver.ts (resolveAgentVoice
at lines 23-63). Trimmed to the backend's runtime path: we don't need
the picker-UI discovery functions (getAvailableProvidersWithVoices,
findVoiceDisplayName) here — those are frontend concerns.

Resolution order (highest precedence first):
  1. `agent.voiceConfig` — per-agent override stamped on the AgentConfig.
  2. Tenant default — `TenantAIConfig.tts_provider` + `tts_voice_id`,
     pre-resolved at WS handshake time and passed via state["ttsConfig"].
  3. Provider default voice — when the tenant pins a provider but not a
     voice (e.g. provider=minimax, voice_id=""), each provider supplies
     a sensible default.
  4. Global fallback — edge_tts + Aria (no api key required, free,
     works without any tenant config at all).

This matches the upstream sequencing in spirit: agent override first,
then a sensible default. The backend doesn't need the picker UI's
"validate against available voices" branch because the API call itself
will surface invalid-voice errors loudly via SpeechSynthesisError.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, TYPE_CHECKING

if TYPE_CHECKING:
    from apps.maic.orchestration.registry import AgentConfig


# ── Provider-specific defaults ────────────────────────────────────────


# Mirrors upstream constants.ts:DEFAULT_VOICES_BY_PROVIDER. Keep this in
# sync when adding providers; voices that don't exist will surface as
# loud HTTP errors at synthesis time.
_DEFAULT_VOICE_BY_PROVIDER: Final[dict[str, str]] = {
    "edge": "en-US-AriaNeural",
    "minimax": "female-yujie",
    # placeholders for Phase 5+ / Phase 9
    "voxcpm": "voxcpm:auto",
    "openai": "alloy",
    "elevenlabs": "EXAVITQu4vr4xnSDxMaL",
}


_FALLBACK_PROVIDER: Final = "edge"
_FALLBACK_VOICE: Final = _DEFAULT_VOICE_BY_PROVIDER[_FALLBACK_PROVIDER]


# ── Public types ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class ResolvedVoice:
    """The synthesis-ready bundle the director hands to synthesize_speech.

    `api_key` and `base_url` come from the tenant config (or env
    fallback), passed through unchanged. `provider`/`voice` are decided
    by this resolver per the precedence ladder in the module docstring.
    """

    provider: str
    voice: str
    model: str | None
    api_key: str | None
    base_url: str | None


# ── Public API ────────────────────────────────────────────────────────


def resolve_agent_voice(
    agent: "AgentConfig",
    *,
    tenant_tts_config: dict | None = None,
) -> ResolvedVoice:
    """Resolve the (provider, voice, model, api_key, base_url) bundle
    for one agent's turn.

    Args:
        agent: The AgentConfig from the registry. `agent.voiceConfig`
               (if set) wins over tenant defaults.
        tenant_tts_config: The dict returned by
               `TenantAIConfig.resolve_tts_config()`. Shape:
               `{provider, api_key, base_url, voice}`. None when no
               tenant context (e.g. probe / unit tests).

    Returns:
        ResolvedVoice ready to splat into `synthesize_speech(**resolved)`
        (after dropping the dataclass→dict conversion).
    """
    cfg = tenant_tts_config or {}
    tenant_provider: str | None = cfg.get("provider") or None
    tenant_voice: str | None = cfg.get("voice") or None
    api_key: str | None = cfg.get("api_key") or None
    base_url: str | None = cfg.get("base_url") or None

    # 1. Per-agent override.
    if agent.voiceConfig is not None:
        return ResolvedVoice(
            provider=agent.voiceConfig.providerId,
            voice=agent.voiceConfig.voiceId,
            model=agent.voiceConfig.modelId,
            api_key=api_key,
            base_url=base_url,
        )

    # 2. Tenant provider + tenant voice (or provider default voice).
    if tenant_provider:
        voice = tenant_voice or _DEFAULT_VOICE_BY_PROVIDER.get(
            tenant_provider, _FALLBACK_VOICE,
        )
        return ResolvedVoice(
            provider=tenant_provider,
            voice=voice,
            model=None,
            api_key=api_key,
            base_url=base_url,
        )

    # 3. Global fallback — edge_tts. No tenant, no agent override → this
    # is the Phase 1 default path; preserves backwards compat for tests
    # that don't pass any tenant context.
    return ResolvedVoice(
        provider=_FALLBACK_PROVIDER,
        voice=_FALLBACK_VOICE,
        model=None,
        api_key=None,
        base_url=None,
    )


def to_synthesize_kwargs(resolved: ResolvedVoice) -> dict:
    """Convert ResolvedVoice → kwargs for synthesize_speech, dropping
    None values so the underlying provider env-var fallback still kicks
    in when the tenant didn't pin them."""
    out: dict = {"provider": resolved.provider, "voice": resolved.voice}
    if resolved.model is not None:
        out["model"] = resolved.model
    if resolved.api_key:
        out["api_key"] = resolved.api_key
    if resolved.base_url:
        out["base_url"] = resolved.base_url
    return out
