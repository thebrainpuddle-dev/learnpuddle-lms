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
    "claude-…"                          → ChatAnthropic
    "gpt-…", "openai/…"                 → ChatOpenAI
    "openrouter/…"                      → ChatOpenAI against OpenRouter
    "ollama/…"                          → direct Ollama HTTP stream
    everything else                     → MaicConfigError

Production callers pass a tenant runtime config resolved from
TenantAIConfig. Environment variables remain only as an operator fallback
for legacy/dev probes, never as the multi-tenant source of truth.

Why a stub mode at all:
    The Phase-1 acceptance contract requires the WS pipe + classroom
    smoke to be exercisable WITHOUT live API credentials in CI. The
    stub mode emits the same JSON-array structured output a real model
    would, so the parser + director loop run identically. Production
    paths NEVER pass model_id="stub"; HTTP/WS/Celery boundaries resolve the
    real school-specific model from TenantAIConfig.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
import json
import logging
import os
from typing import AsyncIterator, Final

from langchain_core.messages import BaseMessage

from apps.maic.exceptions import MaicConfigError, MaicProviderError

logger = logging.getLogger(__name__)

_LLM_RUNTIME_CONFIG: ContextVar[dict | None] = ContextVar(
    "maic_llm_runtime_config",
    default=None,
)


@contextmanager
def use_llm_runtime_config(llm_config: dict | None):
    """Set tenant LLM credentials for the current async context only."""
    token = _LLM_RUNTIME_CONFIG.set(llm_config)
    try:
        yield
    finally:
        _LLM_RUNTIME_CONFIG.reset(token)


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


def resolve_chat_model(language_model_id: str, *, llm_config: dict | None = None):
    """Build a langchain BaseChatModel for the given id.

    Stub model is handled separately by stream_text — this function is
    only called for real LLM paths.

    Raises:
        MaicConfigError: unknown id, missing API key, or import failure.
    """
    llm_config = _effective_llm_config(llm_config)

    if language_model_id == "stub":
        raise MaicConfigError(
            "resolve_chat_model is for real LLMs only; stub is handled in stream_text"
        )

    lid = language_model_id.lower()

    if _is_ollama_model_id(lid):
        raise MaicConfigError(
            "resolve_chat_model is for LangChain-backed models only; "
            "Ollama is handled directly in stream_text"
        )

    # Anthropic family
    if lid.startswith("claude-") or lid.startswith("anthropic/"):
        api_key = _runtime_api_key(llm_config) or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
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
            api_key=api_key,
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
        api_key = _runtime_api_key(llm_config) or os.environ.get("OPENAI_API_KEY")
        if not api_key:
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
        kwargs: dict[str, object] = {
            "model": model_name,
            "api_key": api_key,
            "timeout": 60,
        }
        base_url = _runtime_base_url(llm_config)
        if base_url:
            kwargs["base_url"] = base_url
        return ChatOpenAI(**kwargs)

    # OpenRouter — routes any provider via OpenRouter's OpenAI-compatible
    # API. ID format: `openrouter/<owner>/<model>`, e.g.
    # `openrouter/anthropic/claude-3.5-sonnet`. Uses ChatOpenAI under the
    # hood with a custom base_url + OPENROUTER_API_KEY.
    if lid.startswith("openrouter/"):
        api_key = _runtime_api_key(llm_config) or os.environ.get("OPENROUTER_API_KEY")
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
            base_url=_runtime_base_url(llm_config) or "https://openrouter.ai/api/v1",
            api_key=api_key,
            timeout=60,
        )

    raise MaicConfigError(
        f"unknown language_model_id={language_model_id!r}; "
        f"expected 'stub', 'claude-…', 'gpt-…' / 'openai/…', "
        f"'openrouter/<owner>/<model>', or 'ollama/<model>'"
    )


# ── Streaming text generation ─────────────────────────────────────────


async def stream_text(
    messages: list[BaseMessage],
    language_model_id: str,
    *,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    llm_config: dict | None = None,
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
    llm_config = _effective_llm_config(llm_config)

    if language_model_id == "stub":
        async for chunk in _stub_stream():
            yield chunk
        return

    if language_model_id == "stub-director":
        # Director-stub: returns a JSON decision consumable by
        # parse_director_decision. Cycles deterministically.
        yield _next_director_stub_output()
        return

    if _is_ollama_model_id(language_model_id.lower()):
        async for chunk in _stream_ollama(
            messages,
            language_model_id,
            temperature=temperature,
            max_tokens=max_tokens,
            llm_config=llm_config,
        ):
            yield chunk
        return

    try:
        chat_model = resolve_chat_model(language_model_id, llm_config=llm_config)
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
    llm_config: dict | None = None,
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
        llm_config=llm_config,
    ):
        chunks.append(chunk)
    return "".join(chunks)


def _effective_llm_config(llm_config: dict | None) -> dict | None:
    return llm_config if llm_config is not None else _LLM_RUNTIME_CONFIG.get()


def _runtime_api_key(llm_config: dict | None) -> str:
    if not llm_config:
        return ""
    value = llm_config.get("api_key")
    return value if isinstance(value, str) else ""


def _runtime_base_url(llm_config: dict | None) -> str:
    if not llm_config:
        return ""
    value = llm_config.get("base_url")
    return value.rstrip("/") if isinstance(value, str) and value else ""


# ── Ollama implementation ─────────────────────────────────────────────


def _is_ollama_model_id(language_model_id: str) -> bool:
    return language_model_id.startswith("ollama/") or language_model_id.startswith("ollama:")


def _ollama_model_name(language_model_id: str) -> str:
    if language_model_id.startswith("ollama/"):
        model = language_model_id.removeprefix("ollama/")
    elif language_model_id.startswith("ollama:"):
        model = language_model_id.removeprefix("ollama:")
    else:
        model = ""
    if not model:
        raise MaicConfigError(
            "Ollama model id must be 'ollama/<model>', e.g. 'ollama/qwen2.5:7b'"
        )
    return model


def _message_content_to_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text") or block.get("content")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content or "")


def _to_ollama_messages(messages: list[BaseMessage]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for message in messages:
        msg_type = getattr(message, "type", "")
        if msg_type == "system":
            role = "system"
        elif msg_type == "ai":
            role = "assistant"
        else:
            role = "user"
        text = _message_content_to_text(getattr(message, "content", ""))
        if text:
            out.append({"role": role, "content": text})
    return out or [{"role": "user", "content": ""}]


async def _stream_ollama(
    messages: list[BaseMessage],
    language_model_id: str,
    *,
    temperature: float,
    max_tokens: int | None,
    llm_config: dict | None = None,
) -> AsyncIterator[str]:
    """Stream from a real local Ollama server.

    OpenMAIC supports local Ollama; this direct HTTP path gives MAIC v2 a
    production-real local cert route without external API keys.
    """
    model = _ollama_model_name(language_model_id)
    base_url = (
        _runtime_base_url(llm_config)
        or os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ).rstrip("/")
    timeout_seconds = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "180"))
    options: dict[str, object] = {"temperature": temperature}
    if max_tokens is not None:
        options["num_predict"] = max_tokens
    payload: dict[str, object] = {
        "model": model,
        "messages": _to_ollama_messages(messages),
        "stream": True,
        "options": options,
    }

    try:
        import aiohttp  # type: ignore[import-untyped]
    except ImportError as exc:
        raise MaicConfigError("aiohttp required for Ollama adapter") from exc

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{base_url}/api/chat", json=payload) as resp:
                if resp.status < 200 or resp.status >= 300:
                    body = await resp.text()
                    raise MaicProviderError(
                        f"ollama: HTTP {resp.status} from {base_url}/api/chat: "
                        f"{body[:300]}"
                    )

                async for raw_line in resp.content:
                    line = (
                        raw_line.decode("utf-8")
                        if isinstance(raw_line, (bytes, bytearray))
                        else str(raw_line)
                    ).strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise MaicProviderError(
                            f"ollama: malformed streaming JSON: {line[:200]}"
                        ) from exc

                    message = data.get("message") or {}
                    content = message.get("content") if isinstance(message, dict) else ""
                    if isinstance(content, str) and content:
                        yield content
                    if data.get("done"):
                        return
    except MaicProviderError:
        raise
    except TimeoutError as exc:
        raise MaicProviderError(
            f"ollama: request timed out after {timeout_seconds:.0f}s "
            f"for model {model!r} at {base_url}"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise MaicProviderError(
            f"ollama: request failed for model {model!r}: {exc}"
        ) from exc


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
