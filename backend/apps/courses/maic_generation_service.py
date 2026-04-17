"""
Direct LLM generation for OpenMAIC AI Classrooms.

Used when the OpenMAIC sidecar is unavailable. Calls the tenant's configured
LLM provider (OpenRouter, OpenAI, etc.) directly from Django using the
encrypted API keys stored in TenantAIConfig.

Functions:
    generate_outline_sse()   → SSE text iterator for outline streaming
    generate_scene_content() → dict with multi-slide data (5-8 slides per scene)
    generate_scene_actions() → dict with rich action list (15-25 actions, 12 types)
    generate_tts_audio()     → bytes for per-agent TTS voices
    fallback_quiz_grade()    → LLM-based quiz grading when sidecar is down
"""

import io
import json
import logging
import uuid

import requests as http_requests
from json_repair import repair_json

from apps.courses.maic_models import TenantAIConfig
from apps.courses.maic_voices import (
    AZURE_IN_VOICES,
    VOICE_BY_ID,
    infer_gender_from_name,
    voice_matches_role,
    voices_for_gender,
)
from apps.courses.prompts.loader import load_prompt

logger = logging.getLogger(__name__)

# ─── Agent Voice Mapping ─────────────────────────────────────────────────────
#
# Deterministic fallback when the LLM-chosen voice is missing or invalid.
# Keys are the scene-action roles that agents commonly play; values are
# en-IN Azure Neural voice IDs. Only consulted when validate_agents can't
# accept the LLM output and we need a safe default.

AGENT_VOICE_MAP = {
    "professor": "en-IN-PrabhatNeural",
    "teaching_assistant": "en-IN-NeerjaNeural",
    "student_rep": "en-IN-AaravNeural",
    "student": "en-IN-AaravNeural",
    "moderator": "en-IN-KavyaNeural",
}


# ─── Agent Profile Validation ────────────────────────────────────────────────

# Canonical palettes referenced from prompts/agent_profiles.md — validator enforces
# membership so LLM drift on color/avatar doesn't leak into stored classrooms.
AGENT_COLOR_PALETTE: frozenset[str] = frozenset({
    "#4338CA",  # indigo
    "#0F766E",  # teal
    "#D97706",  # saffron
    "#166534",  # forest
    "#9F1239",  # cranberry
    "#334155",  # slate
})
AGENT_AVATAR_SET: frozenset[str] = frozenset({
    "👨‍🏫", "👩‍🏫", "🧑‍🎓", "👨‍🎓", "👩‍🎓", "🧕", "🙋‍♀️", "🙋‍♂️",
})


class AgentValidationError(ValueError):
    """Raised when a generated agent roster fails validation."""


def validate_agents(agents: list[dict], role_slots: list[dict]) -> None:
    """Raise AgentValidationError if the agent list doesn't satisfy constraints.

    role_slots: [{"role": "professor", "count": 1}, ...]
    """
    # Count by role must match role_slots
    role_counts: dict[str, int] = {}
    for a in agents:
        role_counts[a["role"]] = role_counts.get(a["role"], 0) + 1
    for slot in role_slots:
        actual = role_counts.get(slot["role"], 0)
        if actual != slot["count"]:
            raise AgentValidationError(
                f"role {slot['role']}: expected {slot['count']}, got {actual}"
            )

    # Voice constraints
    seen_voices: set[str] = set()
    for a in agents:
        voice_id = a.get("voiceId")
        if voice_id not in VOICE_BY_ID:
            raise AgentValidationError(f"voice {voice_id!r} not in roster")
        if voice_id in seen_voices:
            raise AgentValidationError(f"duplicate voice: {voice_id}")
        seen_voices.add(voice_id)
        if not voice_matches_role(voice_id, a["role"]):
            raise AgentValidationError(
                f"voice {voice_id} does not suit role {a['role']}"
            )
        # Name ↔ voice gender alignment. Only enforced when the first name
        # can be confidently classified — 'unknown' names skip the check
        # so novel names in the long tail don't thrash the regen loop.
        inferred_gender = infer_gender_from_name(a.get("name", ""))
        voice_gender = VOICE_BY_ID[voice_id]["gender"]
        if inferred_gender != "unknown" and inferred_gender != voice_gender:
            raise AgentValidationError(
                f"name {a.get('name')!r} reads as {inferred_gender}; "
                f"voice {voice_id} is {voice_gender}. "
                "Reassign a voice that matches the first-name gender."
            )

    # Gender balance when count ≥ 3
    if len(agents) >= 3:
        genders = {VOICE_BY_ID[a["voiceId"]]["gender"] for a in agents}
        if len(genders) < 2:
            raise AgentValidationError(
                "gender balance required: need at least one male and one female"
            )

    # Color: palette membership + no duplicates
    colors = [a["color"] for a in agents]
    for c in colors:
        if c not in AGENT_COLOR_PALETTE:
            raise AgentValidationError(
                f"color {c!r} not in palette (allowed: {sorted(AGENT_COLOR_PALETTE)})"
            )
    if len(set(colors)) != len(colors):
        raise AgentValidationError("duplicate color")

    # Avatar: emoji set membership + no duplicates
    avatars = [a["avatar"] for a in agents]
    for av in avatars:
        if av not in AGENT_AVATAR_SET:
            raise AgentValidationError(
                f"avatar {av!r} not in allowed emoji set"
            )
    if len(set(avatars)) != len(avatars):
        raise AgentValidationError("duplicate avatar")

# ─── LLM Call Helpers ─────────────────────────────────────────────────────────

def _build_llm_headers(config: TenantAIConfig) -> dict:
    """Build auth headers for the LLM provider."""
    api_key = config.get_llm_api_key()
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "learnpuddle.com",
        "X-Title": "LearnPuddle LMS",
    }


def _get_llm_url(config: TenantAIConfig) -> str:
    """Get the chat completions URL for the configured provider."""
    if config.llm_base_url:
        base = config.llm_base_url.rstrip("/")
        return f"{base}/chat/completions"
    provider_urls = {
        "openai": "https://api.openai.com/v1/chat/completions",
        "openrouter": "https://openrouter.ai/api/v1/chat/completions",
        "anthropic": "https://api.anthropic.com/v1/messages",
        "google": "https://generativelanguage.googleapis.com/v1beta/chat/completions",
    }
    return provider_urls.get(config.llm_provider, "https://openrouter.ai/api/v1/chat/completions")


def _call_llm(config: TenantAIConfig, system_prompt: str, user_prompt: str,
              temperature: float = 0.7, max_tokens: int = 4096) -> str | None:
    """Call the tenant's LLM provider and return text response."""
    url = _get_llm_url(config)
    headers = _build_llm_headers(config)

    payload = {
        "model": config.llm_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        resp = http_requests.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if choices:
            text = choices[0].get("message", {}).get("content", "").strip()
            if text:
                return text
        logger.warning("LLM returned empty response from %s", config.llm_model)
    except http_requests.HTTPError as e:
        logger.error("LLM HTTP error: %s — %s", e.response.status_code if e.response else "?",
                      e.response.text[:500] if e.response else str(e))
    except Exception as e:
        logger.error("LLM call failed: %s", e)
    return None


def _parse_json_from_llm(text: str) -> dict | list | None:
    """Extract and repair JSON from LLM output (handles markdown fences)."""
    if not text:
        return None
    # Strip markdown code fences
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first line (```json) and last line (```)
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)
    try:
        return json.loads(repair_json(cleaned))
    except Exception:
        logger.warning("Failed to parse LLM JSON output: %s...", cleaned[:200])
        return None


# ─── Agent Profile Generation ────────────────────────────────────────────────

def _auto_fix_voice_gender_mismatches(agents: list[dict]) -> tuple[list[dict], list[str]]:
    """Deterministically swap voiceIds to repair name↔voice gender mismatches.

    LLMs are inconsistent about matching voice gender to Indian first-name
    convention even with explicit instructions. Rather than fail the whole
    generation when a mismatch slips through, try to fix it locally.

    Uses a two-pass release-then-reassign strategy to handle the common
    "swap chain" case — e.g. agent-1 has Priya+male-voice and agent-2 has
    Arjun+female-voice. If we fix them one at a time, the first fix sees
    no free female voice (still held by agent-2) and bails out. So we
    first release all mismatched agents' voices into a free pool, then
    assign each mismatched agent a fresh gender-matched voice from that
    pool. Correctly-paired agents keep their voices untouched.

    Returns a new list (leaves the input untouched) plus a list of
    human-readable fix notes for logging. Only returns a valid roster
    when every mismatch is fixable; otherwise the caller re-prompts the
    LLM with the error context.
    """
    fixed: list[dict] = [dict(a) for a in agents]
    notes: list[str] = []

    # Pass 1: identify mismatched agents + release their voices.
    mismatched_indices: list[int] = []
    kept_voices: set[str] = set()
    for i, a in enumerate(fixed):
        voice_id = a.get("voiceId")
        voice = VOICE_BY_ID.get(voice_id) if voice_id else None
        if not voice:
            kept_voices.add(voice_id) if voice_id else None
            continue
        inferred = infer_gender_from_name(a.get("name", ""))
        if inferred == "unknown" or inferred == voice["gender"]:
            kept_voices.add(voice_id)
            continue
        mismatched_indices.append(i)

    # Pass 2: assign each mismatched agent a fresh matched voice.
    for i in mismatched_indices:
        a = fixed[i]
        old_voice = a.get("voiceId")
        inferred = infer_gender_from_name(a.get("name", ""))
        candidates = [
            v for v in voices_for_gender(inferred)
            if v["id"] not in kept_voices
            and a.get("role") in v.get("suits", [])
        ]
        if not candidates:
            notes.append(
                f"could not auto-fix {a.get('name')!r}: no unused "
                f"{inferred} voice available for role {a.get('role')!r}"
            )
            # Intentionally do NOT add the old (wrong) voice back to the
            # kept pool — it might have just been taken by a prior fix
            # in this same pass, which would leave the roster with
            # duplicate voiceIds. Downstream validation will see the
            # unchanged wrong voice and report the mismatch, triggering
            # an LLM re-prompt.
            continue

        # Prefer voices whose suits list contains ONLY the matching role
        # (e.g. Prabhat -> professor), then fall back to any candidate.
        exact = [v for v in candidates if v["suits"] == [a.get("role")]]
        picked = exact[0] if exact else candidates[0]

        a["voiceId"] = picked["id"]
        kept_voices.add(picked["id"])
        notes.append(
            f"auto-swapped {a.get('name')!r}: {old_voice} -> {picked['id']} "
            f"(matched {inferred} voice)"
        )

    return fixed, notes


def generate_agent_profiles_json(
    topic: str,
    language: str,
    role_slots: list[dict],
    config: TenantAIConfig,
) -> dict:
    """Generate an agent roster via LLM, validated against our constraints.

    Strategy:
      1. Call the LLM, parse JSON, run `validate_agents`.
      2. If validation fails with a voice/name gender mismatch AND the
         fix is a local voice swap, apply the deterministic auto-fix
         and re-validate. This prevents the whole flow from failing on
         an LLM hiccup that we can repair in-process.
      3. If auto-fix doesn't resolve it, re-prompt the LLM with the
         specific error message so the next attempt has context.

    Raises AgentValidationError on persistent failure after 3 attempts.
    """
    system_prompt = load_prompt("agent_profiles")

    # Build the rendered system prompt by filling in template variables baked
    # into the markdown: {{topic}}, {{language}}, {{role_slots_json}}, {{voices_json}}.
    rendered = system_prompt.replace("{{topic}}", topic)
    rendered = rendered.replace("{{language}}", language)
    rendered = rendered.replace("{{role_slots_json}}", json.dumps(role_slots, indent=2))
    rendered = rendered.replace("{{voices_json}}", json.dumps(AZURE_IN_VOICES, indent=2))

    base_user_prompt = f'Generate the agents for the topic "{topic}" in {language}.'

    last_error = None
    for attempt in range(3):
        # On retry, inject the prior error so the LLM has explicit
        # guidance instead of blindly repeating the same pick.
        user_prompt = base_user_prompt
        if last_error and attempt > 0:
            user_prompt = (
                f"{base_user_prompt}\n\n"
                f"Your previous attempt failed validation with this error: {last_error}\n"
                "Fix this specifically. Double-check voice gender against the "
                "first name of every agent BEFORE returning."
            )

        raw = _call_llm(config, rendered, user_prompt, temperature=0.9, max_tokens=2048)
        if not raw:
            last_error = "LLM returned empty"
            continue
        parsed = _parse_json_from_llm(raw)
        if not parsed or not isinstance(parsed, dict) or "agents" not in parsed:
            last_error = "invalid JSON"
            continue
        try:
            validate_agents(parsed["agents"], role_slots)
            return parsed
        except AgentValidationError as e:
            last_error = str(e)
            logger.warning("Agent profile validation failed (attempt %d): %s", attempt + 1, e)
            # Try to auto-correct voice gender mismatches locally before
            # burning another LLM call. Covers the most common LLM drift.
            fixed, notes = _auto_fix_voice_gender_mismatches(parsed["agents"])
            if notes:
                logger.info("Auto-fix notes: %s", "; ".join(notes))
            try:
                validate_agents(fixed, role_slots)
                parsed["agents"] = fixed
                logger.info("Agent roster auto-fixed after attempt %d", attempt + 1)
                return parsed
            except AgentValidationError as e2:
                logger.info("Auto-fix insufficient: %s", e2)
                last_error = str(e2)
                continue

    raise AgentValidationError(
        f"generation failed after 3 attempts: {last_error}"
    )


def regenerate_one_agent(
    topic: str,
    language: str,
    existing_agents: list[dict],
    target_agent_id: str,
    locked_fields: list[str],
    config: TenantAIConfig,
) -> dict:
    """Regenerate a single agent distinct from the existing set.

    locked_fields: list of field names to preserve from the existing agent (e.g., ['voiceId']).
    Returns the new agent dict wrapped in {"agent": ...}.
    """
    existing = next((a for a in existing_agents if a["id"] == target_agent_id), None)
    if not existing:
        raise ValueError(f"target_agent_id {target_agent_id} not in existing_agents")
    others = [a for a in existing_agents if a["id"] != target_agent_id]
    target_role = existing["role"]

    system_prompt = (
        "You are an expert instructional designer. Generate ONE replacement AI agent "
        f'for an Indian classroom teaching "{topic}" in {language}.\n'
        f"The new agent must fill this role slot: {target_role}.\n"
        f"The new agent must be distinct from these existing agents:\n"
        f"{json.dumps(others, indent=2)}\n"
        f"The new agent MUST preserve these locked fields from the existing agent: {locked_fields}.\n"
        f"Existing agent (for locked fields only): "
        f"{json.dumps({k: existing.get(k) for k in locked_fields})}\n"
        "Follow the same rules as full-roster generation:\n"
        "- Indian first name, region-appropriate surname, no stereotypes.\n"
        "- ENGLISH ONLY in every string field. No Hindi, no transliterated slang "
        "(theek hai / bilkul / achha / haan / samjhe / yaar). `speakingStyle` "
        "describes English register (warm / crisp / Socratic / informal).\n"
        "- Match voice gender to the first-name gender convention: "
        "Priya/Neha/Kavya/Aditi → female voice; Arjun/Rahul/Prabhat/Aarav → male voice.\n"
        "- `voiceId` must come from the en-IN Azure roster and suit the role.\n"
        'Return ONLY JSON: {"agent": {...}}'
    )
    user_prompt = f"Generate replacement agent for id={target_agent_id}."

    raw = _call_llm(config, system_prompt, user_prompt, temperature=0.9, max_tokens=1024)
    parsed = _parse_json_from_llm(raw or "")
    if not parsed or not isinstance(parsed, dict) or "agent" not in parsed:
        raise AgentValidationError("regenerate returned invalid JSON")

    new_agent = parsed["agent"]
    # Force-preserve locked fields
    for field in locked_fields:
        new_agent[field] = existing[field]
    new_agent["id"] = target_agent_id  # always preserve id

    # Validate against full roster: replace target in list, re-validate
    full = [new_agent if a["id"] == target_agent_id else a for a in existing_agents]
    role_slots_from_existing = _infer_role_slots(existing_agents)
    validate_agents(full, role_slots_from_existing)

    return {"agent": new_agent}


def _infer_role_slots(agents: list[dict]) -> list[dict]:
    """Build a role-slot list by counting roles in the provided agent roster."""
    counts: dict[str, int] = {}
    for a in agents:
        counts[a["role"]] = counts.get(a["role"], 0) + 1
    return [{"role": r, "count": c} for r, c in counts.items()]


# ─── SSE Formatting ──────────────────────────────────────────────────────────

def _sse_event(event_type: str, data: dict) -> str:
    """Format a single SSE event string."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


def _sse_done() -> str:
    return "data: [DONE]\n\n"


# ─── Outline Generation ──────────────────────────────────────────────────────

OUTLINE_SYSTEM_PROMPT = """You are an expert educational content designer creating a multi-agent interactive classroom.

You will receive a pre-configured agent roster. Do NOT invent new agents. Use the exact `id`s from the roster when assigning agents to scenes.

Return a valid JSON object:
{
  "scenes": [
    {
      "id": "scene-1",
      "title": "Scene title",
      "description": "Brief description of what this scene covers",
      "type": "introduction|lecture|discussion|quiz|activity|pbl|case_study|summary",
      "estimatedMinutes": 3,
      "agentIds": ["agent-1", "agent-2"],
      "slideCount": 6,
      "questionCount": 0
    }
  ],
  "totalMinutes": 20
}

Rules:
- The FIRST scene MUST be type "introduction" — all agents introduce themselves and preview the class
- The LAST scene MUST be type "summary" — wrap up key takeaways and next steps
- Automatically insert a "quiz" scene after every 2-3 lecture/discussion scenes to reinforce learning
- Each scene should have 2-5 minutes estimated time
- Every scene MUST have at least 2 agents assigned (for dialogue) drawn from the provided roster
- Scene type distribution: introduction -> lectures -> quiz -> lectures/discussion -> quiz -> summary
- For "lecture" scenes: set "slideCount" to 5-8 (number of slides to generate)
- For "discussion" scenes: set "slideCount" to 3-5
- For "introduction" scenes: set "slideCount" to 3-4
- For "summary" scenes: set "slideCount" to 3-4
- For "quiz" scenes: set "questionCount" to 3-5, "slideCount" to 1
- For "activity" scenes: set "slideCount" to 3-5
- For "pbl" scenes: set "slideCount" to 4-6
- For "case_study" scenes: set "slideCount" to 4-6
- Use agentIds ONLY from the provided roster — never invent new ids."""


def generate_outline_sse(topic: str, language: str, agents: list[dict],
                         scene_count: int, pdf_text: str | None,
                         config: TenantAIConfig):
    """
    Generator that yields SSE-formatted strings for outline streaming.
    Used as the body of a StreamingHttpResponse.

    ``agents`` is the authoritative roster produced by ``generate_agent_profiles_json``
    (or a teacher-edited variant). The outline prompt no longer invents agents;
    it assigns the supplied agent ids to scenes only.
    """
    agent_roster_for_prompt = [{
        "id": a["id"],
        "name": a["name"],
        "role": a["role"],
        "personality": a.get("personality", ""),
    } for a in agents]

    user_prompt = (
        "Create a classroom outline for the following:\n"
        f"\nTopic: {topic}"
        f"\nLanguage: {language}"
        f"\nNumber of scenes: {scene_count}"
        "\n\nAgent roster (use these ids when assigning agents to scenes):\n"
        f"{json.dumps(agent_roster_for_prompt, indent=2)}\n"
    )
    if pdf_text:
        excerpt = pdf_text[:15000]
        user_prompt += f"\nReference material (excerpt):\n{excerpt}\n"

    # Send a progress event first
    yield _sse_event("generation_progress", {"progress": 10})

    # Call LLM
    raw = _call_llm(config, OUTLINE_SYSTEM_PROMPT, user_prompt, temperature=0.7, max_tokens=4096)

    if not raw:
        yield _sse_event("error", {"message": "Failed to generate outline. Please try again."})
        yield _sse_done()
        return

    yield _sse_event("generation_progress", {"progress": 60})

    parsed = _parse_json_from_llm(raw)
    if not parsed or not isinstance(parsed, dict):
        yield _sse_event("error", {"message": "Invalid outline format from AI. Please try again."})
        yield _sse_done()
        return

    # Ensure required fields exist on scenes and that agent ids come from the supplied roster
    scenes = parsed.get("scenes", [])
    total_minutes = parsed.get("totalMinutes",
                                sum(s.get("estimatedMinutes", 3) for s in scenes))

    agent_ids_allowed = {a["id"] for a in agents}
    for i, scene in enumerate(scenes):
        if not scene.get("id"):
            scene["id"] = f"scene-{i + 1}"
        scene_agent_ids = [
            aid for aid in scene.get("agentIds", []) if aid in agent_ids_allowed
        ]
        if len(scene_agent_ids) < 2:
            # Fall back: pick first two ids from the supplied roster
            scene_agent_ids = [a["id"] for a in agents[:2]]
        scene["agentIds"] = scene_agent_ids

    outline_data = {
        "scenes": scenes,
        "agents": agents,               # pass-through from input
        "totalMinutes": total_minutes,
    }

    yield _sse_event("generation_progress", {"progress": 90})
    yield _sse_event("outline", outline_data)
    yield _sse_event("generation_progress", {"progress": 100})
    yield _sse_done()


# ─── Scene Content Generation ────────────────────────────────────────────────

SCENE_CONTENT_SYSTEM_PROMPT = """You are an expert educational content designer creating rich, visually appealing multi-slide presentations for an interactive AI classroom.

Given a scene from a classroom outline, generate an ARRAY of 5-8 slides with diverse layouts and content types.

Return a valid JSON object:
{
  "slides": [
    {
      "id": "slide-scene-1-1",
      "title": "Introduction to the Topic",
      "elements": [
        {
          "type": "text",
          "id": "el-s1-1",
          "x": 100, "y": 80, "width": 600, "height": 70,
          "content": "Main Title Text",
          "style": {"fontSize": 36, "fontWeight": "bold", "color": "#1E293B", "textAlign": "center"}
        },
        {
          "type": "text",
          "id": "el-s1-2",
          "x": 150, "y": 170, "width": 500, "height": 30,
          "content": "A compelling subtitle or tagline",
          "style": {"fontSize": 18, "color": "#64748B", "fontStyle": "italic", "textAlign": "center"}
        },
        {
          "type": "text",
          "id": "el-s1-3",
          "x": 100, "y": 250, "width": 600, "height": 120,
          "content": "Brief overview of what we will cover in this lesson...",
          "style": {"fontSize": 16, "color": "#475569", "lineHeight": 1.6}
        }
      ],
      "background": "#FFFFFF",
      "speakerScript": "Welcome everyone! Today we are going to explore a fascinating topic...",
      "duration": 40
    },
    {
      "id": "slide-scene-1-2",
      "title": "Key Concepts",
      "elements": [
        {
          "type": "text",
          "id": "el-s2-1",
          "x": 40, "y": 30, "width": 720, "height": 50,
          "content": "Key Concepts",
          "style": {"fontSize": 30, "fontWeight": "bold", "color": "#1E293B"}
        },
        {
          "type": "text",
          "id": "el-s2-2",
          "x": 40, "y": 90, "width": 400, "height": 280,
          "content": "\\u2022 First key point explained clearly\\n\\n\\u2022 Second key point with detail\\n\\n\\u2022 Third key point with example\\n\\n\\u2022 Fourth key point with application",
          "style": {"fontSize": 18, "color": "#334155", "lineHeight": 1.6}
        },
        {
          "type": "image",
          "id": "el-s2-img",
          "x": 460, "y": 90, "width": 300, "height": 240,
          "content": "Descriptive prompt for a relevant diagram or illustration",
          "src": ""
        },
        {
          "type": "text",
          "id": "el-s2-3",
          "x": 40, "y": 390, "width": 720, "height": 30,
          "content": "Key takeaway or memorable insight",
          "style": {"fontSize": 15, "color": "#0F766E", "fontWeight": "600"}
        }
      ],
      "background": "#FFFFFF",
      "speakerScript": "Let me walk you through the key concepts...",
      "duration": 50
    }
  ]
}

SLIDE LAYOUT GUIDELINES (follow this pattern for each slide position):
- Slide 1: TITLE slide — large centered heading (36px), subtitle, brief overview. Clean and impactful.
- Slide 2-3: CONTENT slides — heading + bullet points (left side) + image element (right side) + takeaway. Use split layout.
- Slide 4: DIAGRAM/VISUAL slide — image placeholder element (centered, large) + descriptive caption. Primarily visual.
- Slide 5-6: DEEP DIVE slides — detailed content with examples, code snippets, or step-by-step explanations. Can be text-heavy.
- Slide 7: KEY CONCEPTS slide — summary grid or comparison table layout. Use multiple smaller text blocks arranged in a grid.
- Slide 8: TRANSITION slide — summary of the scene + teaser for next scene. Clean, minimal text.

IMAGE ELEMENTS:
Include "type": "image" elements with "content" being a descriptive prompt for image generation (e.g., "Diagram showing the water cycle with evaporation, condensation, and precipitation labeled"), and "src" set to empty string "".

Rules:
- Coordinate space is 800x450 pixels per slide
- Generate the number of slides specified (default 5-8, minimum 3)
- Each slide element MUST have a globally unique ID (use format "el-s{slideNum}-{elementNum}")
- Each slide ID MUST be unique (use format "slide-{sceneId}-{slideNum}")
- Create 3-6 elements per slide (mix of text and image types)
- Include at least 2 image elements across all slides
- Use \\n\\n for paragraph breaks in bullet content (NOT just \\n)
- Heading: bold, 28-36px, dark color (#1E293B)
- Body: 16-20px, readable color (#334155)
- Takeaway/highlight: distinctive color (#0F766E), smaller font
- Speaker script MUST be 3-5 sentences per slide, written in first person as the presenting agent
- Speaker script should add context BEYOND what is on the slide (do not just read the bullets)
- For introduction scenes: the speaker script should introduce the agent and preview the lesson
- Duration should be 30-60 seconds per slide
- Vary the background colors subtly: #FFFFFF, #F8FAFC, #F1F5F9, #FFFBEB for visual interest

For quiz scenes, return:
{
  "questions": [
    {
      "id": "q1",
      "question": "Question text?",
      "options": [
        {"id": "o1", "text": "Option A", "isCorrect": false},
        {"id": "o2", "text": "Option B", "isCorrect": true},
        {"id": "o3", "text": "Option C", "isCorrect": false},
        {"id": "o4", "text": "Option D", "isCorrect": false}
      ],
      "explanation": "Why the correct answer is correct.",
      "type": "multiple_choice"
    }
  ]
}"""


def _fill_image_urls(parsed: dict, scene_id: str, *,
                     image_provider: str = "disabled") -> dict:
    """Post-process slides to fill in image URLs using image_service.

    When `image_provider == 'disabled'`, skip the fetch entirely and stamp
    `meta.imageProviderDisabled = true` on each image element so the
    frontend renders an honest "AI images off" placeholder rather than a
    random Unsplash photo. Any fetch error is logged (not silenced) so
    ops can see what providers are failing.
    """
    from apps.courses.image_service import fetch_scene_image

    disabled = (image_provider or "disabled").lower() == "disabled"
    slides = parsed.get("slides", [])
    for slide_idx, slide in enumerate(slides):
        for element in slide.get("elements", []):
            if element.get("type") != "image":
                continue
            if element.get("src"):
                continue
            if disabled:
                # Mark it explicitly so the renderer shows a labelled
                # placeholder instead of guessing at stock photos.
                meta = element.setdefault("meta", {})
                meta["imageProviderDisabled"] = True
                continue
            keyword = element.get("content", "educational illustration")
            try:
                url = fetch_scene_image(keyword)
                element["src"] = url
            except Exception as exc:  # noqa: BLE001 — log + fail open
                logger.warning(
                    "image fill failed scene=%s slide=%d keyword=%r err=%s",
                    scene_id, slide_idx, keyword, exc,
                )
                # src stays empty; frontend falls back to the generic
                # broken-image placeholder (not the Unsplash random).
    return parsed


def generate_scene_content(scene: dict, agents: list, language: str,
                           config: TenantAIConfig) -> dict | None:
    """Generate multi-slide content for a single scene. Returns parsed dict with 'slides' array."""
    scene_type = scene.get("type", "lecture")
    scene_id = scene.get("id", "scene-1")
    slide_count = max(3, min(12, scene.get("slideCount", 6)))
    question_count = max(2, min(8, scene.get("questionCount", 4)))

    if scene_type == "quiz":
        user_prompt = f"""Generate content for this classroom quiz scene:

Scene title: {scene["title"]}
Scene description: {scene.get("description", "")}
Scene type: quiz
Language: {language}
Assigned agents: {json.dumps([a["name"] for a in agents if a["id"] in scene.get("agentIds", [])])}

Generate {question_count} multiple choice questions that test understanding of the material covered so far.
"""
    else:
        user_prompt = f"""Generate a multi-slide presentation for this classroom scene:

Scene title: {scene["title"]}
Scene description: {scene.get("description", "")}
Scene type: {scene_type}
Scene ID: {scene_id}
Language: {language}
Number of slides to generate: {slide_count}
Assigned agents: {json.dumps([a["name"] for a in agents if a["id"] in scene.get("agentIds", [])])}

Generate exactly {slide_count} slides following the layout guidelines (title slide, content slides with images, diagram slide, deep dive, key concepts, transition). Include at least 2 image elements across the slides. Each slide must have a unique speakerScript.
"""

    raw = _call_llm(config, SCENE_CONTENT_SYSTEM_PROMPT, user_prompt,
                    temperature=0.6, max_tokens=8192)
    image_provider = getattr(config, "image_provider", "disabled") or "disabled"
    if not raw:
        return _fallback_scene_content(scene, image_provider=image_provider)

    parsed = _parse_json_from_llm(raw)
    if not parsed or not isinstance(parsed, dict):
        return _fallback_scene_content(scene, image_provider=image_provider)

    # Handle multi-slide response
    if "slides" in parsed and isinstance(parsed["slides"], list):
        for i, slide in enumerate(parsed["slides"]):
            if not slide.get("id"):
                slide["id"] = f"slide-{scene_id}-{i + 1}"
            if not slide.get("title"):
                slide["title"] = scene.get("title", "Untitled") if i == 0 else f"Slide {i + 1}"
            if not slide.get("elements"):
                slide["elements"] = []
            if not slide.get("background"):
                slide["background"] = "#FFFFFF"
            if not slide.get("duration"):
                slide["duration"] = 45
            # Ensure each element has an id
            for j, el in enumerate(slide["elements"]):
                if not el.get("id"):
                    el["id"] = f"el-s{i + 1}-{j + 1}"
        # Backward compatibility: include "slide" key pointing to first slide
        parsed["slide"] = parsed["slides"][0]
    elif "slide" in parsed:
        # Old format: single slide returned. Wrap in array for compatibility.
        slide = parsed["slide"]
        if not slide.get("id"):
            slide["id"] = f"slide-{scene_id}-1"
        if not slide.get("title"):
            slide["title"] = scene.get("title", "Untitled")
        if not slide.get("elements"):
            slide["elements"] = []
        for j, el in enumerate(slide["elements"]):
            if not el.get("id"):
                el["id"] = f"el-{j + 1}"
        parsed["slides"] = [slide]

    _fill_image_urls(parsed, scene_id, image_provider=image_provider)
    return parsed


def _fallback_scene_content(scene: dict, *, image_provider: str = "disabled") -> dict:
    """Deterministic fallback when LLM fails. Returns multi-slide format (3 slides min)."""
    scene_id = scene.get("id", "scene-1")
    title = scene.get("title", "Untitled")
    description = scene.get("description", "Content for this scene.")
    duration_per_slide = max(30, (scene.get("estimatedMinutes", 3) * 60) // 3)

    slide_1 = {
        "id": f"slide-{scene_id}-1",
        "title": title,
        "elements": [
            {
                "type": "text",
                "id": f"el-{scene_id}-s1-heading",
                "x": 100, "y": 80, "width": 600, "height": 70,
                "content": title,
                "style": {"fontSize": 36, "fontWeight": "bold", "color": "#1E293B", "textAlign": "center"},
            },
            {
                "type": "text",
                "id": f"el-{scene_id}-s1-subtitle",
                "x": 150, "y": 170, "width": 500, "height": 30,
                "content": description[:120],
                "style": {"fontSize": 18, "color": "#64748B", "fontStyle": "italic", "textAlign": "center"},
            },
        ],
        "background": "#FFFFFF",
        "speakerScript": f"Welcome! Let's explore {title}. {description}",
        "duration": duration_per_slide,
    }

    slide_2 = {
        "id": f"slide-{scene_id}-2",
        "title": f"Understanding {title}",
        "elements": [
            {
                "type": "text",
                "id": f"el-{scene_id}-s2-heading",
                "x": 40, "y": 30, "width": 720, "height": 50,
                "content": f"Understanding {title}",
                "style": {"fontSize": 30, "fontWeight": "bold", "color": "#1E293B"},
            },
            {
                "type": "text",
                "id": f"el-{scene_id}-s2-body",
                "x": 40, "y": 90, "width": 400, "height": 280,
                "content": description,
                "style": {"fontSize": 18, "color": "#4B5563", "lineHeight": 1.6},
            },
            {
                "type": "image",
                "id": f"el-{scene_id}-s2-img",
                "x": 460, "y": 90, "width": 300, "height": 240,
                "content": f"Educational diagram illustrating the concept of {title}",
                "src": "",
            },
        ],
        "background": "#F8FAFC",
        "speakerScript": f"Now let me explain the key aspects of {title}. This is fundamental to understanding the broader topic.",
        "duration": duration_per_slide,
    }

    slide_3 = {
        "id": f"slide-{scene_id}-3",
        "title": "Key Takeaways",
        "elements": [
            {
                "type": "text",
                "id": f"el-{scene_id}-s3-heading",
                "x": 40, "y": 30, "width": 720, "height": 50,
                "content": "Key Takeaways",
                "style": {"fontSize": 30, "fontWeight": "bold", "color": "#1E293B"},
            },
            {
                "type": "text",
                "id": f"el-{scene_id}-s3-body",
                "x": 40, "y": 100, "width": 720, "height": 250,
                "content": f"\u2022 Core concepts of {title}\n\n\u2022 Practical applications and relevance\n\n\u2022 How this connects to what comes next",
                "style": {"fontSize": 18, "color": "#334155", "lineHeight": 1.6},
            },
            {
                "type": "text",
                "id": f"el-{scene_id}-s3-takeaway",
                "x": 40, "y": 380, "width": 720, "height": 30,
                "content": f"Remember: {title} is a building block for everything that follows.",
                "style": {"fontSize": 15, "color": "#0F766E", "fontWeight": "600"},
            },
        ],
        "background": "#F1F5F9",
        "speakerScript": f"Let's wrap up what we have learned about {title}. Keep these key points in mind as we move forward.",
        "duration": duration_per_slide,
    }

    slides = [slide_1, slide_2, slide_3]
    result = {
        "slides": slides,
        "slide": slides[0],  # Backward compatibility
    }
    _fill_image_urls(result, scene_id, image_provider=image_provider)
    return result


# ─── Scene Actions Generation ────────────────────────────────────────────────

ACTIONS_SYSTEM_PROMPT = """You are an expert director choreographing a multi-agent interactive classroom. Your job is to create a dynamic, engaging sequence where MULTIPLE agents teach together across MULTIPLE SLIDES — like a real classroom with a professor and teaching assistants.

HARD LANGUAGE RULE (read before anything else):
- Output ONLY English. No Hindi words, no transliterated slang ("theek hai", "bilkul", "achha", "haan", "samjhe", "arre", "yaar", etc.), no code-switching, no mixed-script text.
- If a persona's `speakingStyle` hints at multilingualism, render the flavor through English register (warm, precise, crisp, Socratic, informal) — never by inserting non-English words.
- The audience is Indian learners who read and speak English in class. Anglo-Indian English is fine; Hinglish is NOT.

Given a scene's multi-slide content and agents, generate a rich sequence of playback actions that creates DIALOGUE between agents AND navigates between slides.

Return a valid JSON object:
{
  "actions": [
    {"type": "speech", "agentId": "agent-1", "text": "Welcome everyone! Today we are exploring..."},
    {"type": "spotlight", "elementId": "el-s1-1", "duration": 2500},
    {"type": "speech", "agentId": "agent-2", "text": "I am excited to dive into this topic with you all!"},
    {"type": "pause", "duration": 200},
    {"type": "transition", "slideIndex": 1},
    {"type": "speech", "agentId": "agent-1", "text": "Now let us look at the key concepts..."},
    {"type": "spotlight", "elementId": "el-s2-1", "duration": 2000},
    {"type": "highlight", "elementId": "el-s2-2", "color": "#DBEAFE"},
    {"type": "speech", "agentId": "agent-2", "text": "Students often find this part tricky. Think of it like..."},
    {"type": "wb_open"},
    {"type": "wb_draw_text", "text": "Key Formula: E = mc^2", "x": 200, "y": 100, "fontSize": 28, "color": "#1E293B"},
    {"type": "speech", "agentId": "agent-1", "text": "Let me write this out on the board so it is clearer..."},
    {"type": "wb_draw_shape", "shape": "arrow", "x": 200, "y": 160, "width": 200, "height": 40, "color": "#DC2626"},
    {"type": "wb_close"},
    {"type": "transition", "slideIndex": 2},
    {"type": "speech", "agentId": "agent-1", "text": "Notice how this diagram shows..."},
    {"type": "discussion", "sessionType": "qa", "topic": "Why is this important?", "agentIds": ["agent-1", "agent-2"], "triggerMode": "manual"},
    {"type": "transition", "slideIndex": 3},
    {"type": "speech", "agentId": "agent-2", "text": "Let me summarize what we have covered..."}
  ]
}

ACTION TYPES (12 types — use all of these for maximum engagement):

1. speech       — Agent speaks (requires: agentId, text). 1-3 sentences each.
2. spotlight    — Highlight element glow (requires: elementId, duration in ms)
3. highlight    — Color overlay on element (requires: elementId, color hex like "#DBEAFE")
4. pause        — Dramatic pause (requires: duration in ms, 500-1500)
5. transition   — Advance to next slide (requires: slideIndex — 0-based index of the target slide). CRITICAL for multi-slide scenes.
6. wb_open      — Open whiteboard overlay (no params)
7. wb_draw_text — Draw text on whiteboard (requires: text, x, y, fontSize, color)
8. wb_draw_shape— Draw shape on whiteboard (requires: shape ["circle"|"rect"|"arrow"], x, y, width, height, color)
9. wb_draw_line — Draw line on whiteboard (requires: x1, y1, x2, y2, color, strokeWidth)
10. wb_close    — Close whiteboard overlay (no params)
11. wb_clear    — Clear whiteboard content (no params)
12. discussion  — Start discussion segment (requires: sessionType ["qa"|"roundtable"], topic, agentIds)

CRITICAL RULES:
- VOICE DISCIPLINE: You MUST write speech text that reflects each agent's `speakingStyle` through ENGLISH register only — warm vs crisp, Socratic vs supportive, formal vs informal. Each agent's lines should be identifiable as that agent's voice without relying on non-English words.
  BAD (both agents sound identical, generic):
    - agent-1 (professor, style: "warm, unhurried, pauses to check understanding"): "Photosynthesis is the process by which plants convert sunlight into energy."
    - agent-2 (student, style: "curious, asks why, plays with analogies"):  "Yes, that's correct. The plant uses sunlight to make food."
  GOOD (each agent's register lands in the sentence, English only):
    - agent-1 (professor): "Think of the leaf like a tiny kitchen — sunlight is the stove, and the sugar made inside is the meal. Does that picture work for everyone?"
    - agent-2 (student):   "Wait — but what happens at night when the stove is off? Does the plant just go hungry?"
  Every agent's 3+ speech lines should read like THAT agent typed them, not a generic narrator. NEVER insert Hindi or Hinglish words.
- Generate 15-25 actions per scene (more is better for engagement)
- EVERY assigned agent MUST speak at least 3 times
- For multi-slide scenes, you MUST include "transition" actions between slides
  - The first slide is slideIndex 0 (shown by default, no transition needed)
  - To move to slide 2, use {"type": "transition", "slideIndex": 1}
  - Include ALL transitions — one for each slide after the first
- Create DIALOGUE: agents should respond to each other, not just monologue
  - Agent A explains -> Agent B adds perspective -> Agent A builds on it
  - Agent B asks "What about...?" -> Agent A answers
  - Agent A says fact -> Agent B gives analogy -> Agent A summarizes
- Use WHITEBOARD (wb_open/wb_draw_text/wb_draw_shape/wb_close) at least once per scene for formulas, diagrams, or key concepts
- Discussion segments: if you include a "discussion" action, set `"triggerMode": "manual"` so the panel only opens when the teacher clicks the Roundtable button. Never rely on discussions auto-popping mid-scene.
- Speech text should feel like a real conversation, not reading from notes
- Each speech should be 1-3 sentences (short, punchy, conversational)
- Use the speaker's role style: professors explain authoritatively, assistants ask clarifying questions, student reps voice common confusions
- Spotlight the heading element first, then key content elements on each slide
- Keep pauses between speakers SHORT (150-250ms) — the audio engine renders real silences, so large pauses stack into noticeable dead air. Rely on natural TTS cadence, not extra pause actions.
- For introduction scenes: each agent introduces themselves personally
- Use element IDs from the slide content for spotlight/highlight actions
- End with a strong summary or transition statement
- The action flow should follow the slide order: discuss slide 0, transition to 1, discuss 1, transition to 2, etc."""


def generate_scene_actions(scene: dict, agents: list, language: str,
                           config: TenantAIConfig) -> dict | None:
    """Generate rich playback actions for a multi-slide scene. Returns parsed dict."""
    content = scene.get("content", {})

    # Build per-slide element descriptions for the prompt
    slides_desc = []
    total_slide_count = 1
    if isinstance(content, dict):
        slides = content.get("slides", [])
        if slides:
            total_slide_count = len(slides)
            for si, slide in enumerate(slides):
                elements = slide.get("elements", [])
                el_summary = [{"id": e.get("id"), "type": e.get("type"),
                               "content": str(e.get("content", ""))[:80]}
                              for e in elements]
                slides_desc.append({
                    "slideIndex": si,
                    "title": slide.get("title", ""),
                    "speakerScript": slide.get("speakerScript", "")[:200],
                    "elements": el_summary,
                })
        elif content.get("type") == "slide" or "elements" in content:
            # Legacy single-slide format
            elements = content.get("elements", [])
            el_summary = [{"id": e.get("id"), "type": e.get("type"),
                           "content": str(e.get("content", ""))[:80]}
                          for e in elements]
            slides_desc.append({
                "slideIndex": 0,
                "title": content.get("title", scene.get("title", "")),
                "speakerScript": content.get("speakerScript", "")[:200],
                "elements": el_summary,
            })

    # Check both multiAgent.agentIds (frontend format) and agentIds (outline format)
    scene_agent_ids = (
        scene.get("multiAgent", {}).get("agentIds", [])
        or scene.get("agentIds", [])
    )
    assigned_agents = [a for a in agents if a.get("id") in scene_agent_ids]
    if len(assigned_agents) < 2:
        # Ensure at least 2 agents for dialogue
        assigned_agents = agents[:min(len(agents), 3)]

    agent_details = json.dumps([{
        "id": a["id"],
        "name": a["name"],
        "role": a.get("role", "professor"),
        "personality": a.get("personality", ""),
        "speakingStyle": a.get("speakingStyle", ""),
    } for a in assigned_agents])

    slides_json = json.dumps(slides_desc, indent=2) if slides_desc else "[]"

    user_prompt = f"""Generate a rich, multi-agent dialogue sequence for this multi-slide scene:

Scene title: {scene.get("title", "")}
Scene type: {scene.get("type", "lecture")}
Language: {language}
Total slides in this scene: {total_slide_count}

Slides and their elements (use these IDs for spotlight/highlight):
{slides_json}

Agents in this scene:
{agent_details}

IMPORTANT:
- Generate 15-25 actions with rich variety (speech, spotlight, highlight, whiteboard, discussion, transitions)
- Include a "transition" action (with slideIndex) between EACH slide. First slide (index 0) is shown by default.
- ALL agents must participate in dialogue — each agent speaks at least 3 times
- Use whiteboard (wb_open, wb_draw_text/shape, wb_close) at least once for a key concept
- Include at least one discussion action
- Create back-and-forth conversation, not monologue
- Reference element IDs from the slides for spotlight and highlight actions
"""

    raw = _call_llm(config, ACTIONS_SYSTEM_PROMPT, user_prompt,
                    temperature=0.5, max_tokens=4096)
    if not raw:
        fallback = _fallback_actions(scene, assigned_agents)
        _stamp_action_durations(fallback.get("actions", []))
        return fallback

    parsed = _parse_json_from_llm(raw)
    if not parsed or not isinstance(parsed, dict) or "actions" not in parsed:
        fallback = _fallback_actions(scene, assigned_agents)
        _stamp_action_durations(fallback.get("actions", []))
        return fallback

    _stamp_action_durations(parsed["actions"])
    return parsed


# ─── Action post-processing ──────────────────────────────────────────────────

# Character-based speech duration estimator. 55 ms/char approximates a
# natural en-IN TTS cadence (~18 chars/sec). The playback engine uses this
# as a fallback timer when TTS metadata isn't available and as the minimum
# "hold time" for subtitles on slow networks. Minimum 800 ms so very short
# utterances ("Exactly.", "Right.") still register on screen.
_SPEECH_MS_PER_CHAR = 55
_SPEECH_MIN_MS = 800


def _stamp_action_durations(actions: list) -> None:
    """Mutate `actions` in place: add a `durationMs` field to every speech
    action that doesn't already have one. Computed from text length so the
    frontend can synchronize slide transitions and subtitle timing without
    waiting for the audio element to report duration.

    Also normalizes discussion actions: if `triggerMode` is missing, defaults
    to "manual" so stored classrooms generated before Chunk 9 don't auto-pop
    the Roundtable panel mid-scene.
    """
    for action in actions:
        if not isinstance(action, dict):
            continue
        a_type = action.get("type")
        if a_type == "speech" and "durationMs" not in action:
            text = str(action.get("text", ""))
            action["durationMs"] = max(_SPEECH_MIN_MS, round(len(text) * _SPEECH_MS_PER_CHAR))
        elif a_type == "discussion" and "triggerMode" not in action:
            action["triggerMode"] = "manual"


def _persona_flavored(base: str, agent: dict) -> str:
    """Append a persona hint to a fallback speech line so agents still sound distinct
    when the LLM path fails. Pulls first few words of speakingStyle into a parenthetical
    delivery cue; falls back cleanly if no speakingStyle is set.
    """
    style = (agent.get("speakingStyle") or "").strip()
    if not style:
        return base
    # Surface ONE short fragment, not the full sentence.
    fragment = style.split(".")[0].strip()
    if not fragment or len(fragment) > 80:
        return base
    return f"{base} ({fragment.lower()})"


def _fallback_actions(scene: dict, agents: list) -> dict:
    """Deterministic multi-agent fallback actions with transitions and rich action types.

    Honors each agent's speakingStyle so fallback text still reads as that agent's voice
    when the LLM action-generation path fails — otherwise the entire persona investment
    is lost the moment the provider misbehaves.
    """
    primary = agents[0] if agents else {"id": "agent-1", "name": "Instructor"}
    primary_id = primary["id"]
    primary_name = primary.get("name", "Instructor")
    secondary = agents[1] if len(agents) > 1 else None
    content = scene.get("content", {})
    title = scene.get("title", "this topic")

    # Gather slide data for multi-slide transitions
    slides = []
    if isinstance(content, dict):
        slides = content.get("slides", [])
        if not slides and "elements" in content:
            # Single-slide legacy format
            slides = [content]

    actions = []

    # --- Slide 0: Introduction ---
    slide0_script = ""
    slide0_elements = []
    if slides:
        slide0_script = slides[0].get("speakerScript", "")
        slide0_elements = slides[0].get("elements", [])

    actions.append({
        "type": "speech", "agentId": primary_id,
        "text": _persona_flavored(
            slide0_script or f"Let me walk you through {title}.",
            primary,
        ),
    })

    if slide0_elements:
        actions.append({"type": "spotlight", "elementId": slide0_elements[0].get("id", "el-1"), "duration": 2500})

    # Second agent responds
    if secondary:
        actions.append({"type": "pause", "duration": 200})
        actions.append({
            "type": "speech", "agentId": secondary["id"],
            "text": _persona_flavored(
                f"That's a great way to frame it, {primary_name}. Let me add a bit more context.",
                secondary,
            ),
        })

    # --- Transitions for slides 1+ ---
    for si in range(1, len(slides)):
        slide = slides[si]
        slide_elements = slide.get("elements", [])
        slide_script = slide.get("speakerScript", "")

        actions.append({"type": "transition", "slideIndex": si})

        actions.append({
            "type": "speech", "agentId": primary_id,
            "text": _persona_flavored(
                slide_script or f"Moving on to {slide.get('title', 'the next topic')}.",
                primary,
            ),
        })

        if slide_elements:
            actions.append({"type": "spotlight", "elementId": slide_elements[0].get("id", f"el-s{si+1}-1"), "duration": 2000})

        if len(slide_elements) > 1:
            actions.append({"type": "highlight", "elementId": slide_elements[1].get("id", f"el-s{si+1}-2"), "color": "#DBEAFE"})

        if secondary:
            actions.append({"type": "pause", "duration": 200})
            actions.append({
                "type": "speech", "agentId": secondary["id"],
                "text": _persona_flavored(
                    f"That connects nicely to what we covered about {title}.",
                    secondary,
                ),
            })

    # --- Whiteboard segment ---
    actions.append({"type": "wb_open"})
    actions.append({"type": "wb_draw_text", "text": f"Key Concept: {title}", "x": 150, "y": 80, "fontSize": 24, "color": "#1E293B"})
    actions.append({
        "type": "speech", "agentId": primary_id,
        "text": _persona_flavored(
            f"Let me write this on the board so it's clearer. This is the core idea behind {title}.",
            primary,
        ),
    })
    actions.append({"type": "wb_draw_shape", "shape": "rect", "x": 120, "y": 60, "width": 560, "height": 60, "color": "#3B82F6"})
    actions.append({"type": "wb_close"})

    # --- Discussion ---
    all_agent_ids = [a["id"] for a in agents]
    actions.append({"type": "discussion", "sessionType": "qa", "topic": f"What questions do you have about {title}?", "agentIds": all_agent_ids})

    # --- Closing ---
    if secondary:
        actions.append({
            "type": "speech", "agentId": secondary["id"],
            "text": _persona_flavored(
                f"Excellent discussion! The key takeaway from {title} will really help in the next section.",
                secondary,
            ),
        })
    actions.append({
        "type": "speech", "agentId": primary_id,
        "text": _persona_flavored(
            "Well said. Let's move on to see how these concepts apply in practice.",
            primary,
        ),
    })

    return {"actions": actions}


# ─── Chat Generation ────────────────────────────────────────────────────────

CHAT_SYSTEM_PROMPT = """You are a panel of AI teaching agents in an interactive classroom. Multiple agents should respond to the student's question, each bringing their unique perspective and their own voice.

HARD LANGUAGE RULE: Output ONLY English. No Hindi words, no transliterated slang ("theek hai", "bilkul", "achha"), no code-switching. Persona flavor comes from English register (warm/precise/crisp/informal), not from non-English interjections.

You MUST return a valid JSON array of agent responses:
[
  {"agentId": "agent-1", "agentName": "Dr. Aarav Sharma", "content": "Your response..."},
  {"agentId": "agent-2", "agentName": "Ms. Priya Iyer", "content": "Building on that..."}
]

Rules:
- Return 2-3 agent responses (not just one)
- The lead agent (professor) answers first with the main explanation
- Supporting agents add perspective, ask follow-ups, give analogies, or provide examples
- Each response is 2-4 sentences
- EACH AGENT MUST SPEAK IN THEIR OWN VOICE per their `personality` and `speakingStyle`. Do not write generic answers — make them identifiable.
- Be conversational, warm, and encouraging
- Reference the classroom topic + prior conversation naturally — if the student is asking a follow-up, tie it back to what was already discussed
- If the question is off-topic, gently redirect"""


# How many recent turns to inline verbatim; older turns are summarized.
_CHAT_HISTORY_INLINE_LIMIT = 6
# Max history entries to accept from the request body (mirrors frontend cap).
_CHAT_HISTORY_MAX_ENTRIES = 12
# Words shared between a "summarize" command and the set we short-circuit on.
_SUMMARIZE_COMMANDS = frozenset({
    "summarize", "summary", "summarise",
    "summarize key concepts", "summarise key concepts",
    "recap", "recap the key concepts", "recap so far",
    "key concepts", "key takeaways",
})


def _sanitize_chat_history(history: list | None) -> list[dict]:
    """Drop malformed entries, coerce to {'role', 'content'[, 'agentId']} shape,
    and cap length so oversized client payloads can't blow the prompt."""
    if not isinstance(history, list):
        return []
    out: list[dict] = []
    for entry in history:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role")
        content = entry.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str) or not content.strip():
            continue
        clean = {"role": role, "content": content.strip()}
        agent_id = entry.get("agentId")
        if role == "assistant" and isinstance(agent_id, str) and agent_id:
            clean["agentId"] = agent_id
        out.append(clean)
    return out[-_CHAT_HISTORY_MAX_ENTRIES:]


def _render_chat_history_block(history: list[dict]) -> str:
    """Format sanitized history as a plain-text block the LLM can read.

    Inline the last `_CHAT_HISTORY_INLINE_LIMIT` turns verbatim; anything
    older is compressed into a deterministic one-line summary listing the
    student's earlier questions. We avoid a second LLM call in the SSE
    hot path — a simple join is good enough for continuity.
    """
    if not history:
        return ""
    recent = history[-_CHAT_HISTORY_INLINE_LIMIT:]
    older = history[:-_CHAT_HISTORY_INLINE_LIMIT]
    parts: list[str] = []
    if older:
        earlier_q = [e["content"] for e in older if e["role"] == "user"]
        if earlier_q:
            compressed = "; ".join(q[:120] for q in earlier_q[-5:])
            parts.append(f"Earlier in this session the student also asked: {compressed}")
    for e in recent:
        speaker = "Student" if e["role"] == "user" else "Tutor"
        parts.append(f"{speaker}: {e['content']}")
    return "\n".join(parts)


def generate_chat_sse(message: str, classroom_title: str, agents: list,
                      config: TenantAIConfig, history: list | None = None,
                      scene_titles: list[str] | None = None):
    """
    Generator that yields SSE-formatted strings for multi-agent chat responses.
    Multiple agents respond, each with their unique perspective and voice.

    history: optional list of {'role', 'content'} dicts from the frontend
        session cache. Kept short (≤12); older turns are compressed into a
        one-line summary so long sessions don't balloon the prompt.
    scene_titles: optional classroom outline titles, used to ground
        "summarize" commands even when no prior chat exists.
    """
    if not agents:
        agents = [{"id": "agent-1", "name": "Teaching Assistant", "role": "professor"}]

    sanitized_history = _sanitize_chat_history(history)
    message_stripped = (message or "").strip()

    # Short-circuit: "summarize" commands with no history and no outline
    # have nothing to summarize. Respond politely instead of asking the
    # LLM to hallucinate a recap.
    if (
        message_stripped.lower() in _SUMMARIZE_COMMANDS
        and not sanitized_history
        and not scene_titles
    ):
        yield _sse_event("chat_message", {
            "content": (
                "Ask me a specific question first and I'll be happy to "
                "summarize what we've discussed. For example: 'Explain X' "
                "or 'Why does Y happen?' — then ask for a summary."
            ),
            "agentId": agents[0].get("id", "agent-1"),
            "agentName": agents[0].get("name", "Teaching Assistant"),
        })
        yield _sse_done()
        return

    agents_for_prompt = json.dumps([{
        "id": a.get("id"),
        "name": a.get("name"),
        "role": a.get("role", "professor"),
        "personality": a.get("personality", ""),
        "speakingStyle": a.get("speakingStyle", ""),
    } for a in agents[:4]], indent=2)  # Max 4 agents in chat

    history_block = _render_chat_history_block(sanitized_history)
    outline_block = ""
    if scene_titles:
        titles_joined = "; ".join(t for t in scene_titles[:20] if t)
        if titles_joined:
            outline_block = f"Classroom outline (scene titles in order): {titles_joined}\n"

    conversation_block = (
        f"\nConversation so far:\n{history_block}\n" if history_block else ""
    )

    user_prompt = (
        f"Classroom topic: {classroom_title}\n"
        f"{outline_block}"
        "Agents (each must speak in their own voice):\n"
        f"{agents_for_prompt}\n"
        f"{conversation_block}"
        f"\nStudent's current question: {message_stripped}\n\n"
        "Generate 2-3 agent responses. If this question is a follow-up, "
        "reference the earlier conversation naturally. ENGLISH ONLY."
    )

    try:
        raw = _call_llm(config, CHAT_SYSTEM_PROMPT, user_prompt,
                        temperature=0.7, max_tokens=2048)
    except Exception as exc:  # noqa: BLE001 — defensive boundary for SSE
        logger.warning("chat LLM call failed: %s", exc)
        raw = None

    if not raw:
        yield _sse_event("chat_message", {
            "content": "I'm having trouble processing your question right now. Could you try again?",
            "agentId": agents[0].get("id", "agent-1"),
            "agentName": agents[0].get("name", "Teaching Assistant"),
        })
        yield _sse_done()
        return

    try:
        parsed = _parse_json_from_llm(raw)
    except Exception as exc:  # noqa: BLE001 — defensive
        logger.warning("chat LLM parse failed err=%s raw=%s", exc, str(raw)[:500])
        parsed = None

    if isinstance(parsed, list):
        emitted = 0
        for resp in parsed:
            if isinstance(resp, dict) and resp.get("content"):
                yield _sse_event("chat_message", {
                    "content": resp["content"],
                    "agentId": resp.get("agentId", agents[0].get("id")),
                    "agentName": resp.get("agentName", agents[0].get("name")),
                })
                emitted += 1
        if emitted == 0:
            # Parsed list but every item was malformed — fall back to raw.
            logger.warning("chat LLM returned list with no valid entries; raw=%s", str(raw)[:500])
            yield _sse_event("chat_message", {
                "content": str(raw),
                "agentId": agents[0].get("id", "agent-1"),
                "agentName": agents[0].get("name", "Teaching Assistant"),
            })
    else:
        # Fallback: treat as single response from lead agent
        yield _sse_event("chat_message", {
            "content": str(raw),
            "agentId": agents[0].get("id", "agent-1"),
            "agentName": agents[0].get("name", "Teaching Assistant"),
        })

    yield _sse_done()


# ─── TTS Generation ─────────────────────────────────────────────────────────

def generate_tts_audio(text: str, config: TenantAIConfig,
                       voice_id: str | None = None) -> bytes | None:
    """
    Generate TTS audio using the tenant's configured TTS provider.
    Returns MP3 bytes or None on failure.

    Args:
        text: The text to synthesize.
        config: Tenant AI configuration with provider settings.
        voice_id: Optional per-agent voice override. If provided, this takes
                  priority over the tenant default (config.tts_voice_id).
                  Can be an Edge TTS voice name (e.g. "en-IN-NeerjaNeural")
                  or a provider-specific voice ID.

    Voice-ID-based routing: when the caller passes an Azure Neural voice
    name (matches `xx-YY-*Neural`), we route to Edge TTS regardless of
    the tenant's configured provider. This is how the per-agent Indian
    voices added in Chunk 4 actually play on tenants that are otherwise
    configured for ElevenLabs / OpenAI — those providers don't accept
    Azure Neural voice IDs, and shipping per-agent voices requires a
    consistent backend that understands them. Edge TTS is free and
    supports the full Azure Neural catalog.
    """
    # Resolve effective voice: explicit override > tenant config default
    effective_voice = voice_id or config.tts_voice_id

    # Azure Neural voice IDs (e.g. en-IN-NeerjaNeural) — always Edge TTS.
    if effective_voice and _is_azure_neural_voice(effective_voice):
        audio = _tts_edge(text, effective_voice)
        if audio:
            return audio
        # Edge TTS failed (network, throttle, package missing). Fall
        # through to the tenant's configured provider — but SWAP the
        # voice to the tenant default, because ElevenLabs / OpenAI
        # will reject the Azure voice ID with a 400 and we end up
        # returning 204 (silence). A generic tenant voice is worse for
        # persona but better than silence on the demo.
        logger.warning(
            "Edge TTS failed for %r, falling back to tenant provider %r with default voice",
            effective_voice, config.tts_provider,
        )
        if config.tts_voice_id and not _is_azure_neural_voice(config.tts_voice_id):
            effective_voice = config.tts_voice_id
        else:
            # Tenant default is also an Azure voice (or empty) — let the
            # provider pick its own default by passing None.
            effective_voice = None

    tts_provider = config.tts_provider or "disabled"
    if tts_provider == "disabled":
        return None

    # Edge TTS is free — no API key required
    if tts_provider == "edge":
        return _tts_edge(text, effective_voice)

    tts_key = config.get_tts_api_key()
    if not tts_key:
        # No API key configured — fall back to Edge TTS as a free alternative
        logger.info("No TTS API key for %s, falling back to Edge TTS", tts_provider)
        return _tts_edge(text, effective_voice)

    try:
        if tts_provider == "openai":
            return _tts_openai(text, tts_key, effective_voice)
        elif tts_provider == "elevenlabs":
            return _tts_elevenlabs(text, tts_key, effective_voice)
        elif tts_provider == "azure":
            # Azure TTS direct API not yet implemented — fall back to Edge TTS
            return _tts_edge(text, effective_voice)
        else:
            logger.warning("Unsupported TTS provider: %s, falling back to Edge TTS", tts_provider)
            return _tts_edge(text, effective_voice)
    except Exception as e:
        logger.error("TTS generation failed (%s): %s — falling back to Edge TTS", tts_provider, e)
        return _tts_edge(text, effective_voice)


def _is_azure_neural_voice(voice_id: str) -> bool:
    """Heuristic: does this voice ID look like an Azure Neural voice?

    Azure Neural voices follow the pattern `xx-YY-NameNeural` or
    `xx-YY-NameNeural` with multi-letter region codes. A short regex check
    is enough — ElevenLabs + OpenAI IDs don't follow this pattern.
    """
    if not voice_id or not isinstance(voice_id, str):
        return False
    # Examples: en-IN-NeerjaNeural, en-US-JennyNeural, hi-IN-MadhurNeural
    import re
    return bool(re.match(r"^[a-z]{2}-[A-Z]{2}-[A-Za-z]+Neural$", voice_id))


def _tts_openai(text: str, api_key: str, voice_id: str | None) -> bytes | None:
    """Call OpenAI TTS API directly."""
    voice = voice_id or "alloy"
    url = "https://api.openai.com/v1/audio/speech"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "tts-1",
        "input": text[:4096],
        "voice": voice,
        "response_format": "mp3",
    }
    resp = http_requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.content


def _tts_elevenlabs(text: str, api_key: str, voice_id: str | None) -> bytes | None:
    """Call ElevenLabs TTS API directly."""
    voice = voice_id or "21m00Tcm4TlvDq8ikWAM"  # Rachel default
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text[:5000],
        "model_id": "eleven_monolingual_v1",
    }
    resp = http_requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.content


def _tts_edge(text: str, voice_id: str | None) -> bytes | None:
    """Generate TTS using Edge TTS (free Microsoft TTS). No API key needed."""
    from apps.courses.tts_service import synthesize_speech

    # Only use voice_id if it looks like an Edge TTS voice (e.g. "en-US-GuyNeural").
    # ElevenLabs/OpenAI voice IDs are opaque strings — don't pass those to Edge TTS.
    edge_voice = "en-US-GuyNeural"
    if voice_id and "-" in voice_id and "Neural" in voice_id:
        edge_voice = voice_id

    try:
        path = synthesize_speech(
            text=text[:5000],
            voice_id=edge_voice,
            provider="edge_tts",
        )
        if not path:
            return None
        import os
        try:
            with open(path, "rb") as f:
                return f.read()
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
    except Exception as e:
        logger.error("Edge TTS generation failed: %s", e)
        return None


# ─── Quiz Grading Fallback ──────────────────────────────────────────────────

QUIZ_GRADE_SYSTEM_PROMPT = """You are a fair, encouraging teacher grading a student's answer.

Given the student's answer and the expected answer (with optional rubric), evaluate the response.

Return a valid JSON object:
{
  "score": 85,
  "feedback": "Good understanding of the core concept. You correctly identified X and Y. To improve, consider also mentioning Z.",
  "isCorrect": true
}

Rules:
- score: integer 0-100
- isCorrect: true if score >= 70, false otherwise
- feedback: 1-3 sentences. Be encouraging but honest. Point out what was correct, what was missing, and how to improve.
- For multiple choice questions: score is 100 (correct) or 0 (incorrect)
- For short answer questions: grade on a scale based on completeness, accuracy, and understanding
- Be lenient with minor spelling/grammar issues if the concept is correct
- If the student answer is blank or clearly off-topic, score 0 with constructive feedback"""


def fallback_quiz_grade(student_answer: str, expected_answer: str,
                        rubric: str | None, config: TenantAIConfig) -> dict:
    """
    Grade a student's answer using the LLM when the OpenMAIC sidecar is down.
    Returns {"score": int, "feedback": str, "isCorrect": bool}.
    """
    user_prompt = f"""Grade this student answer:

Student's answer: {student_answer}

Expected/correct answer: {expected_answer}
"""
    if rubric:
        user_prompt += f"\nGrading rubric: {rubric}\n"

    raw = _call_llm(config, QUIZ_GRADE_SYSTEM_PROMPT, user_prompt,
                    temperature=0.3, max_tokens=512)
    if not raw:
        return _fallback_quiz_grade_deterministic(student_answer, expected_answer)

    parsed = _parse_json_from_llm(raw)
    if not parsed or not isinstance(parsed, dict):
        return _fallback_quiz_grade_deterministic(student_answer, expected_answer)

    # Validate and normalize the response
    score = parsed.get("score", 0)
    if not isinstance(score, (int, float)):
        score = 0
    score = max(0, min(100, int(score)))

    return {
        "score": score,
        "feedback": parsed.get("feedback", "Thank you for your answer."),
        "isCorrect": score >= 70,
    }


def _fallback_quiz_grade_deterministic(student_answer: str,
                                        expected_answer: str) -> dict:
    """Simple string-match fallback when even the LLM call fails."""
    if not student_answer or not student_answer.strip():
        return {
            "score": 0,
            "feedback": "No answer was provided. Please try again.",
            "isCorrect": False,
        }

    student_norm = student_answer.strip().lower()
    expected_norm = expected_answer.strip().lower()

    # Exact match
    if student_norm == expected_norm:
        return {
            "score": 100,
            "feedback": "Correct! Great job.",
            "isCorrect": True,
        }

    # Partial match — check if expected answer is contained in student answer
    if expected_norm in student_norm or student_norm in expected_norm:
        return {
            "score": 75,
            "feedback": "Good attempt! Your answer captures the main idea.",
            "isCorrect": True,
        }

    # Word overlap heuristic
    student_words = set(student_norm.split())
    expected_words = set(expected_norm.split())
    if expected_words:
        overlap = len(student_words & expected_words) / len(expected_words)
        if overlap >= 0.5:
            return {
                "score": 60,
                "feedback": "Partial credit. You mentioned some key concepts but missed others. Review the expected answer for a more complete understanding.",
                "isCorrect": False,
            }

    return {
        "score": 20,
        "feedback": "Your answer does not match the expected response. Please review the material and try again.",
        "isCorrect": False,
    }
