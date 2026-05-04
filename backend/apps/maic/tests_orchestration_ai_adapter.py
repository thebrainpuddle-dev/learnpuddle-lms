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


# ── generate_text (Phase 4 / MAIC-433) ─────────────────────────────


@pytest.mark.asyncio
async def test_generate_text_against_stub_returns_full_stub_output():
    """`generate_text` must drain `stream_text` and return the joined
    string — Phase 4's generation pipeline relies on a complete string
    for json_repair.parse_json_response."""
    from apps.maic.orchestration.ai_adapter import generate_text, STUB_OUTPUT
    text = await generate_text([], "stub")
    assert text == STUB_OUTPUT


@pytest.mark.asyncio
async def test_generate_text_is_deterministic_across_calls():
    """Two calls with the same input return the same output. Critical
    for the ADR-005 parity test — golden outputs only stay stable if
    the generation calls are deterministic."""
    from apps.maic.orchestration.ai_adapter import generate_text
    a = await generate_text([], "stub")
    b = await generate_text([], "stub")
    assert a == b


@pytest.mark.asyncio
async def test_generate_text_default_temperature_is_zero():
    """Generation calls default to temperature=0 (deterministic) —
    distinct from stream_text's 0.7 default. Lock the contract so a
    future refactor doesn't accidentally re-introduce non-determinism
    into generation calls (which would flake the parity test)."""
    import inspect
    from apps.maic.orchestration.ai_adapter import generate_text
    sig = inspect.signature(generate_text)
    assert sig.parameters["temperature"].default == 0.0


@pytest.mark.asyncio
async def test_generate_text_with_stub_director_returns_one_decision():
    """`stub-director` cycles through 4 decisions; one call returns
    exactly one decision (the cycle counter advances)."""
    from apps.maic.orchestration.ai_adapter import (
        generate_text,
        reset_director_stub_counter,
    )
    reset_director_stub_counter()
    text = await generate_text([], "stub-director")
    # Whatever the first decision is, must be a valid JSON shape
    import json
    parsed = json.loads(text)
    assert "next_agent" in parsed


@pytest.mark.asyncio
async def test_generate_text_propagates_unknown_provider_error():
    """generate_text doesn't swallow MaicConfigError — generation's
    GenerationResult envelope wraps these explicitly upstream."""
    from apps.maic.orchestration.ai_adapter import generate_text
    from apps.maic.exceptions import MaicConfigError
    with pytest.raises(MaicConfigError):
        await generate_text([], "totally-unknown-provider-xyz")


@pytest.mark.asyncio
async def test_generate_text_returns_empty_string_for_empty_stream():
    """Defensive: if a future provider yields zero chunks (e.g. an
    error path that gracefully returns nothing), generate_text must
    return '' rather than raising or hanging."""
    from apps.maic.orchestration import ai_adapter
    from apps.maic.orchestration.ai_adapter import generate_text

    async def _empty_stream(*args, **kwargs):
        return
        yield  # unreachable; makes this a generator

    # Replace stream_text in the module for this one test
    original = ai_adapter.stream_text
    ai_adapter.stream_text = _empty_stream  # type: ignore[assignment]
    try:
        text = await generate_text([], "stub")
        assert text == ""
    finally:
        ai_adapter.stream_text = original  # type: ignore[assignment]
