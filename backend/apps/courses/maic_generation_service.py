"""
Direct LLM generation for OpenMAIC AI Classrooms.

Used when the OpenMAIC sidecar is unavailable. Calls the tenant's configured
LLM provider (OpenRouter, OpenAI, etc.) directly from Django using the
encrypted API keys stored in TenantAIConfig.

Functions:
    generate_outline_sse()   → SSE text iterator for outline streaming
    generate_scene_content() → dict with slide data
    generate_scene_actions() → dict with action list
"""

import io
import json
import logging
import uuid

import requests as http_requests
from json_repair import repair_json

from apps.courses.maic_models import TenantAIConfig

logger = logging.getLogger(__name__)

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


# ─── SSE Formatting ──────────────────────────────────────────────────────────

def _sse_event(event_type: str, data: dict) -> str:
    """Format a single SSE event string."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


def _sse_done() -> str:
    return "data: [DONE]\n\n"


# ─── Outline Generation ──────────────────────────────────────────────────────

OUTLINE_SYSTEM_PROMPT = """You are an expert educational content designer creating a multi-agent interactive classroom.

Return a valid JSON object with this exact structure:
{
  "scenes": [
    {
      "id": "scene-1",
      "title": "Scene title",
      "description": "Brief description of what this scene covers",
      "type": "lecture|discussion|quiz|activity|summary",
      "estimatedMinutes": 3,
      "agentIds": ["agent-1", "agent-2"]
    }
  ],
  "agents": [
    {
      "id": "agent-1",
      "name": "Professor Chen",
      "role": "professor",
      "avatar": "👨‍🏫",
      "color": "#4F46E5",
      "personality": "Warm, authoritative, uses analogies to explain complex ideas",
      "expertise": "Subject matter expert who leads lectures"
    }
  ],
  "totalMinutes": 20
}

Rules:
- The FIRST scene MUST be type "introduction" — all agents introduce themselves and preview the class
- Create exactly the requested number of scenes and agents after the introduction
- Each scene should have 2-5 minutes estimated time
- Every scene MUST have at least 2 agents assigned (for dialogue)
- Agents should have DISTINCT personalities — one might be enthusiastic, another analytical, another asks probing questions
- Use diverse scene types: introduction → lectures → discussion → quiz → summary
- Agent roles: professor (leads), teaching_assistant (supports, asks questions), student_rep (raises common confusions), moderator (guides discussion)
- Agent names should be realistic full names (e.g. "Dr. Sarah Kim", "Professor James Rivera")
- Agent colors should be visually distinct hex colors
- Agent avatars should be relevant emoji
- Include a "personality" field that describes how this agent talks and thinks
- Include an "expertise" field that describes what this agent contributes"""


def generate_outline_sse(topic: str, language: str, agent_count: int,
                         scene_count: int, pdf_text: str | None,
                         config: TenantAIConfig):
    """
    Generator that yields SSE-formatted strings for outline streaming.
    Used as the body of a StreamingHttpResponse.
    """
    user_prompt = f"""Create a classroom outline for the following:

Topic: {topic}
Language: {language}
Number of AI agents: {agent_count}
Number of scenes: {scene_count}
"""
    if pdf_text:
        # Truncate to avoid token limits
        excerpt = pdf_text[:6000]
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

    # Ensure required fields exist
    scenes = parsed.get("scenes", [])
    agents = parsed.get("agents", [])
    total_minutes = parsed.get("totalMinutes", sum(s.get("estimatedMinutes", 3) for s in scenes))

    # Validate/fix scene IDs and agent IDs — ensure every scene has ≥2 agents
    all_agent_ids = [a.get("id", f"agent-{j+1}") for j, a in enumerate(agents)]
    for i, scene in enumerate(scenes):
        if not scene.get("id"):
            scene["id"] = f"scene-{i + 1}"
        if not scene.get("agentIds") or len(scene.get("agentIds", [])) < 2:
            # Assign at least 2 agents — primary + one supporting
            scene["agentIds"] = all_agent_ids[:min(len(all_agent_ids), 3)]

    for i, agent in enumerate(agents):
        if not agent.get("id"):
            agent["id"] = f"agent-{i + 1}"
        if not agent.get("color"):
            agent["color"] = ["#4F46E5", "#059669", "#D97706", "#DC2626", "#7C3AED"][i % 5]
        if not agent.get("avatar"):
            agent["avatar"] = ["👨‍🏫", "👩‍🎓", "🤖", "👨‍💼", "👩‍🔬"][i % 5]

    outline_data = {
        "scenes": scenes,
        "agents": agents,
        "totalMinutes": total_minutes,
    }

    yield _sse_event("generation_progress", {"progress": 90})
    yield _sse_event("outline", outline_data)
    yield _sse_event("generation_progress", {"progress": 100})
    yield _sse_done()


# ─── Scene Content Generation ────────────────────────────────────────────────

SCENE_CONTENT_SYSTEM_PROMPT = """You are an expert educational content designer creating rich, visually appealing slides for an interactive AI classroom.

Given a scene from a classroom outline, generate detailed slide content with well-laid-out elements.

Return a valid JSON object:
{
  "slide": {
    "id": "slide-<scene_id>",
    "title": "Slide title",
    "elements": [
      {
        "type": "text",
        "id": "el-1",
        "x": 40,
        "y": 30,
        "width": 720,
        "height": 50,
        "content": "Main Heading Text",
        "style": {"fontSize": 32, "fontWeight": "bold", "color": "#1E293B"}
      },
      {
        "type": "text",
        "id": "el-2",
        "x": 40,
        "y": 90,
        "width": 720,
        "height": 20,
        "content": "A brief subtitle or context line",
        "style": {"fontSize": 16, "color": "#64748B", "fontStyle": "italic"}
      },
      {
        "type": "text",
        "id": "el-3",
        "x": 40,
        "y": 130,
        "width": 720,
        "height": 260,
        "content": "• Key point one explained clearly\\n\\n• Key point two with detail\\n\\n• Key point three with example\\n\\n• Key point four — practical application",
        "style": {"fontSize": 18, "color": "#334155", "lineHeight": 1.6}
      },
      {
        "type": "text",
        "id": "el-4",
        "x": 40,
        "y": 400,
        "width": 720,
        "height": 30,
        "content": "💡 Key takeaway or memorable insight",
        "style": {"fontSize": 15, "color": "#0F766E", "fontWeight": "600"}
      }
    ],
    "background": "#FFFFFF",
    "speakerScript": "A detailed 3-5 sentence script that the lead agent reads aloud. It should explain the content naturally, with context, transitions, and a conversational tone — as if teaching a real class.",
    "duration": 45
  }
}

Rules:
- Coordinate space is 800x450 pixels
- Create 3-5 text elements per slide (heading, optional subtitle, body content, takeaway)
- Use \\n\\n for paragraph breaks in bullet content (NOT just \\n)
- Heading: bold, 28-34px, dark color (#1E293B)
- Body: 16-20px, readable color (#334155)
- Takeaway/highlight: distinctive color, smaller font
- Speaker script MUST be 3-5 sentences, written in first person as the presenting agent
- Speaker script should add context BEYOND what's on the slide (don't just read the bullets)
- For introduction scenes: the speaker script should introduce the agent and preview the lesson
- Duration should be 30-60 seconds per slide

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


def generate_scene_content(scene: dict, agents: list, language: str,
                           config: TenantAIConfig) -> dict | None:
    """Generate slide content for a single scene. Returns parsed dict."""
    scene_type = scene.get("type", "lecture")
    user_prompt = f"""Generate content for this classroom scene:

Scene title: {scene["title"]}
Scene description: {scene.get("description", "")}
Scene type: {scene_type}
Language: {language}
Assigned agents: {json.dumps([a["name"] for a in agents if a["id"] in scene.get("agentIds", [])])}

{"Generate quiz questions (3-4 multiple choice questions)." if scene_type == "quiz" else "Generate a visual slide with text elements and a speaker script."}
"""

    raw = _call_llm(config, SCENE_CONTENT_SYSTEM_PROMPT, user_prompt, temperature=0.6, max_tokens=3000)
    if not raw:
        return _fallback_scene_content(scene)

    parsed = _parse_json_from_llm(raw)
    if not parsed or not isinstance(parsed, dict):
        return _fallback_scene_content(scene)

    # Ensure slide has required fields
    if "slide" in parsed:
        slide = parsed["slide"]
        if not slide.get("id"):
            slide["id"] = f"slide-{scene.get('id', uuid.uuid4().hex[:8])}"
        if not slide.get("title"):
            slide["title"] = scene.get("title", "Untitled")
        if not slide.get("elements"):
            slide["elements"] = []
        # Ensure each element has an id
        for j, el in enumerate(slide["elements"]):
            if not el.get("id"):
                el["id"] = f"el-{j + 1}"

    return parsed


def _fallback_scene_content(scene: dict) -> dict:
    """Deterministic fallback when LLM fails."""
    scene_id = scene.get("id", "scene-1")
    return {
        "slide": {
            "id": f"slide-{scene_id}",
            "title": scene.get("title", "Untitled"),
            "elements": [
                {
                    "type": "text",
                    "id": "el-heading",
                    "x": 50, "y": 80, "width": 700, "height": 40,
                    "content": scene.get("title", "Untitled"),
                    "style": {"fontSize": 28, "fontWeight": "bold", "color": "#1F2937"},
                },
                {
                    "type": "text",
                    "id": "el-body",
                    "x": 50, "y": 150, "width": 700, "height": 200,
                    "content": scene.get("description", "Content for this scene."),
                    "style": {"fontSize": 18, "color": "#4B5563"},
                },
            ],
            "background": "#FFFFFF",
            "speakerScript": scene.get("description", f"Let's talk about {scene.get('title', 'this topic')}."),
            "duration": scene.get("estimatedMinutes", 3) * 60,
        }
    }


# ─── Scene Actions Generation ────────────────────────────────────────────────

ACTIONS_SYSTEM_PROMPT = """You are an expert director choreographing a multi-agent interactive classroom. Your job is to create a dynamic, engaging sequence where MULTIPLE agents teach together — like a real classroom with a professor and teaching assistants.

Given a scene's content and agents, generate a sequence of playback actions that creates DIALOGUE between agents.

Return a valid JSON object:
{
  "actions": [
    {"type": "speech", "agentId": "agent-1", "text": "Welcome everyone! Today we're exploring..."},
    {"type": "spotlight", "elementId": "el-1", "duration": 2500},
    {"type": "speech", "agentId": "agent-1", "text": "Let me start by explaining the first key concept..."},
    {"type": "highlight", "elementId": "el-3", "color": "#DBEAFE"},
    {"type": "speech", "agentId": "agent-2", "text": "Great point! I'd like to add that many students find this confusing at first. Think of it like..."},
    {"type": "pause", "duration": 800},
    {"type": "speech", "agentId": "agent-1", "text": "Exactly! And building on that analogy..."},
    {"type": "spotlight", "elementId": "el-4", "duration": 2000},
    {"type": "speech", "agentId": "agent-2", "text": "So the key takeaway here is..."}
  ]
}

Action types:
- speech: Agent speaks text (requires agentId, text). Text should be 1-3 sentences, natural and conversational.
- spotlight: Highlight an element (requires elementId, duration in ms)
- highlight: Color-highlight an element (requires elementId, color hex like "#DBEAFE")
- pause: Brief dramatic pause (requires duration in ms, typically 500-1500)

CRITICAL RULES:
- Generate 6-12 actions per scene (more is better for engagement)
- EVERY assigned agent MUST speak at least twice
- Create DIALOGUE: agents should respond to each other, not just monologue
  - Agent A explains → Agent B adds perspective → Agent A builds on it
  - Agent B asks "What about...?" → Agent A answers
  - Agent A says fact → Agent B gives analogy → Agent A summarizes
- Speech text should feel like a real conversation, not reading from notes
- Each speech should be 1-3 sentences (short, punchy, conversational)
- Use the speaker's NAME style: professors explain authoritatively, assistants ask clarifying questions, student reps voice common confusions
- Spotlight the heading element first, then key content elements
- Add pauses (500-1000ms) between speaker changes for natural pacing
- For introduction scenes: each agent introduces themselves personally
- Use element IDs from the slide content for spotlight/highlight actions
- End with a strong summary or transition statement"""


def generate_scene_actions(scene: dict, agents: list, language: str,
                           config: TenantAIConfig) -> dict | None:
    """Generate playback actions for a scene. Returns parsed dict."""
    elements_desc = ""
    content = scene.get("content", {})
    if isinstance(content, dict) and content.get("type") == "slide":
        elements = content.get("elements", [])
        elements_desc = json.dumps([{"id": e.get("id"), "type": e.get("type"), "content": str(e.get("content", ""))[:100]} for e in elements])

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
    } for a in assigned_agents])

    user_prompt = f"""Generate a rich, multi-agent dialogue sequence for this scene:

Scene title: {scene.get("title", "")}
Scene type: {scene.get("type", "slide")}
Language: {language}
Slide elements (use these IDs for spotlight/highlight): {elements_desc}
Speaker script (use as basis for the lead agent's content): {scene.get("content", {}).get("speakerScript", "") if isinstance(scene.get("content"), dict) else ""}

Agents in this scene:
{agent_details}

IMPORTANT: Generate 8-12 actions where ALL agents participate in dialogue. Create a back-and-forth conversation between the agents about this topic. Each agent should speak at least 2 times. Spotlight key elements as agents discuss them.
"""

    raw = _call_llm(config, ACTIONS_SYSTEM_PROMPT, user_prompt, temperature=0.5, max_tokens=2000)
    if not raw:
        return _fallback_actions(scene, assigned_agents)

    parsed = _parse_json_from_llm(raw)
    if not parsed or not isinstance(parsed, dict) or "actions" not in parsed:
        return _fallback_actions(scene, assigned_agents)

    return parsed


def _fallback_actions(scene: dict, agents: list) -> dict:
    """Deterministic multi-agent fallback actions."""
    primary_id = agents[0]["id"] if agents else "agent-1"
    primary_name = agents[0].get("name", "Instructor") if agents else "Instructor"
    content = scene.get("content", {})
    script = ""
    if isinstance(content, dict):
        script = content.get("speakerScript", "") or scene.get("description", "")
    title = scene.get("title", "this topic")

    actions = [
        {"type": "speech", "agentId": primary_id, "text": script or f"Let me walk you through {title}."},
    ]

    # Spotlight first element
    if isinstance(content, dict):
        elements = content.get("elements", [])
        if elements:
            actions.append({"type": "spotlight", "elementId": elements[0].get("id", "el-1"), "duration": 2500})

    # Second agent adds perspective
    if len(agents) > 1:
        second_id = agents[1]["id"]
        second_name = agents[1].get("name", "Assistant")
        actions.append({"type": "pause", "duration": 800})
        actions.append({"type": "speech", "agentId": second_id,
                        "text": f"Great overview, {primary_name}! Students often ask about the practical applications of {title}. Let me add some context."})
        # Spotlight another element if available
        if isinstance(content, dict):
            elements = content.get("elements", [])
            if len(elements) > 1:
                actions.append({"type": "highlight", "elementId": elements[-1].get("id", "el-2"), "color": "#DBEAFE"})
        actions.append({"type": "speech", "agentId": primary_id,
                        "text": f"Thank you, {second_name}. That's an excellent point. Let's continue to the next part."})

    return {"actions": actions}


# ─── Chat Generation ────────────────────────────────────────────────────────

CHAT_SYSTEM_PROMPT = """You are a panel of AI teaching agents in an interactive classroom. Multiple agents should respond to the student's question, each bringing their unique perspective.

You MUST return a valid JSON array of agent responses:
[
  {{"agentId": "agent-1", "agentName": "Dr. Smith", "content": "Your response here..."}},
  {{"agentId": "agent-2", "agentName": "Alex", "content": "Building on that, I'd add..."}}
]

Rules:
- Return 2-3 agent responses (not just one)
- The lead agent (professor) answers first with the main explanation
- Supporting agents add perspective, ask follow-ups, give analogies, or provide examples
- Each response should be 2-4 sentences
- Be conversational, warm, and encouraging
- Reference the classroom topic naturally
- If the question is off-topic, gently redirect
- Use the agent's personality and role to shape their response style"""


def generate_chat_sse(message: str, classroom_title: str, agents: list,
                      config: TenantAIConfig):
    """
    Generator that yields SSE-formatted strings for multi-agent chat responses.
    Multiple agents respond, each with their unique perspective.
    """
    if not agents:
        agents = [{"id": "agent-1", "name": "Teaching Assistant", "role": "professor"}]

    agent_roster = json.dumps([{
        "agentId": a.get("id"),
        "agentName": a.get("name"),
        "role": a.get("role", "professor"),
        "personality": a.get("personality", ""),
    } for a in agents[:4]])  # Max 4 agents in chat

    system = f"""{CHAT_SYSTEM_PROMPT}

Classroom topic: {classroom_title}

Available agents (use these exact IDs and names):
{agent_roster}

Respond with a JSON array. The first response should be from the lead professor, followed by 1-2 supporting agents."""

    raw = _call_llm(config, system, message, temperature=0.7, max_tokens=2048)

    if not raw:
        yield _sse_event("chat_message", {
            "content": "I'm having trouble processing your question right now. Could you try again?",
            "agentId": agents[0].get("id", "agent-1"),
            "agentName": agents[0].get("name", "Teaching Assistant"),
        })
        yield _sse_done()
        return

    # Parse the multi-agent response
    parsed = _parse_json_from_llm(raw)
    if isinstance(parsed, list):
        for resp in parsed:
            if isinstance(resp, dict) and resp.get("content"):
                yield _sse_event("chat_message", {
                    "content": resp["content"],
                    "agentId": resp.get("agentId", agents[0].get("id")),
                    "agentName": resp.get("agentName", agents[0].get("name")),
                })
    else:
        # Fallback: treat as single response from lead agent
        yield _sse_event("chat_message", {
            "content": raw,
            "agentId": agents[0].get("id", "agent-1"),
            "agentName": agents[0].get("name", "Teaching Assistant"),
        })

    yield _sse_done()


# ─── TTS Generation ─────────────────────────────────────────────────────────

def generate_tts_audio(text: str, config: TenantAIConfig) -> bytes | None:
    """
    Generate TTS audio using the tenant's configured TTS provider.
    Returns MP3 bytes or None on failure.
    """
    tts_provider = config.tts_provider or "disabled"
    if tts_provider == "disabled":
        return None

    tts_key = config.get_tts_api_key()
    if not tts_key:
        return None

    try:
        if tts_provider == "openai":
            return _tts_openai(text, tts_key, config.tts_voice_id)
        elif tts_provider == "elevenlabs":
            return _tts_elevenlabs(text, tts_key, config.tts_voice_id)
        else:
            logger.warning("Unsupported TTS provider: %s", tts_provider)
            return None
    except Exception as e:
        logger.error("TTS generation failed (%s): %s", tts_provider, e)
        return None


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
