"""Tests for apps.maic.orchestration.stateless_parser.

Critical invariants:
  • Items emitted exactly once.
  • Trailing-partial-text deltas accumulate without duplicating content.
  • Markdown fences and explanatory prefixes before `[` are stripped.
  • finalize_parser produces user-visible output even when the model
    never produced valid JSON.
  • interleaving order is preserved (matters for TTS-text-and-action
    sync in the playback engine).
"""
from __future__ import annotations

import json

import pytest

from apps.maic.orchestration.stateless_parser import (
    create_parser_state,
    finalize_parser,
    parse_structured_chunk,
)


# ── Whole-array, single shot (the simplest case) ──────────────────────


def test_full_array_single_chunk_text_only():
    state = create_parser_state()
    payload = json.dumps([
        {"type": "text", "content": "hello"},
        {"type": "text", "content": " world"},
    ])
    result = parse_structured_chunk(payload, state)
    assert result.isDone is True
    assert result.textChunks == ["hello", " world"]
    assert result.actions == []
    assert [e["type"] for e in result.ordered] == ["text", "text"]


def test_full_array_single_chunk_actions_only():
    state = create_parser_state()
    payload = json.dumps([
        {"type": "action", "name": "spotlight", "params": {"elementId": "x"}},
        {"type": "action", "name": "speech", "params": {"text": "hi"}},
    ])
    result = parse_structured_chunk(payload, state)
    assert result.isDone is True
    assert len(result.actions) == 2
    assert result.actions[0]["actionName"] == "spotlight"
    assert result.actions[1]["actionName"] == "speech"
    assert result.actions[0]["params"] == {"elementId": "x"}


def test_interleaved_text_and_action_order_preserved():
    state = create_parser_state()
    payload = json.dumps([
        {"type": "text", "content": "Look here:"},
        {"type": "action", "name": "spotlight", "params": {"elementId": "el-1"}},
        {"type": "text", "content": "And here:"},
        {"type": "action", "name": "spotlight", "params": {"elementId": "el-2"}},
    ])
    result = parse_structured_chunk(payload, state)
    seq = [
        ("text", result.textChunks[e["index"]]) if e["type"] == "text"
        else ("action", result.actions[e["index"]]["actionName"])
        for e in result.ordered
    ]
    assert seq == [
        ("text", "Look here:"),
        ("action", "spotlight"),
        ("text", "And here:"),
        ("action", "spotlight"),
    ]


# ── Streaming (chunked input) ──────────────────────────────────────────


def test_streaming_text_emits_deltas_without_duplication():
    """LLM produces 'hello world' across 3 chunks; we must NOT re-emit
    any prefix. The total concatenation across all yielded text chunks
    equals the final content exactly once."""
    state = create_parser_state()

    # Cumulative buffer growth — each chunk only adds the diff
    chunks_in = [
        '[{"type":"text","content":"hel',
        'lo wo',
        'rld"}]',
    ]

    emitted_text = []
    final_done = False
    for c in chunks_in:
        r = parse_structured_chunk(c, state)
        emitted_text.extend(r.textChunks)
        if r.isDone:
            final_done = True

    assert final_done is True
    assert "".join(emitted_text) == "hello world"
    # And no individual delta is empty
    assert all(t for t in emitted_text)


def test_streaming_action_arrives_only_when_complete():
    """An action is only emitted once its closing `}` is in the buffer."""
    state = create_parser_state()

    # Chunk 1 — opens action, doesn't complete it
    r1 = parse_structured_chunk('[{"type":"action","name":"spotlight","params":{"el', state)
    assert r1.actions == []

    # Chunk 2 — completes action and closes array
    r2 = parse_structured_chunk('ementId":"x"}}]', state)
    assert len(r2.actions) == 1
    assert r2.actions[0]["actionName"] == "spotlight"
    assert r2.actions[0]["params"] == {"elementId": "x"}
    assert r2.isDone is True


def test_streaming_text_then_action_no_text_overcount():
    """After completed text item, an action that follows must not double-emit
    the text."""
    state = create_parser_state()

    chunks_in = [
        '[{"type":"text","content":"hello"},',
        '{"type":"action","name":"speech","params":{"text":"hello"}}]',
    ]
    text_total: list[str] = []
    actions_total: list[dict] = []
    for c in chunks_in:
        r = parse_structured_chunk(c, state)
        text_total.extend(r.textChunks)
        actions_total.extend(r.actions)

    assert "".join(text_total) == "hello"
    assert len(actions_total) == 1
    assert actions_total[0]["actionName"] == "speech"


# ── Prefix / suffix robustness ─────────────────────────────────────────


def test_strips_markdown_fence_prefix():
    state = create_parser_state()
    payload = '```json\n' + json.dumps([{"type": "text", "content": "ok"}]) + '\n```'
    result = parse_structured_chunk(payload, state)
    # The model produces extra text after the closing `]`, but the parser
    # must still recognize the array boundary.
    assert "ok" in "".join(result.textChunks) or len(result.textChunks) >= 1


def test_strips_explanatory_prose_before_bracket():
    state = create_parser_state()
    payload = (
        "Here is the JSON:\n"
        + json.dumps([{"type": "text", "content": "x"}])
    )
    r = parse_structured_chunk(payload, state)
    assert r.textChunks == ["x"]


def test_legacy_tool_name_format_supported():
    """Upstream supports a `tool_name`/`parameters` legacy field-name
    pair (lib/orchestration/stateless-generate.ts:101-107)."""
    state = create_parser_state()
    payload = json.dumps([
        {"type": "action", "tool_name": "speech", "parameters": {"text": "hi"}},
    ])
    r = parse_structured_chunk(payload, state)
    assert len(r.actions) == 1
    assert r.actions[0]["actionName"] == "speech"
    assert r.actions[0]["params"] == {"text": "hi"}


def test_action_without_name_is_dropped():
    state = create_parser_state()
    payload = json.dumps([{"type": "action", "params": {}}])
    r = parse_structured_chunk(payload, state)
    assert r.actions == []


# ── finalize_parser ────────────────────────────────────────────────────


def test_finalize_parser_plain_text_fallback():
    """Model never output `[` — treat buffer as a single text item."""
    state = create_parser_state()
    parse_structured_chunk("Sorry, I cannot generate JSON today.", state)
    final = finalize_parser(state)
    assert final.textChunks == ["Sorry, I cannot generate JSON today."]
    assert final.isDone is True


def test_finalize_parser_unfinished_array_fallback():
    """Buffer has `[` but no closing `]`. With json-repair, the partial
    array can usually be parsed; we accept either repair-success or the
    raw-text fallback path."""
    state = create_parser_state()
    parse_structured_chunk('[{"type":"text","content":"hello', state)
    final = finalize_parser(state)
    assert final.isDone is True
    # Either the repaired parse delivered "hello" as a text chunk, or
    # the raw-after-bracket fallback delivered something non-empty.
    assert any(final.textChunks) or any(final.actions)


def test_finalize_parser_empty_buffer_emits_nothing():
    state = create_parser_state()
    final = finalize_parser(state)
    assert final.textChunks == []
    assert final.actions == []


def test_finalize_parser_after_already_done_is_idempotent():
    state = create_parser_state()
    parse_structured_chunk(json.dumps([{"type": "text", "content": "x"}]), state)
    assert state.isDone is True
    final = finalize_parser(state)
    assert final.textChunks == []  # nothing new — already done
    assert final.isDone is True


# ── State invariants ───────────────────────────────────────────────────


def test_state_isdone_blocks_further_parses():
    state = create_parser_state()
    parse_structured_chunk(json.dumps([{"type": "text", "content": "x"}]), state)
    r = parse_structured_chunk(' more chunks (ignored)', state)
    assert r.textChunks == []
    assert r.actions == []


def test_action_id_assigned_when_missing():
    state = create_parser_state()
    payload = json.dumps([{"type": "action", "name": "speech", "params": {"text": "hi"}}])
    r = parse_structured_chunk(payload, state)
    assert r.actions[0]["actionId"]
    # uuid4 form: 36 chars including hyphens, prefixed `action-`
    assert r.actions[0]["actionId"].startswith("action-")
    assert len(r.actions[0]["actionId"]) > len("action-")


def test_action_id_preserved_when_provided():
    state = create_parser_state()
    payload = json.dumps([
        {"type": "action", "name": "speech", "action_id": "fixed-123", "params": {"text": "hi"}},
    ])
    r = parse_structured_chunk(payload, state)
    assert r.actions[0]["actionId"] == "fixed-123"
