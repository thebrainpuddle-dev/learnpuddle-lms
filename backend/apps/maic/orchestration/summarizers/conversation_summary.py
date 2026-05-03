"""Conversation summary — compress the last N messages for prompt injection.

Direct port of upstream `lib/orchestration/summarizers/conversation-summary.ts`.

Source:
    https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/orchestration/summarizers/conversation-summary.ts

The Phase 3 plan stub described this as "LLM-backed; cache key = hash of
message ids". That was a misread — upstream is **pure-function**: take the
last N messages, truncate long ones, render with role labels. No LLM call,
no cache. The pure-function shape is what every caller in upstream expects,
and it keeps the director's prompt assembly deterministic + cheap.

Used by:
    - `apps.maic.orchestration.director_graph._build_conversation_summary`
      delegates to this module so the director and any future caller use
      the same compression rule.
"""
from __future__ import annotations

from typing import Any


_DEFAULT_MAX_MESSAGES = 10
_DEFAULT_MAX_CONTENT_LENGTH = 200

_ROLE_LABELS = {
    "user": "User",
    "assistant": "Assistant",
    "system": "System",
}


def summarize_conversation(
    messages: list[dict[str, Any]],
    max_messages: int = _DEFAULT_MAX_MESSAGES,
    max_content_length: int = _DEFAULT_MAX_CONTENT_LENGTH,
) -> str:
    """Render the last N messages as `[Role] content...` lines.

    Mirrors upstream's `summarizeConversation`:
        - Empty input  → "No conversation history yet."
        - Slice to the last `max_messages` entries.
        - Truncate any single message's content to `max_content_length`
          and append "..." when truncated.
        - Render with `[User] / [Assistant] / [System]` labels.

    Args:
        messages: list of `{"role": str, "content": str}` dicts. A
            message missing `content` is skipped.
        max_messages: how many recent messages to include (default 10).
        max_content_length: per-message truncation cap (default 200).

    Returns:
        A newline-joined block ready to drop into a prompt template, or
        `"No conversation history yet."` for an empty input.
    """
    if not messages:
        return "No conversation history yet."

    recent = messages[-max_messages:] if max_messages > 0 else []
    lines: list[str] = []
    for msg in recent:
        content = msg.get("content")
        if content is None:
            continue
        role = msg.get("role", "")
        label = _ROLE_LABELS.get(role, "System")
        if len(content) > max_content_length:
            content = content[:max_content_length] + "..."
        lines.append(f"[{label}] {content}")

    if not lines:
        return "No conversation history yet."
    return "\n".join(lines)
