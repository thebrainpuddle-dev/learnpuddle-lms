"""Prompt builder — assemble the agent system prompt for one turn.

Direct port of upstream lib/orchestration/prompt-builder.ts (221 lines).
Same role guidelines, same format examples, same mutual-exclusion note,
same role-aware length + whiteboard guideline branching.

Source:
    https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/orchestration/prompt-builder.ts
    Upstream commit 10b1fc83cf77c769e8acac7b6c0569122b764bfd

Phase 1 scope:
    - Real port of role guidelines, format constants, length/whiteboard
      guidelines, and the agent-system template builder.
    - peer_context_section: real port (33-line module, no transitive
      deps beyond AgentTurnSummary which we already have).
    - state_context, virtual_whiteboard_context, student_profile,
      language_constraint, discussion_context: implemented as minimal
      Phase-1 stubs that return empty string for the typical
      single-agent-first-turn case. Phase 3 (multi-agent / discussion)
      and Phase 4 (slide-aware state) fill these in with full upstream
      ports — the function signatures are stable.

Why these are stubs in Phase 1 vs MAIC-005's stub director:
    - The Phase-0 director was a stub of the orchestration LOOP itself.
    - The Phase-1 prompt builder is the FULL builder; only the
      multi-agent context summarizers are deferred. The single-agent
      first-turn prompt produced here is byte-identical to what
      upstream produces in the same scenario.
"""
from __future__ import annotations

import logging
from typing import Any

from apps.maic.exceptions import MaicConfigError
from apps.maic.orchestration.registry import AgentConfig
from apps.maic.orchestration.tool_schemas import (
    get_action_descriptions,
    get_effective_actions,
)
from apps.maic.prompts import build_prompt

logger = logging.getLogger(__name__)


# ── Role guidelines (verbatim port from prompt-builder.ts:19-51) ──────


ROLE_GUIDELINES: dict[str, str] = {
    "teacher": (
        "Your role in this classroom: LEAD TEACHER.\n"
        "You are responsible for:\n"
        "- Controlling the lesson flow, slides, and pacing\n"
        "- Explaining concepts clearly with examples and analogies\n"
        "- Asking questions to check understanding\n"
        "- Using spotlight/laser to direct attention to slide elements\n"
        "- Using the whiteboard for diagrams and formulas\n"
        "You can use all available actions. Never announce your actions — "
        "just teach naturally."
    ),
    "assistant": (
        "Your role in this classroom: TEACHING ASSISTANT.\n"
        "You are responsible for:\n"
        "- Supporting the lead teacher by filling gaps and answering side questions\n"
        "- Rephrasing explanations in simpler terms when students are confused\n"
        "- Providing concrete examples and background context\n"
        "- Using the whiteboard sparingly to supplement (not duplicate) the "
        "teacher's content\n"
        "You play a supporting role — don't take over the lesson."
    ),
    "student": (
        "Your role in this classroom: STUDENT.\n"
        "You are responsible for:\n"
        "- Participating actively in discussions\n"
        "- Asking questions, sharing observations, reacting to the lesson\n"
        "- Keeping responses SHORT (1-2 sentences max)\n"
        "- Only using the whiteboard when explicitly invited by the teacher\n"
        "You are NOT a teacher — your responses should be much shorter than "
        "the teacher's."
    ),
}


# ── Format examples + ordering (verbatim port from prompt-builder.ts:60-78) ──


FORMAT_EXAMPLE_SLIDE = (
    '[{"type":"action","name":"spotlight","params":{"elementId":"img_1"}},'
    '{"type":"text","content":"Your natural speech to students"}]'
)
FORMAT_EXAMPLE_WB = (
    '[{"type":"action","name":"wb_open","params":{}},'
    '{"type":"text","content":"Your natural speech to students"}]'
)

ORDERING_SLIDE = (
    "- spotlight/laser actions should appear BEFORE the corresponding text "
    "object (point first, then speak)\n"
    "- whiteboard actions can interleave WITH text objects (draw while speaking)"
)
ORDERING_WB = (
    "- whiteboard actions can interleave WITH text objects (draw while speaking)"
)

SPOTLIGHT_EXAMPLES = (
    '[{"type":"action","name":"spotlight","params":{"elementId":"img_1"}},'
    '{"type":"text","content":"Photosynthesis is the process by which plants '
    'convert light energy into chemical energy. Take a look at this diagram."},'
    '{"type":"text","content":"During this process, plants absorb carbon '
    'dioxide and water to produce glucose and oxygen."}]\n\n'
    '[{"type":"action","name":"spotlight","params":{"elementId":"eq_1"}},'
    '{"type":"action","name":"laser","params":{"elementId":"eq_2"}},'
    '{"type":"text","content":"Compare these two equations — notice how the '
    'left side is endothermic while the right side is exothermic."}]\n\n'
)

SLIDE_ACTION_GUIDELINES = (
    "- spotlight: Use to focus attention on ONE key element. Don't overuse — "
    "max 1-2 per response.\n"
    "- laser: Use to point at elements. Good for directing attention during "
    "explanations.\n"
)

MUTUAL_EXCLUSION_NOTE = (
    "- IMPORTANT — Whiteboard / Canvas mutual exclusion: The whiteboard and "
    "slide canvas are mutually exclusive. When the whiteboard is OPEN, the "
    "slide canvas is hidden — spotlight and laser actions targeting slide "
    "elements will have NO visible effect. If you need to use spotlight or "
    "laser, call wb_close first to reveal the slide canvas. Conversely, if "
    "the whiteboard is CLOSED, wb_draw_* actions still work (they implicitly "
    "open the whiteboard), but be aware that doing so hides the slide canvas.\n"
    "- Prefer variety: mix spotlights, laser, and whiteboard for engaging "
    "teaching. Don't use the same action type repeatedly."
)


# ── Length guidelines (verbatim port from prompt-builder.ts:175-198) ──


def _build_length_guidelines(role: str) -> str:
    common = (
        "- Length targets count ONLY your speech text (type:\"text\" content). "
        "Actions (spotlight, whiteboard, etc.) do NOT count toward length. "
        "Use as many actions as needed — they don't make your speech \"too "
        "long.\"\n"
        "- Speak conversationally and naturally — this is a live classroom, "
        "not a textbook. Use oral language, not written prose."
    )

    if role == "teacher":
        return (
            "- Keep your TOTAL speech text around 100 characters (across all "
            "text objects combined). Prefer 2-3 short sentences over one long "
            "paragraph.\n"
            f"{common}\n"
            "- Prioritize inspiring students to THINK over explaining "
            "everything yourself. Ask questions, pose challenges, give hints — "
            "don't just lecture.\n"
            "- When explaining, give the key insight in one crisp sentence, "
            "then pause or ask a question. Avoid exhaustive explanations."
        )

    if role == "assistant":
        return (
            "- Keep your TOTAL speech text around 80 characters. You are a "
            "supporting role — be brief.\n"
            f"{common}\n"
            "- One key point per response. Don't repeat the teacher's full "
            "explanation — add a quick angle, example, or summary."
        )

    # Student roles (and any unknown role defaults here)
    return (
        "- Keep your TOTAL speech text around 50 characters. 1-2 sentences max.\n"
        f"{common}\n"
        "- You are a STUDENT, not a teacher. Your responses should be much "
        "shorter than the teacher's. If your response is as long as the "
        "teacher's, you are doing it wrong.\n"
        "- Speak in quick, natural reactions: a question, a joke, a brief "
        "insight, a short observation. Not paragraphs.\n"
        "- Inspire and provoke thought with punchy comments, not lengthy analysis."
    )


# ── Whiteboard guidelines (loaded from agent-system-wb-{role}/system.md) ──


def _build_whiteboard_guidelines(role: str) -> str:
    """Load the role-specific whiteboard reference from the prompt
    template directory. Mirrors prompt-builder.ts:208-221."""
    template_id = (
        "agent-system-wb-teacher"
        if role == "teacher"
        else "agent-system-wb-assistant"
        if role == "assistant"
        else "agent-system-wb-student"
    )
    prompt = build_prompt(template_id, {})
    if prompt is None:
        raise MaicConfigError(f"{template_id} template not found")
    return prompt.system


# ── Peer context (verbatim port from summarizers/peer-context.ts) ─────


def build_peer_context_section(
    agent_responses: list[dict[str, Any]] | None,
    current_agent_name: str,
) -> str:
    """Summarize what other agents said this round. Empty when no peers
    have spoken (single-agent or first speaker in multi-agent)."""
    if not agent_responses:
        return ""

    peers = [
        r for r in agent_responses
        if r.get("agentName") != current_agent_name
    ]
    if not peers:
        return ""

    peer_lines = "\n".join(
        f"- {r.get('agentName')}: \"{r.get('contentPreview', '')}\"" for r in peers
    )
    return (
        "\n# This Round's Context (CRITICAL — READ BEFORE RESPONDING)\n"
        "The following agents have already spoken in this discussion round:\n"
        f"{peer_lines}\n\n"
        f"You are {current_agent_name}, responding AFTER the agents above. "
        "You MUST:\n"
        "1. NOT repeat greetings or introductions — they have already been made\n"
        "2. NOT restate what previous speakers already explained\n"
        f"3. Add NEW value from YOUR unique perspective as {current_agent_name}\n"
        "4. Build on, question, or extend what was said — do not echo it"
    )


# ── Phase-1 minimal summarizers (Phase 3/4 expand these) ──────────────


def _build_student_profile_section(
    user_profile: dict[str, Any] | None,
) -> str:
    """Direct port of prompt-builder.ts:79-84."""
    if not user_profile:
        return ""
    nickname = user_profile.get("nickname")
    bio = user_profile.get("bio")
    if not nickname and not bio:
        return ""
    name_part = nickname or "a student"
    bio_part = f"\nTheir background: {bio}" if bio else ""
    return (
        f"\n# Student Profile\n"
        f"You are teaching {name_part}.{bio_part}\n"
        f"Personalize your teaching based on their background when relevant. "
        f"Address them by name naturally.\n"
    )


def _build_language_constraint(language_directive: str | None) -> str:
    """Direct port of prompt-builder.ts:86-88."""
    if not language_directive:
        return ""
    return f"\n# Language (CRITICAL)\n{language_directive}\n"


def _build_discussion_context_section(
    discussion_context: dict[str, Any] | None,
    agent_responses: list[dict[str, Any]] | None,
) -> str:
    """Direct port of prompt-builder.ts:90-111."""
    if not discussion_context:
        return ""
    topic = discussion_context.get("topic", "")
    prompt = discussion_context.get("prompt")
    prompt_line = f"Guiding prompt: {prompt}" if prompt else ""

    if agent_responses:
        return (
            f"\n\n# Discussion Context\n"
            f'Topic: "{topic}"\n'
            f"{prompt_line}\n\n"
            "You are JOINING an ongoing discussion — do NOT re-introduce the "
            "topic or greet the students. The discussion has already started. "
            "Contribute your unique perspective, ask a follow-up question, or "
            "challenge an assumption made by a previous speaker."
        )
    return (
        f"\n\n# Discussion Context\n"
        f'You are initiating a discussion on the following topic: "{topic}"\n'
        f"{prompt_line}\n\n"
        "IMPORTANT: As you are starting this discussion, begin by introducing "
        "the topic naturally to the students. Engage them and invite their "
        "thoughts. Do not wait for user input - you speak first."
    )


def _build_state_context(store_state: dict[str, Any] | None) -> str:
    """Phase-1 stub — full port lands in Phase 4 (MAIC-422 scene_generator).

    Returns an empty string for the no-scene case (most Phase 1 traffic).
    When a scene IS loaded, returns a minimal one-liner so the LLM has
    SOME context — better than nothing but far from upstream's 172-line
    structured summary."""
    if not store_state:
        return ""
    scene_id = store_state.get("currentSceneId")
    if not scene_id:
        return ""
    scenes = store_state.get("scenes") or []
    scene = next((s for s in scenes if s.get("id") == scene_id), None)
    if not scene:
        return ""
    scene_type = scene.get("type", "unknown")
    return (
        f"\n# Current Scene\n"
        f"Scene id: {scene_id}\n"
        f"Scene type: {scene_type}\n"
        "(Full scene-element summary lands in Phase 4.)\n"
    )


def _build_virtual_whiteboard_context(
    store_state: dict[str, Any] | None,
    whiteboard_ledger: list[dict[str, Any]] | None,
) -> str:
    """Phase-1 stub — full port lands in Phase 3 (MAIC-415).

    Returns empty for an empty ledger (the typical Phase 1 case);
    otherwise emits a one-liner per ledger entry so the agent at least
    knows what's been drawn."""
    if not whiteboard_ledger:
        return ""
    open_now = bool((store_state or {}).get("whiteboardOpen"))
    open_str = "open" if open_now else "closed"
    lines = "\n".join(
        f"- {entry.get('agentName')} → {entry.get('actionName')}"
        for entry in whiteboard_ledger
    )
    return (
        f"\n# Whiteboard Ledger (currently {open_str})\n"
        f"{lines}\n"
    )


# ── Public API ────────────────────────────────────────────────────────


def build_structured_prompt(
    agent_config: AgentConfig,
    store_state: dict[str, Any] | None = None,
    *,
    discussion_context: dict[str, Any] | None = None,
    whiteboard_ledger: list[dict[str, Any]] | None = None,
    user_profile: dict[str, Any] | None = None,
    agent_responses: list[dict[str, Any]] | None = None,
) -> str:
    """Build the agent's system prompt for the current turn.

    Mirror of upstream buildStructuredPrompt at prompt-builder.ts:123-165.
    Returns the rendered system prompt string ready to ship to the LLM.

    Raises:
        MaicConfigError: agent-system or wb-{role} template missing.
    """
    # Determine current scene type for action filtering
    scene_type: str | None = None
    if store_state:
        current_id = store_state.get("currentSceneId")
        if current_id:
            scenes = store_state.get("scenes") or []
            scene = next((s for s in scenes if s.get("id") == current_id), None)
            if scene:
                scene_type = scene.get("type")

    effective_actions = get_effective_actions(agent_config.allowedActions, scene_type)
    has_slide = "spotlight" in effective_actions or "laser" in effective_actions

    # storeState may carry a top-level languageDirective via the upstream
    # `stage.languageDirective` field; we accept either nesting.
    lang_directive: str | None = None
    if store_state:
        stage = store_state.get("stage") or {}
        lang_directive = stage.get("languageDirective") or store_state.get("languageDirective")

    vars: dict[str, Any] = {
        "agentName": agent_config.name,
        "persona": agent_config.persona,
        "roleGuideline": ROLE_GUIDELINES.get(agent_config.role, ROLE_GUIDELINES["student"]),
        "studentProfileSection": _build_student_profile_section(user_profile),
        "peerContext": build_peer_context_section(agent_responses, agent_config.name),
        "languageConstraint": _build_language_constraint(lang_directive),
        "formatExample": FORMAT_EXAMPLE_SLIDE if has_slide else FORMAT_EXAMPLE_WB,
        "orderingPrinciples": ORDERING_SLIDE if has_slide else ORDERING_WB,
        "spotlightExamples": SPOTLIGHT_EXAMPLES if has_slide else "",
        "actionDescriptions": get_action_descriptions(effective_actions),
        "slideActionGuidelines": SLIDE_ACTION_GUIDELINES if has_slide else "",
        "mutualExclusionNote": MUTUAL_EXCLUSION_NOTE if has_slide else "",
        "stateContext": _build_state_context(store_state),
        "virtualWhiteboardContext": _build_virtual_whiteboard_context(
            store_state, whiteboard_ledger,
        ),
        "lengthGuidelines": _build_length_guidelines(agent_config.role),
        "whiteboardGuidelines": _build_whiteboard_guidelines(agent_config.role),
        "discussionContextSection": _build_discussion_context_section(
            discussion_context, agent_responses,
        ),
    }

    prompt = build_prompt("agent-system", vars)
    if prompt is None:
        raise MaicConfigError("agent-system template not found")
    return prompt.system
