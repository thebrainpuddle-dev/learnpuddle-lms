"""Unit tests for apps.maic.tts.voice_resolver (MAIC-502).

Resolution ladder:
  1. agent.voiceConfig (per-agent override)
  2. tenant TTS config (provider + voice from TenantAIConfig)
  3. provider default voice
  4. global fallback (edge + Aria)

Each test pins ONE level of the ladder; assertions check that the
expected level wins given the inputs.
"""
from __future__ import annotations

import pytest

from apps.maic.orchestration.registry import AgentConfig, VoiceConfig
from apps.maic.tts.voice_resolver import (
    ResolvedVoice,
    resolve_agent_voice,
    to_synthesize_kwargs,
)


def _agent(voice_config: VoiceConfig | None = None) -> AgentConfig:
    """Minimal AgentConfig — only the fields the resolver reads matter."""
    return AgentConfig(
        id="default-1",
        name="Teacher",
        role="TEACHER",
        persona="A patient classroom teacher.",
        avatar="🧑‍🏫",
        color="#3b82f6",
        allowedActions=["speech"],
        priority=5,
        voiceConfig=voice_config,
    )


# ── Level 1: agent.voiceConfig wins ───────────────────────────────────


def test_agent_voice_config_overrides_tenant():
    agent = _agent(
        VoiceConfig(providerId="elevenlabs", voiceId="custom-clone-xyz", modelId="eleven_v2"),
    )
    resolved = resolve_agent_voice(
        agent,
        tenant_tts_config={"provider": "minimax", "voice": "female-yujie", "api_key": "k"},
    )
    assert resolved.provider == "elevenlabs"
    assert resolved.voice == "custom-clone-xyz"
    assert resolved.model == "eleven_v2"
    # api_key/base_url still flow through from tenant — provider may
    # share auth with whatever the tenant has set.
    assert resolved.api_key == "k"


def test_agent_voice_config_no_tenant_context():
    agent = _agent(
        VoiceConfig(providerId="minimax", voiceId="male-qn-qingse"),
    )
    resolved = resolve_agent_voice(agent, tenant_tts_config=None)
    assert resolved.provider == "minimax"
    assert resolved.voice == "male-qn-qingse"
    assert resolved.api_key is None  # no env fallback at resolver level


# ── Level 2: tenant config when no agent override ─────────────────────


def test_tenant_provider_and_voice_used():
    agent = _agent(voice_config=None)
    resolved = resolve_agent_voice(
        agent,
        tenant_tts_config={
            "provider": "minimax",
            "voice": "english-female-narrator",
            "api_key": "tenant-key",
            "base_url": "https://custom.example.com",
        },
    )
    assert resolved.provider == "minimax"
    assert resolved.voice == "english-female-narrator"
    assert resolved.api_key == "tenant-key"
    assert resolved.base_url == "https://custom.example.com"


def test_tenant_provider_without_voice_uses_provider_default():
    """Tenant pinned a provider but didn't pick a voice — resolver
    fills in the provider's documented default voice."""
    agent = _agent(voice_config=None)
    resolved = resolve_agent_voice(
        agent,
        tenant_tts_config={"provider": "minimax", "voice": "", "api_key": "k"},
    )
    assert resolved.provider == "minimax"
    assert resolved.voice == "female-yujie"  # _DEFAULT_VOICE_BY_PROVIDER["minimax"]


# ── Level 4: global fallback (no agent voice, no tenant) ──────────────


def test_global_fallback_to_edge_aria():
    agent = _agent(voice_config=None)
    resolved = resolve_agent_voice(agent, tenant_tts_config=None)
    assert resolved.provider == "edge"
    assert resolved.voice == "en-US-AriaNeural"
    assert resolved.api_key is None
    assert resolved.base_url is None


def test_empty_tenant_dict_is_same_as_none():
    """resolve_tts_config() may return a dict with all-empty values
    when a TenantAIConfig row exists but has no provider set yet.
    Must be equivalent to None."""
    agent = _agent(voice_config=None)
    resolved = resolve_agent_voice(
        agent,
        tenant_tts_config={"provider": None, "voice": None, "api_key": "", "base_url": None},
    )
    assert resolved.provider == "edge"
    assert resolved.voice == "en-US-AriaNeural"


# ── to_synthesize_kwargs() shape ──────────────────────────────────────


def test_to_synthesize_kwargs_drops_none_lets_provider_env_fallback_kick_in():
    """Don't pass api_key=None — that overrides synthesize_speech's
    env-var fallback. Drop the key entirely so the env path is taken."""
    resolved = ResolvedVoice(
        provider="minimax", voice="female-yujie", model=None,
        api_key=None, base_url=None,
    )
    kwargs = to_synthesize_kwargs(resolved)
    assert kwargs == {"provider": "minimax", "voice": "female-yujie"}
    assert "api_key" not in kwargs
    assert "base_url" not in kwargs
    assert "model" not in kwargs


def test_to_synthesize_kwargs_passes_all_when_set():
    resolved = ResolvedVoice(
        provider="minimax", voice="vx", model="speech-2.5",
        api_key="k", base_url="https://x",
    )
    assert to_synthesize_kwargs(resolved) == {
        "provider": "minimax",
        "voice": "vx",
        "model": "speech-2.5",
        "api_key": "k",
        "base_url": "https://x",
    }


def test_to_synthesize_kwargs_drops_empty_string_api_key():
    """resolve_tts_config returns api_key='' (empty str) when the row
    has no encrypted blob. Empty strings are falsy → drop, let env-var
    fallback in synthesize_speech kick in."""
    resolved = ResolvedVoice(
        provider="minimax", voice="vx", model=None,
        api_key="", base_url="",
    )
    kwargs = to_synthesize_kwargs(resolved)
    assert "api_key" not in kwargs
    assert "base_url" not in kwargs
