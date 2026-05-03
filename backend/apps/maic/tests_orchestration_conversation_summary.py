"""Tests for apps.maic.orchestration.summarizers.conversation_summary.

Direct port of upstream's `summarizeConversation`. Same shape, same
defaults, same truncation rules. The director-graph delegates to this
module (MAIC-109) so any drift here ripples through the multi-agent
prompt assembly — keep these tests strict.
"""
from __future__ import annotations

import pytest

from apps.maic.orchestration.summarizers import summarize_conversation


# ── empty + edge cases ─────────────────────────────────────────────────


def test_empty_messages_returns_no_history_sentinel():
    """Mirrors upstream: empty list returns the literal string
    'No conversation history yet.' so prompt templates can detect
    no-history without introducing a separate sentinel."""
    assert summarize_conversation([]) == "No conversation history yet."


def test_messages_with_only_missing_content_returns_no_history():
    """Defensive: messages dicts with no `content` field are filtered
    out. If filtering empties the list, return the no-history sentinel
    rather than the empty string — same contract as the empty-input
    case so upstream can branch on a single check."""
    msgs = [{"role": "user"}, {"role": "assistant"}]
    assert summarize_conversation(msgs) == "No conversation history yet."


# ── happy path ─────────────────────────────────────────────────────────


def test_renders_role_labels_in_brackets():
    msgs = [
        {"role": "user", "content": "What are fractions?"},
        {"role": "assistant", "content": "A fraction is..."},
    ]
    out = summarize_conversation(msgs)
    assert "[User] What are fractions?" in out
    assert "[Assistant] A fraction is..." in out


def test_unknown_role_falls_through_to_system_label():
    """Defensive: any role not in the {user, assistant, system} set
    renders as 'System' rather than crashing or emitting raw role
    strings into the prompt."""
    msgs = [{"role": "tool_call", "content": "x"}]
    assert "[System] x" in summarize_conversation(msgs)


def test_renders_with_newline_between_messages():
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    out = summarize_conversation(msgs)
    assert out == "[User] hi\n[Assistant] hello"


# ── truncation ─────────────────────────────────────────────────────────


def test_truncates_long_content_with_ellipsis():
    long_text = "x" * 500
    out = summarize_conversation([{"role": "user", "content": long_text}])
    # 200 char cap + "..." suffix
    assert out.endswith("...")
    payload = out.removeprefix("[User] ").removesuffix("...")
    assert len(payload) == 200


def test_max_content_length_is_configurable():
    long_text = "y" * 50
    out = summarize_conversation(
        [{"role": "user", "content": long_text}],
        max_content_length=10,
    )
    payload = out.removeprefix("[User] ")
    assert payload == "y" * 10 + "..."


def test_short_content_is_not_truncated():
    msgs = [{"role": "user", "content": "short"}]
    out = summarize_conversation(msgs)
    assert out == "[User] short"
    assert "..." not in out


# ── windowing ──────────────────────────────────────────────────────────


def test_keeps_only_the_last_max_messages():
    msgs = [{"role": "user", "content": f"msg-{i}"} for i in range(20)]
    out = summarize_conversation(msgs, max_messages=3)
    assert "msg-17" in out
    assert "msg-18" in out
    assert "msg-19" in out
    # Older messages dropped
    assert "msg-0" not in out
    assert "msg-15" not in out


def test_zero_max_messages_returns_no_history_sentinel():
    """Edge: a caller passing max_messages=0 wants no messages — the
    function returns the no-history sentinel rather than an empty
    string so prompt templates render cleanly."""
    msgs = [{"role": "user", "content": "x"}]
    assert summarize_conversation(msgs, max_messages=0) == (
        "No conversation history yet."
    )


def test_default_max_messages_is_ten():
    """Locks the upstream default. If we ever change this, every caller
    needs to be notified — director, peer-context, etc. all assume the
    same window length unless they pass an override."""
    msgs = [{"role": "user", "content": f"m{i}"} for i in range(15)]
    out = summarize_conversation(msgs)  # uses default
    # Should include the last 10 (m5 through m14)
    assert "m5" in out
    assert "m14" in out
    assert "m4" not in out


# ── director-graph delegation (regression net) ────────────────────────


def test_director_graph_helper_delegates_to_summarizer():
    """`_build_conversation_summary` in director_graph.py was changed
    in MAIC-109 to delegate here. Lock that delegation: a non-empty
    conversation must produce summarizer-shaped output."""
    from apps.maic.orchestration.director_graph import _build_conversation_summary

    state = {
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ],
    }
    out = _build_conversation_summary(state)
    assert "[User] hi" in out
    assert "[Assistant] hello" in out


def test_director_graph_helper_returns_empty_for_no_history():
    """Director template expects empty string for 'no history' (so the
    block doesn't render at all) — distinct from the summarizer's
    'No conversation history yet.' sentence."""
    from apps.maic.orchestration.director_graph import _build_conversation_summary

    assert _build_conversation_summary({"messages": []}) == ""
    assert _build_conversation_summary({}) == ""
