"""Tests for apps.maic.orchestration.ai_adapter.

The stub-mode tests exercise the full streaming machinery without any
network or API key. The real-model tests exercise the model-id resolver
(no LLM call — just construction)."""
from __future__ import annotations

import asyncio
import os

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from apps.maic.exceptions import MaicConfigError, MaicProviderError
from apps.maic.orchestration.ai_adapter import (
    STUB_OUTPUT,
    resolve_chat_model,
    stream_text,
)


# ── stub mode — deterministic streaming ───────────────────────────────


@pytest.mark.asyncio
async def test_stub_stream_emits_full_output_across_chunks():
    """The stub emits STUB_OUTPUT in slices; concatenating yielded
    chunks must equal STUB_OUTPUT exactly (no duplication, no loss)."""
    chunks = []
    async for c in stream_text([], "stub"):
        chunks.append(c)
    assert "".join(chunks) == STUB_OUTPUT


@pytest.mark.asyncio
async def test_stub_stream_yields_more_than_one_chunk():
    """Tests downstream of this should exercise chunk-by-chunk parsing,
    so the stub MUST chunk (not yield the whole output as one slice)."""
    chunk_count = 0
    async for _ in stream_text([], "stub"):
        chunk_count += 1
    assert chunk_count > 1, "stub must yield multiple chunks for parser realism"


@pytest.mark.asyncio
async def test_stub_output_is_valid_structured_json():
    """STUB_OUTPUT must be parseable by parse_structured_chunk so
    agent_generate end-to-end (MAIC-105.3+) gets a deterministic
    sequence: one text item + one wb_open action.  The action MUST be
    in the teacher's allowedActions (whiteboard family) so validation
    passes."""
    import json
    parsed = json.loads(STUB_OUTPUT)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed[0]["type"] == "text"
    assert parsed[1]["type"] == "action"
    assert parsed[1]["name"] == "wb_open"


# ── resolve_chat_model — real-model resolver ──────────────────────────


def test_resolve_stub_explicitly_rejects():
    """resolve_chat_model is for real LLMs only — the stub path is
    handled separately in stream_text."""
    with pytest.raises(MaicConfigError, match="stub"):
        resolve_chat_model("stub")


def test_resolve_unknown_id_raises_config_error():
    with pytest.raises(MaicConfigError, match="unknown"):
        resolve_chat_model("totally-made-up-model")


def test_resolve_anthropic_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(MaicConfigError, match="ANTHROPIC_API_KEY"):
        resolve_chat_model("claude-sonnet-4-5")


def test_resolve_openai_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(MaicConfigError, match="OPENAI_API_KEY"):
        resolve_chat_model("gpt-4.1")


def test_resolve_anthropic_with_key_returns_chat_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-not-a-real-key-just-test")
    from langchain_anthropic import ChatAnthropic
    model = resolve_chat_model("claude-sonnet-4-5-20250929")
    assert isinstance(model, ChatAnthropic)


def test_resolve_anthropic_strips_provider_prefix(monkeypatch):
    """`anthropic/claude-…` form is accepted — strips the prefix when
    constructing the model_name."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    from langchain_anthropic import ChatAnthropic
    model = resolve_chat_model("anthropic/claude-sonnet-4-5-20250929")
    assert isinstance(model, ChatAnthropic)
    # langchain-anthropic stores the model name in `model` attribute
    assert "claude-sonnet-4-5" in str(model.model)


def test_resolve_openai_with_key_returns_chat_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from langchain_openai import ChatOpenAI
    model = resolve_chat_model("gpt-4.1")
    assert isinstance(model, ChatOpenAI)


def test_resolve_openai_o_series_models(monkeypatch):
    """o1/o3/o4 reasoning models are OpenAI family — must resolve via
    the same path."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from langchain_openai import ChatOpenAI
    assert isinstance(resolve_chat_model("o1-mini"), ChatOpenAI)
    assert isinstance(resolve_chat_model("o3"), ChatOpenAI)


# ── stream_text — error wrapping ──────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_text_unknown_id_raises_config_error():
    with pytest.raises(MaicConfigError):
        async for _ in stream_text([HumanMessage(content="hi")], "no-such-model"):
            pass


@pytest.mark.asyncio
async def test_stream_text_anthropic_without_key_raises_config(monkeypatch):
    """Cleanly surfaces config error rather than letting langchain raise
    a less informative provider error."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(MaicConfigError, match="ANTHROPIC_API_KEY"):
        async for _ in stream_text([HumanMessage(content="x")], "claude-sonnet-4-5"):
            pass


# ── Determinism check (regression net for end-to-end smoke) ───────────


@pytest.mark.asyncio
async def test_stub_stream_is_deterministic():
    """Two stub runs must produce identical output (no time/random
    nondeterminism). The MAIC-105.4 end-to-end smoke depends on this."""
    run_1 = "".join([c async for c in stream_text([], "stub")])
    run_2 = "".join([c async for c in stream_text([], "stub")])
    assert run_1 == run_2 == STUB_OUTPUT
