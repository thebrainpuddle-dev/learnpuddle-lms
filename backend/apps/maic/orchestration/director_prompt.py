"""Director prompt builder + decision parser.

Source: THU-MAIC/OpenMAIC main lib/orchestration/director-prompt.ts
        (commit 10b1fc83) lines 23-89 (build_director_prompt) +
        216-239 (parse_director_decision) + 91-160
        (summarize_agent_whiteboard_actions) + 162-208
        (summarize_whiteboard_for_director, build_whiteboard_state).

The director template lives at apps/maic/prompts/templates/director/
system.md (already verified byte-identical to upstream's). We populate
its `{{agentList}}`, `{{respondedList}}`, `{{conversationSummary}}`,
`{{discussionSection}}`, `{{whiteboardSection}}`, `{{studentProfileSection}}`,
`{{rule1}}`, `{{turnCountPlusOne}}`, `{{whiteboardOpenText}}` slots.

Decision parsing: the LLM returns JSON like `{"next_agent": "default-3"}`
or `{"next_agent": "END"}`. We tolerate prose around the JSON via a
regex extract; on any parse failure the caller's round-robin fallback
kicks in (see director_graph._director_llm_decide in MAIC-104.1).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from apps.maic.exceptions import MaicConfigError
from apps.maic.prompts.loader import build_prompt

if TYPE_CHECKING:
    from apps.maic.orchestration.registry import AgentConfig
    from apps.maic.orchestration.state import (
        AgentTurnSummary,
        WhiteboardActionRecord,
    )


logger = logging.getLogger(__name__)


# ── Public API ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class DirectorDecision:
    """Parsed output of the director LLM call.

    `next_agent_id` is the agent the director picked, or None if the
    director chose to end this round (e.g. cue user back).

    `should_end` mirrors upstream's `shouldEnd` flag — true iff the
    director wants the loop to terminate after this decision.
    """
    next_agent_id: str | None
    should_end: bool


def build_director_prompt(
    agents: list[AgentConfig],
    conversation_summary: str,
    agent_responses: list[AgentTurnSummary],
    turn_count: int,
    *,
    discussion_context: dict | None = None,
    trigger_agent_id: str | None = None,
    whiteboard_ledger: list[WhiteboardActionRecord] | None = None,
    user_profile: dict | None = None,
    whiteboard_open: bool = False,
) -> str:
    """Build the director system prompt.

    Args:
        agents: Available agents the director may pick from
        conversation_summary: Compressed history (from MAIC-109
            summarizer when ready; for now the caller can pass an
            empty string or a hand-built rolling window)
        agent_responses: Reducer-accumulated AgentTurnSummary records
            from prior turns this round
        turn_count: 0-indexed turn count; we render `turn_count + 1`
            to the LLM (1-indexed reads better)
        discussion_context: Optional {topic, prompt?} when in
            discussion mode (mirrors upstream)
        trigger_agent_id: Agent id that initiated a discussion (used
            only when discussion_context is set)
        whiteboard_ledger: Reducer-accumulated whiteboard actions —
            populates the "what's on the board" section
        user_profile: Optional {nickname?, bio?} for the student
        whiteboard_open: True when the whiteboard surface is currently
            open (slide canvas hidden)

    Returns:
        The fully-rendered system prompt string.
    """
    agent_list = "\n".join(
        f'- id: "{a.id}", name: "{a.name}", role: {a.role}, priority: {a.priority}'
        for a in agents
    )

    if agent_responses:
        responded_list = "\n".join(
            _format_agent_response(r) for r in agent_responses
        )
    else:
        responded_list = "None yet."

    is_discussion = discussion_context is not None

    if is_discussion:
        topic = discussion_context.get("topic", "")
        prompt_part = (
            f'\nPrompt: "{discussion_context["prompt"]}"'
            if discussion_context.get("prompt")
            else ""
        )
        initiator_part = (
            f'\nInitiator: "{trigger_agent_id}"' if trigger_agent_id else ""
        )
        discussion_section = (
            f'\n# Discussion Mode\n'
            f'Topic: "{topic}"{prompt_part}{initiator_part}\n'
            f"This is a student-initiated discussion, not a Q&A session.\n"
        )
    else:
        discussion_section = ""

    if is_discussion:
        rule1_initiator = (
            f' ("{trigger_agent_id}")' if trigger_agent_id else ""
        )
        rule1 = (
            f"1. The discussion initiator{rule1_initiator} should speak "
            "first to kick off the topic. Then the teacher responds to "
            "guide the discussion. After that, other students may add "
            "their perspectives."
        )
    else:
        rule1 = (
            "1. The teacher (role: teacher, highest priority) should "
            "usually speak first to address the user's question or "
            "topic."
        )

    if user_profile and (user_profile.get("nickname") or user_profile.get("bio")):
        nickname = user_profile.get("nickname") or "Unknown"
        bio = user_profile.get("bio")
        bio_line = f"Background: {bio}" if bio else ""
        student_profile_section = (
            f"\n# Student Profile\n"
            f"Student name: {nickname}\n"
            f"{bio_line}\n"
        )
    else:
        student_profile_section = ""

    whiteboard_section = build_whiteboard_state_for_director(whiteboard_ledger)

    whiteboard_open_text = (
        "OPEN (slide canvas is hidden — spotlight/laser will not work)"
        if whiteboard_open
        else "CLOSED (slide canvas is visible)"
    )

    variables = {
        "agentList": agent_list,
        "respondedList": responded_list,
        "conversationSummary": conversation_summary,
        "discussionSection": discussion_section,
        "whiteboardSection": whiteboard_section,
        "studentProfileSection": student_profile_section,
        "rule1": rule1,
        "turnCountPlusOne": turn_count + 1,
        "whiteboardOpenText": whiteboard_open_text,
    }

    built = build_prompt("director", variables)
    if built is None:
        raise MaicConfigError("director prompt template failed to load")
    return built.system


def parse_director_decision(content: str) -> DirectorDecision:
    """Parse the director's JSON response.

    The LLM may wrap the JSON in prose ("Based on the conversation, my
    decision is: { ... }"). We extract the first object containing a
    `next_agent` key. On any failure, return a safe end-this-round
    decision so the loop terminates cleanly rather than panicking.

    Args:
        content: Raw LLM response text

    Returns:
        DirectorDecision with next_agent_id (None means END) and
        should_end (True when next_agent absent, == "END", or parse
        fails).
    """
    if not content:
        return DirectorDecision(next_agent_id=None, should_end=True)

    try:
        match = re.search(r'\{[^{}]*"next_agent"[^{}]*\}', content, re.DOTALL)
        if not match:
            logger.warning(
                "director: no JSON with next_agent found in: %s",
                content[:200],
            )
            return DirectorDecision(next_agent_id=None, should_end=True)

        parsed = json.loads(match.group(0))
        next_agent = parsed.get("next_agent")

        if not next_agent or next_agent == "END":
            return DirectorDecision(next_agent_id=None, should_end=True)

        if not isinstance(next_agent, str):
            logger.warning(
                "director: next_agent is %s, expected string; ending round",
                type(next_agent).__name__,
            )
            return DirectorDecision(next_agent_id=None, should_end=True)

        return DirectorDecision(next_agent_id=next_agent, should_end=False)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "director: failed to parse decision (%s): %s",
            type(exc).__name__,
            content[:200],
        )
        return DirectorDecision(next_agent_id=None, should_end=True)


# ── Whiteboard ledger summary ──────────────────────────────────────


def summarize_whiteboard_for_director(
    ledger: list[WhiteboardActionRecord],
) -> dict:
    """Replay the whiteboard ledger to compute current element count
    and contributors.

    Mirrors upstream `summarizeWhiteboardForDirector`. wb_clear resets
    the count but NOT the contributor set (people who participated
    still participated).

    Returns:
        dict with `element_count: int` and `contributors: list[str]`.
    """
    element_count = 0
    contributors: set[str] = set()

    for record in ledger:
        action_name = record.get("actionName", "")
        if action_name == "wb_clear":
            element_count = 0
        elif action_name == "wb_delete":
            element_count = max(0, element_count - 1)
        elif action_name.startswith("wb_draw_"):
            element_count += 1
            agent_name = record.get("agentName")
            if agent_name:
                contributors.add(agent_name)

    return {
        "element_count": element_count,
        "contributors": sorted(contributors),
    }


def build_whiteboard_state_for_director(
    ledger: list[WhiteboardActionRecord] | None,
) -> str:
    """Build the whiteboard state section for the director prompt.

    Returns empty string if there are no whiteboard actions. Otherwise
    a "# Whiteboard State" block with element count + contributors,
    plus a crowded-warning when >5 elements are on the board.
    """
    if not ledger:
        return ""

    summary = summarize_whiteboard_for_director(ledger)
    element_count = summary["element_count"]
    contributors = summary["contributors"]

    crowded_warning = ""
    if element_count > 5:
        crowded_warning = (
            "\n⚠ The whiteboard is getting crowded. Consider routing to "
            "an agent that will organize or clear it rather than adding "
            "more."
        )

    contributors_text = (
        ", ".join(contributors) if contributors else "none"
    )

    return (
        f"\n# Whiteboard State\n"
        f"Elements on whiteboard: {element_count}\n"
        f"Contributors: {contributors_text}{crowded_warning}\n"
    )


# ── Internals ──────────────────────────────────────────────────────


def _format_agent_response(record: AgentTurnSummary) -> str:
    """Render one AgentTurnSummary into the responded-list block.

    Format mirrors upstream:
        - {agentName} ({agentId}): "{contentPreview}" [{actionCount} actions{whiteboardSummary}]
    """
    wb_summary = _summarize_agent_whiteboard_actions(
        record.get("whiteboardActions", []),
    )
    wb_part = f" | Whiteboard: {wb_summary}" if wb_summary else ""
    return (
        f'- {record.get("agentName", "?")} '
        f'({record.get("agentId", "?")}): '
        f'"{record.get("contentPreview", "")}" '
        f'[{record.get("actionCount", 0)} actions{wb_part}]'
    )


def _summarize_agent_whiteboard_actions(
    actions: list[dict],
) -> str:
    """Compact one agent's whiteboard actions into a one-line summary.

    Mirrors upstream `summarizeAgentWhiteboardActions` (lib/orchestration
    /director-prompt.ts:91-160).
    """
    if not actions:
        return ""

    parts: list[str] = []
    for a in actions:
        action_name = a.get("actionName", "")
        params = a.get("params") or {}

        if action_name == "wb_draw_text":
            content = str(params.get("content") or "")[:30]
            ellipsis = "..." if len(content) >= 30 else ""
            parts.append(f'drew text "{content}{ellipsis}"')
        elif action_name == "wb_draw_shape":
            shape = params.get("shape") or params.get("type") or "rectangle"
            parts.append(f"drew shape({shape})")
        elif action_name == "wb_draw_chart":
            data = params.get("data")
            labels: list[str] | None = None
            if isinstance(data, dict):
                raw_labels = data.get("labels")
                if isinstance(raw_labels, list):
                    labels = [str(label) for label in raw_labels]
            elif isinstance(params.get("labels"), list):
                labels = [str(label) for label in params["labels"]]
            chart_type = params.get("chartType") or params.get("type") or "bar"
            label_part = (
                f", labels: [{','.join(labels[:4])}]" if labels else ""
            )
            parts.append(f"drew chart({chart_type}{label_part})")
        elif action_name == "wb_draw_latex":
            latex = str(params.get("latex") or "")[:30]
            ellipsis = "..." if len(latex) >= 30 else ""
            parts.append(f'drew formula "{latex}{ellipsis}"')
        elif action_name == "wb_draw_table":
            data = params.get("data")
            rows = len(data) if isinstance(data, list) else 0
            cols = (
                len(data[0])
                if rows and isinstance(data[0], list)
                else 0
            )
            parts.append(f"drew table({rows}×{cols})")
        elif action_name == "wb_draw_line":
            pts = params.get("points")
            has_arrow = isinstance(pts, list) and "arrow" in pts
            arrow_part = " arrow" if has_arrow else ""
            parts.append(f"drew{arrow_part} line")
        elif action_name == "wb_draw_code":
            lang = str(params.get("language") or "")
            file_name = params.get("fileName")
            file_part = f' "{file_name}"' if file_name else ""
            parts.append(f"drew code block{file_part} ({lang})")
        elif action_name == "wb_edit_code":
            op = params.get("operation") or "edit"
            parts.append(f"edited code ({op})")
        elif action_name == "wb_clear":
            parts.append("CLEARED whiteboard")
        elif action_name == "wb_delete":
            element_id = params.get("elementId", "")
            parts.append(f'deleted element "{element_id}"')
        # wb_open / wb_close intentionally omitted — structural, not
        # content (matches upstream lines 153-156)

    return ", ".join(parts)
