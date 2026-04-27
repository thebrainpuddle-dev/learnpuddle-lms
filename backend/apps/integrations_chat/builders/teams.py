"""
Microsoft Teams Adaptive Card message builders.

Each builder is a pure function: takes notification_type and a payload dict,
returns a Teams incoming-webhook JSON-serializable dict using the
``@type: MessageCard`` (Office connector) format which is universally
supported by Teams incoming-webhook connectors without OAuth.

Reference: https://docs.microsoft.com/en-us/outlook/actionable-messages/message-card-reference
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Theme colours (hex) per notification type
# ---------------------------------------------------------------------------

_COLOUR_MAP: dict[str, str] = {
    "COURSE_ASSIGNED": "1F4788",
    "ASSIGNMENT_DUE": "F5A623",
    "QUIZ_SUBMISSION": "7ED321",
    "CERTIFICATION_EXPIRING": "D0021B",
    "REPORT_GENERATED": "4A90E2",
    "REMINDER": "9B9B9B",
    "ANNOUNCEMENT": "417505",
    "SYSTEM": "9B9B9B",
}


def build_teams_message(notification_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Build a Microsoft Teams MessageCard body for the given *notification_type*.

    :param notification_type: One of the ChatRoutingRule.NOTIFICATION_TYPE_CHOICES keys.
    :param payload: Arbitrary context dict (title, message, url, recipient_name, etc.).
    :returns: A dict suitable for ``json=`` in a Teams incoming-webhook POST.
    """
    colour = _COLOUR_MAP.get(notification_type, "9B9B9B")

    title = payload.get("title", notification_type.replace("_", " ").title())
    message = payload.get("message", "")
    recipient = payload.get("recipient_name", "")
    school = payload.get("school_name", "LearnPuddle")
    lms_url = payload.get("url", "")

    facts: list[dict[str, str]] = [{"name": "School", "value": school}]
    if recipient:
        facts.append({"name": "Recipient", "value": recipient})
    facts.append({"name": "Type", "value": notification_type.replace("_", " ").title()})

    sections: list[dict[str, Any]] = [
        {
            "activityTitle": title,
            "activityText": message or "",
            "facts": facts,
            "markdown": True,
        }
    ]

    card: dict[str, Any] = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "themeColor": colour,
        "summary": f"[{school}] {title}",
        "title": title,
        "sections": sections,
    }

    if lms_url:
        card["potentialAction"] = [
            {
                "@type": "OpenUri",
                "name": "Open in LearnPuddle",
                "targets": [{"os": "default", "uri": lms_url}],
            }
        ]

    return card
