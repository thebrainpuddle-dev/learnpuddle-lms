"""
Slack Block Kit message builders.

Each builder is a pure function: takes notification_type and a payload dict,
returns a Slack Block Kit JSON-serializable dict.

Reference: https://api.slack.com/block-kit
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Colours (sidebar stripe for attachments — used as fallback for old clients)
# ---------------------------------------------------------------------------

_COLOUR_MAP: dict[str, str] = {
    "COURSE_ASSIGNED": "#1F4788",
    "ASSIGNMENT_DUE": "#F5A623",
    "QUIZ_SUBMISSION": "#7ED321",
    "CERTIFICATION_EXPIRING": "#D0021B",
    "REPORT_GENERATED": "#4A90E2",
    "REMINDER": "#9B9B9B",
    "ANNOUNCEMENT": "#417505",
    "SYSTEM": "#9B9B9B",
}

_EMOJI_MAP: dict[str, str] = {
    "COURSE_ASSIGNED": ":books:",
    "ASSIGNMENT_DUE": ":alarm_clock:",
    "QUIZ_SUBMISSION": ":pencil2:",
    "CERTIFICATION_EXPIRING": ":certificate:",
    "REPORT_GENERATED": ":bar_chart:",
    "REMINDER": ":bell:",
    "ANNOUNCEMENT": ":mega:",
    "SYSTEM": ":gear:",
}


def _header_block(text: str) -> dict[str, Any]:
    return {"type": "header", "text": {"type": "plain_text", "text": text, "emoji": True}}


def _section_block(text: str) -> dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _context_block(elements: list[str]) -> dict[str, Any]:
    return {
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": e} for e in elements],
    }


def _divider() -> dict[str, Any]:
    return {"type": "divider"}


def _button_action(text: str, url: str, action_id: str = "open_lms") -> dict[str, Any]:
    return {
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": text, "emoji": True},
                "url": url,
                "action_id": action_id,
            }
        ],
    }


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------


def build_slack_message(notification_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Build a Slack Block Kit message body for the given *notification_type*.

    :param notification_type: One of the ChatRoutingRule.NOTIFICATION_TYPE_CHOICES keys.
    :param payload: Arbitrary context dict (title, message, url, recipient_name, etc.).
    :returns: A dict suitable for ``json=`` in a Slack incoming-webhook POST.
    """
    emoji = _EMOJI_MAP.get(notification_type, ":bell:")
    colour = _COLOUR_MAP.get(notification_type, "#9B9B9B")

    title = payload.get("title", notification_type.replace("_", " ").title())
    message = payload.get("message", "")
    recipient = payload.get("recipient_name", "")
    school = payload.get("school_name", "LearnPuddle")
    lms_url = payload.get("url", "")

    blocks: list[dict[str, Any]] = [
        _header_block(f"{emoji} {title}"),
    ]

    if message:
        blocks.append(_section_block(message))

    blocks.append(_divider())

    context_parts = [f"*School:* {school}"]
    if recipient:
        context_parts.append(f"*For:* {recipient}")
    blocks.append(_context_block(context_parts))

    if lms_url:
        blocks.append(_button_action("Open in LearnPuddle", lms_url))

    body: dict[str, Any] = {
        "blocks": blocks,
        # Fallback text for notifications / accessibility.
        "text": f"[{school}] {title}" + (f": {message}" if message else ""),
        # Legacy attachment for colour-coded sidebar (Slack still renders this).
        "attachments": [{"color": colour, "fallback": title}],
    }
    return body
