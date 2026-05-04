"""AI adapter — resolve a `language_model_id` string to a streaming LLM call.

Replaces upstream's Vercel AI SDK + LangChain glue (lib/orchestration/
ai-sdk-adapter.ts, 156 lines). We talk to LLM providers directly through
langchain-anthropic / langchain-openai, with `litellm` available as a
broader fallback for providers we haven't wired explicitly yet.

Used by:
    apps/maic/orchestration/director_graph._agent_generate_node
    (MAIC-105.3) — the agent_generate node calls `stream_text(...)` to
    pipe the LLM's structured-JSON output through parse_structured_chunk.

Model ID resolution:
    "stub"                              → deterministic in-process stream
                                           (used by tests + dev probe;
                                            no network, no API key)
    "claude-…"                          → ChatAnthropic (env: ANTHROPIC_API_KEY)
    "gpt-…", "openai/…"                 → ChatOpenAI    (env: OPENAI_API_KEY)
    everything else                     → MaicConfigError

Why a stub mode at all:
    The Phase-1 acceptance contract requires the WS pipe + classroom
    smoke to be exercisable WITHOUT live API credentials in CI. The
    stub mode emits the same JSON-array structured output a real model
    would, so the parser + director loop run identically. Production
    paths NEVER pass model_id="stub" (the HTTP session route picks the
    real default).
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import AsyncIterator, Final

from langchain_core.messages import BaseMessage

from apps.maic.exceptions import MaicConfigError, MaicProviderError

logger = logging.getLogger(__name__)


# ── Model ID resolution ───────────────────────────────────────────────


# Default models when caller doesn't specify a concrete model id but
# does specify a provider family. Picked to balance latency and quality
# at Phase-1 demo time; production callers should pass an explicit ID.
_DEFAULT_ANTHROPIC_MODEL: Final = "claude-sonnet-4-5-20250929"
_DEFAULT_OPENAI_MODEL: Final = "gpt-4.1"

# Stream chunk size for the stub: yield one ~30-char slice at a time so
# tests exercise the chunk-by-chunk parser, not just one shot.
_STUB_CHUNK_SIZE: Final = 30

# The stub's structured-output payload. Mirrors what an upstream live
# agent's LLM emits: text items become `text_delta` events (TTS handled
# downstream by the playback engine), action items become `action`
# events.  Live upstream agents do NOT emit explicit "speech" actions —
# the spoken content is the `text` item itself.  We include one wb_open
# action so the validation + whiteboard-ledger paths in agent_generate
# fire under the stub.
STUB_OUTPUT: Final[str] = (
    '[\n'
    '  {"type":"text","content":"Hello students. Today we will learn '
    'about the topic at hand."},\n'
    '  {"type":"action","name":"wb_open","params":{}}\n'
    ']'
)

# Director-stub output (Phase 3 / MAIC-104.1).  The director_node's
# LLM call expects a JSON decision; the regular STUB_OUTPUT is shaped
# for agent_generate. This second stub returns a deterministic
# next_agent decision so dev runs + tests can exercise the
# multi-agent director without burning real LLM credits. Cycles
# through agents based on a counter so successive calls return
# different next_agent values (lets tests verify multi-turn dispatch).
DIRECTOR_STUB_OUTPUTS: Final[tuple[str, ...]] = (
    '{"next_agent": "default-1"}',
    '{"next_agent": "default-3"}',
    '{"next_agent": "default-4"}',
    '{"next_agent": "END"}',
)
_director_stub_counter = 0


def _next_director_stub_output() -> str:
    """Round-robin pick from DIRECTOR_STUB_OUTPUTS so back-to-back
    calls return distinct decisions."""
    global _director_stub_counter
    out = DIRECTOR_STUB_OUTPUTS[_director_stub_counter % len(DIRECTOR_STUB_OUTPUTS)]
    _director_stub_counter += 1
    return out


def reset_director_stub_counter() -> None:
    """Test helper — reset the round-robin counter between tests."""
    global _director_stub_counter
    _director_stub_counter = 0


def resolve_chat_model(language_model_id: str):
    """Build a langchain BaseChatModel for the given id.

    Stub model is handled separately by stream_text — this function is
    only called for real LLM paths.

    Raises:
        MaicConfigError: unknown id, missing API key, or import failure.
    """
    if language_model_id == "stub":
        raise MaicConfigError(
            "resolve_chat_model is for real LLMs only; stub is handled in stream_text"
        )

    lid = language_model_id.lower()

    # Anthropic family
    if lid.startswith("claude-") or lid.startswith("anthropic/"):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise MaicConfigError(
                "ANTHROPIC_API_KEY is required to call Anthropic models"
            )
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise MaicConfigError("langchain-anthropic not installed") from exc

        model_name = (
            language_model_id.removeprefix("anthropic/")
            if lid.startswith("anthropic/")
            else language_model_id
        )
        return ChatAnthropic(
            model_name=model_name,
            timeout=60,
            stop=None,
        )

    # OpenAI family (incl. providers that emulate OpenAI's API).
    # Reasoning models accept both bare ("o3") and dashed ("o3-mini") forms.
    if (
        lid.startswith("gpt-")
        or lid.startswith("openai/")
        or lid in {"o1", "o3", "o4"}
        or lid.startswith("o1-")
        or lid.startswith("o3-")
        or lid.startswith("o4-")
    ):
        if not os.environ.get("OPENAI_API_KEY"):
            raise MaicConfigError(
                "OPENAI_API_KEY is required to call OpenAI models"
            )
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise MaicConfigError("langchain-openai not installed") from exc

        model_name = (
            language_model_id.removeprefix("openai/")
            if lid.startswith("openai/")
            else language_model_id
        )
        return ChatOpenAI(
            model=model_name,
            timeout=60,
        )

    # OpenRouter — routes any provider via OpenRouter's OpenAI-compatible
    # API. ID format: `openrouter/<owner>/<model>`, e.g.
    # `openrouter/anthropic/claude-3.5-sonnet`. Uses ChatOpenAI under the
    # hood with a custom base_url + OPENROUTER_API_KEY.
    if lid.startswith("openrouter/"):
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise MaicConfigError(
                "OPENROUTER_API_KEY is required to call OpenRouter models"
            )
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise MaicConfigError("langchain-openai not installed") from exc

        # Strip the `openrouter/` prefix; OpenRouter's slug format is
        # `<owner>/<model>` (e.g. `anthropic/claude-3.5-sonnet`).
        model_name = language_model_id.removeprefix("openrouter/")
        return ChatOpenAI(
            model=model_name,
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            timeout=60,
        )

    raise MaicConfigError(
        f"unknown language_model_id={language_model_id!r}; "
        f"expected 'stub', 'claude-…', 'gpt-…' / 'openai/…', "
        f"or 'openrouter/<owner>/<model>'"
    )


# ── Streaming text generation ─────────────────────────────────────────


async def stream_text(
    messages: list[BaseMessage],
    language_model_id: str,
    *,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> AsyncIterator[str]:
    """Stream the LLM's response as text chunks.

    Each yielded value is a slice of the model's text output (NOT a
    parsed event — the agent_generate node hands these to
    parse_structured_chunk to extract text/action items in original
    interleaved order).

    Stub path (`language_model_id == "stub"`):
        Yields STUB_OUTPUT in fixed-size slices so tests exercise the
        same chunk-by-chunk semantics a live stream would. No network.
        Deterministic.

    Real-model path:
        Resolves the chat model, calls .astream(messages), yields each
        chunk's `.content` as a string. Wraps non-trivial errors in
        MaicProviderError so the consumer can surface them as `error`
        frames cleanly.
    """
    if language_model_id == "stub":
        async for chunk in _stub_stream():
            yield chunk
        return

    if language_model_id == "stub-director":
        # Director-stub: returns a JSON decision consumable by
        # parse_director_decision. Cycles deterministically.
        yield _next_director_stub_output()
        return

    try:
        chat_model = resolve_chat_model(language_model_id)
        # Apply runtime params via .bind so we don't re-instantiate.
        bound = chat_model.bind(temperature=temperature)
        if max_tokens is not None:
            bound = bound.bind(max_tokens=max_tokens)
    except MaicConfigError:
        raise
    except Exception as exc:  # noqa: BLE001 — re-raised wrapped
        raise MaicProviderError(
            f"failed to build chat model {language_model_id!r}: {exc}"
        ) from exc

    try:
        async for chunk in bound.astream(messages):
            content = getattr(chunk, "content", None)
            # langchain ChatModel chunks may have str OR list-of-content-blocks
            # for multimodal models. We only care about plain text here.
            if isinstance(content, str):
                if content:
                    yield content
            elif isinstance(content, list):
                # Stream only the text-block parts; ignore tool_use blocks
                # (we don't use langchain tool_calls — actions come from
                # the structured JSON in the text stream itself).
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        if text:
                            yield text
    except Exception as exc:  # noqa: BLE001
        raise MaicProviderError(
            f"LLM stream failed ({language_model_id!r}): {exc}"
        ) from exc


# ── Sync-collect helper (Phase 4 / MAIC-433) ──────────────────────────


async def generate_text(
    messages: list[BaseMessage],
    language_model_id: str,
    *,
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> str:
    """Drain `stream_text(...)` and return the joined string.

    Phase 4's generation pipeline (`apps.maic.generation.*`) parses
    LLM output via `json_repair.parse_json_response`, which expects a
    complete string — not a stream. Rather than fork a second HTTP
    client (the chatbot/outline_service `requests.post` pattern),
    generation reuses `stream_text` and joins the yielded chunks here.

    Defaulting `temperature=0.0` (lower than `stream_text`'s 0.7
    default) — generation calls are deterministic by design so the
    parity test (ADR-005) gets stable golden outputs.

    Args:
        messages: langchain BaseMessage list (system + user typically).
        language_model_id: the same id `stream_text` accepts —
            'stub', 'stub-director', 'claude-...', 'gpt-...',
            'openai/...', or 'openrouter/<owner>/<model>'.
        temperature: 0.0 by default (was 0.7 in stream_text). Override
            for non-deterministic generation paths if any.
        max_tokens: passed through to `stream_text` for provider
            backends that support it.

    Returns:
        The concatenated text the LLM produced. Empty string if the
        stream yielded nothing.

    Raises:
        MaicConfigError / MaicProviderError — same exception classes
        `stream_text` raises. Generation callers wrap these into
        `GenerationResult{success: False, error: ...}` envelopes.

    Example:
        >>> from langchain_core.messages import SystemMessage, HumanMessage
        >>> text = await generate_text(
        ...     [SystemMessage(content="..."), HumanMessage(content="...")],
        ...     "openrouter/anthropic/claude-3.5-sonnet",
        ... )
    """
    chunks: list[str] = []
    async for chunk in stream_text(
        messages,
        language_model_id,
        temperature=temperature,
        max_tokens=max_tokens,
    ):
        chunks.append(chunk)
    return "".join(chunks)


# ── Stub implementation ───────────────────────────────────────────────


async def _stub_stream() -> AsyncIterator[str]:
    """Yield STUB_OUTPUT in fixed-size slices with tiny await between
    chunks so the surrounding async machinery (StreamWriter, Channels
    consumer) gets exercised under realistic ordering."""
    for i in range(0, len(STUB_OUTPUT), _STUB_CHUNK_SIZE):
        slice_ = STUB_OUTPUT[i : i + _STUB_CHUNK_SIZE]
        # Microscopic await — yields the event loop without measurable
        # latency. Production streams from the network insert latency
        # naturally between chunks; tests run effectively instantly.
        await asyncio.sleep(0)
        yield slice_
