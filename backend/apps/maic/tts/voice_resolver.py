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


# ── Per-provider voice rotation for multi-agent differentiation ──────
#
# Mirrors upstream lib/audio/voice-resolver.ts:resolveAgentVoice's
# `availableProviders[0].voices[agentIndex % first.voices.length]`
# fallback (lines 53-60). Without this, six default classroom agents
# with no per-agent voiceConfig would all share the tenant's single
# voice — bad UX. We hash the agent.id deterministically into a small
# voice rotation so each agent gets a distinct voice without requiring
# an `agentIndex` parameter at the call site.
#
# Voice ids are taken from upstream OpenMAIC `lib/audio/constants.ts`
# (TTS_PROVIDERS['minimax-tts'].voices and TTS_PROVIDERS['azure-tts']
# / Edge — same Microsoft Neural catalog). These are the same voice
# slugs that ship with upstream so listening parity holds.
_VOICE_ROTATION_BY_PROVIDER: Final[dict[str, tuple[str, ...]]] = {
    "minimax": (
        "female-yujie",          # warm mature female — slot 0 (teacher)
        "male-qn-jingying",      # confident male — slot 1 (assistant)
        "female-shaonv",         # bright young female — slot 2
        "male-qn-qingse",        # younger male — slot 3
        "audiobook_female_1",    # narrator female — slot 4
        "audiobook_male_1",      # narrator male — slot 5
    ),
    "edge": (
        "en-US-AriaNeural",      # warm female
        "en-US-GuyNeural",       # neutral male
        "en-US-JennyNeural",     # friendly female
        "en-US-DavisNeural",     # warm male
        "en-US-AmberNeural",     # bright female
        "en-US-BrandonNeural",   # young male
    ),
}


def _rotate_voice(provider: str, agent_id: str) -> str | None:
    """Pick a voice from the provider's rotation deterministically by
    agent_id. Returns None when the provider has no rotation configured
    (caller should fall back to provider default). Uses hashlib.md5 (not
    Python's built-in hash) so the assignment is stable across Python
    invocations — important for cross-session consistency."""
    import hashlib

    rotation = _VOICE_ROTATION_BY_PROVIDER.get(provider)
    if not rotation:
        return None
    digest = hashlib.md5(agent_id.encode("utf-8")).digest()
    idx = int.from_bytes(digest[:4], "big") % len(rotation)
    return rotation[idx]


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

    # 2. Tenant provider + tenant voice (or rotated voice for multi-
    # agent classrooms when tenant didn't pin a voice).
    if tenant_provider:
        if tenant_voice:
            # Tenant explicitly pinned a voice — every agent gets it.
            # This is the right call for single-tutor or branded
            # deployments where consistency matters.
            voice = tenant_voice
        else:
            # No tenant voice → distribute the provider's voice catalog
            # across agents so each one sounds distinct (mirrors
            # upstream's agentIndex % first.voices.length pattern).
            # Falls back to the provider's static default when no
            # rotation is configured for that provider.
            voice = _rotate_voice(tenant_provider, agent.id) or (
                _DEFAULT_VOICE_BY_PROVIDER.get(tenant_provider, _FALLBACK_VOICE)
            )
        return ResolvedVoice(
            provider=tenant_provider,
            voice=voice,
            model=None,
            api_key=api_key,
            base_url=base_url,
        )

    # 3. Global fallback — edge_tts + Aria. No tenant context means we
    # may be in a probe, a unit test, or a misconfigured deployment.
    # Default to a single predictable voice rather than rotating; multi-
    # agent rotation only kicks in once a tenant has *opted into* a
    # provider but skipped pinning a voice (the level-2 branch above).
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
