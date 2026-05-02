"""Streaming structured-output parser for LLM agent_generate output.

Direct port of upstream `lib/orchestration/stateless-generate.ts` lines
1-306. Same wire format, same emission semantics.

Source:
    https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/orchestration/stateless-generate.ts

Why we need this
================

The agent's LLM is told to emit a single JSON array of mixed `text` and
`action` items, e.g.

    [
      {"type":"action","name":"spotlight","params":{"elementId":"img_1"}},
      {"type":"text","content":"Hello students. Look at this..."},
      {"type":"action","name":"speech","params":{"text":"Hello students. Look at this."}},
      {"type":"text","content":" Now consider..."},
      ...
    ]

The LLM streams this array token-by-token. We need to:

  1. Skip any prefix before `[` (markdown fences, explanations).
  2. Incrementally parse the growing buffer with `json-repair` (handles
     malformed/truncated JSON gracefully — Python's `json` module will
     not parse `[{"type":"text","content":"hi`).
  3. Emit fully-completed items exactly once.
  4. For the trailing partial text item, emit each new content slice
     so the UI can render text deltas in real time.
  5. Mark done when the closing `]` arrives.

Compared to upstream
====================

  - Uses `json-repair` only (Python lacks a partial-json equivalent;
    json-repair tolerates truncated arrays well enough in practice).
  - Returns `ParseResult` as a dataclass (fully typed, immutable per-call).
  - `ParserState` is a dataclass with the same five fields as upstream.
  - Action ID generation: upstream emits a Date.now()-based id when the
    LLM doesn't provide one; we use uuid4 (collision-free over a session
    lifetime, opaque to clients).

Used by
=======

  - apps/maic/orchestration/director_graph.py (Phase 1 MAIC-105 will
    replace its agent_generate stub with a real LLM stream that pipes
    through this parser).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Final, Literal, TypedDict

from json_repair import repair_json

logger = logging.getLogger(__name__)


# ── Types ──────────────────────────────────────────────────────────────


class ParsedAction(TypedDict):
    """Parsed action shape — pre-validation. The director graph runs
    this through `apps.maic.protocol.validate_action` before emitting
    on the wire so any malformed action is dropped at the orchestrator
    boundary, not the playback engine."""

    actionId: str
    actionName: str
    params: dict[str, Any]


@dataclass
class ParserState:
    """Mutable parser state — one instance per agent generation call.

    Fields mirror upstream `ParserState` interface (lib/orchestration/
    stateless-generate.ts:42-53):
      buffer:                 accumulated raw LLM output
      jsonStarted:            True once `[` has been seen
      lastParsedItemCount:    number of items already emitted
      lastPartialTextLength:  chars of the trailing partial text item
                              already emitted (so we can stream deltas)
      isDone:                 True once `]` is seen
    """

    buffer: str = ""
    jsonStarted: bool = False
    lastParsedItemCount: int = 0
    lastPartialTextLength: int = 0
    isDone: bool = False


OrderedEntry = dict  # actually {"type": "text"|"action", "index": int}


@dataclass
class ParseResult:
    """Result of one chunk parse. textChunks/actions are appended; the
    `ordered` list records original-interleaving order so callers can
    re-emit text and action events in the same sequence the LLM produced."""

    textChunks: list[str] = field(default_factory=list)
    actions: list[ParsedAction] = field(default_factory=list)
    isDone: bool = False
    ordered: list[OrderedEntry] = field(default_factory=list)


_REPAIR_FAILED: Final = object()  # sentinel for json-repair giving up


# ── Public API ─────────────────────────────────────────────────────────


def create_parser_state() -> ParserState:
    """Allocate a fresh parser state. One per agent_generate invocation."""
    return ParserState()


def parse_structured_chunk(chunk: str, state: ParserState) -> ParseResult:
    """Process a streaming chunk of LLM output. Mutates state.

    Returns a ParseResult containing only what was newly emitted by THIS
    chunk (not cumulative). Callers iterate `result.ordered` to replay
    items in original order.
    """
    result = ParseResult()

    if state.isDone:
        return result

    state.buffer += chunk

    # Step 1 — find the opening `[`, trim everything before it
    if not state.jsonStarted:
        idx = state.buffer.find("[")
        if idx == -1:
            return result
        state.buffer = state.buffer[idx:]
        state.jsonStarted = True

    # Step 2 — closing `]` detection
    trimmed = state.buffer.rstrip()
    is_array_closed = trimmed.endswith("]") and len(trimmed) > 1

    # Step 3 — incremental parse via json-repair
    parsed = _repair_and_load(state.buffer)
    if parsed is _REPAIR_FAILED or not isinstance(parsed, list):
        return result

    # Step 4 — count items considered fully complete
    complete_up_to = len(parsed) if is_array_closed else max(0, len(parsed) - 1)

    # Step 5 — emit newly-completed items (skipping items already emitted)
    for i in range(state.lastParsedItemCount, complete_up_to):
        item = parsed[i]
        if not isinstance(item, dict):
            continue

        item_type = item.get("type")

        # Special case: the previously-streamed trailing partial text
        # has now been completed. Emit ONLY the remaining tail, not the
        # full content again.
        if (
            i == state.lastParsedItemCount
            and state.lastPartialTextLength > 0
            and item_type == "text"
        ):
            content = str(item.get("content") or "")
            remaining = content[state.lastPartialTextLength :]
            if remaining:
                result.textChunks.append(remaining)
                result.ordered.append(
                    {"type": "text", "index": len(result.textChunks) - 1}
                )
            state.lastPartialTextLength = 0
            continue

        _emit_item(item, result)

    state.lastParsedItemCount = complete_up_to

    # Step 6 — stream partial text delta for the trailing item
    if not is_array_closed and len(parsed) > complete_up_to:
        last = parsed[-1]
        if isinstance(last, dict) and last.get("type") == "text":
            content = str(last.get("content") or "")
            if len(content) > state.lastPartialTextLength:
                delta = content[state.lastPartialTextLength :]
                result.textChunks.append(delta)
                result.ordered.append(
                    {"type": "text", "index": len(result.textChunks) - 1}
                )
                state.lastPartialTextLength = len(content)

    # Step 7 — mark done if closed
    if is_array_closed:
        state.isDone = True
        result.isDone = True
        state.lastParsedItemCount = len(parsed)
        state.lastPartialTextLength = 0

    return result


def finalize_parser(state: ParserState) -> ParseResult:
    """Called once after the stream ends.

    Handles two ragged cases the LLM may leave us in:
      a) Model never output `[` — treat the whole buffer as plain text
         (so the user sees something rather than a blank classroom).
      b) Model output `[` but never closed it — try one last parse, and
         if that yields nothing, emit raw post-`[` text as a fallback.
    """
    result = ParseResult(isDone=True)

    if state.isDone:
        return result

    content = state.buffer.strip()
    if not content:
        return result

    if not state.jsonStarted:
        # Plain-text fallback
        result.textChunks.append(content)
        result.ordered.append({"type": "text", "index": 0})
        state.isDone = True
        return result

    # JSON started but never closed — one last parse attempt
    final_chunk = parse_structured_chunk("", state)
    result.textChunks.extend(final_chunk.textChunks)
    result.actions.extend(final_chunk.actions)
    result.ordered.extend(final_chunk.ordered)

    if not result.textChunks and not result.actions:
        bracket_idx = content.find("[")
        raw = content[bracket_idx + 1 :].strip() if bracket_idx >= 0 else content
        if raw:
            result.textChunks.append(raw)
            result.ordered.append({"type": "text", "index": 0})

    state.isDone = True
    return result


# ── Internals ──────────────────────────────────────────────────────────


def _emit_item(item: dict, result: ParseResult) -> None:
    """Append one parsed item to result.ordered + textChunks/actions."""
    item_type = item.get("type")

    if item_type == "text":
        content = str(item.get("content") or "")
        if content:
            result.textChunks.append(content)
            result.ordered.append({"type": "text", "index": len(result.textChunks) - 1})
        return

    if item_type == "action":
        # Support both new format (name/params) and legacy
        # tool_name/parameters format from the upstream backwards-compat
        # branch (lib/orchestration/stateless-generate.ts:101-107).
        action_name = item.get("name") or item.get("tool_name")
        if not action_name:
            logger.warning("dropping action item without name/tool_name: %r", item)
            return
        params = item.get("params") or item.get("parameters") or {}
        if not isinstance(params, dict):
            logger.warning("dropping action with non-dict params: %r", item)
            return
        result.actions.append({
            "actionId": str(item.get("action_id") or f"action-{uuid.uuid4()}"),
            "actionName": str(action_name),
            "params": params,
        })
        result.ordered.append({"type": "action", "index": len(result.actions) - 1})
        return

    # Unknown item type — drop silently. Same behavior as upstream.


def _repair_and_load(buffer: str) -> Any:
    """Try to parse `buffer` (possibly truncated) via json-repair.

    Returns the parsed value (typically a list) or `_REPAIR_FAILED` if
    repair couldn't produce valid JSON. Empty/whitespace input → empty
    list (safe default — the parse loop bails when it's not a list anyway).
    """
    if not buffer.strip():
        return []
    try:
        # repair_json returns a Python object when return_objects=True
        repaired = repair_json(buffer, return_objects=True)
        return repaired
    except Exception:  # noqa: BLE001 — defensive; repair_json shouldn't raise
        logger.debug("json-repair failed on partial buffer", exc_info=True)
        return _REPAIR_FAILED
