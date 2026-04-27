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

# TEST-P1-9: MAICPhase + log_extra live in apps.courses._log_helpers so
# tasks/views/services can import them without dragging in the full LLM
# generation module.  Re-exported here so legacy callers that imported
# these names from ``maic_generation_service`` keep working without
# churn (SPRINT-2-BATCH-8-F2: ``_log_extra`` alias deleted).
from apps.courses._log_helpers import MAICPhase, log_extra  # noqa: F401

# TEST-P1-10: Prometheus instruments for the MAIC pipeline. Only the
# call-site decorations live in this module; the global Counter/Histogram
# objects are defined in utils.metrics so tests can read REGISTRY samples
# without importing the heavy generation surface.
from utils.metrics import (
    maic_scene_generation_total,
    time_llm_call,
)

logger = logging.getLogger(__name__)

# ─── Scene Content Length Budgets ────────────────────────────────────────────
#
# Server-side caps for LLM-generated scene content. These match what the
# frontend SlideRenderer / action-engine can comfortably display and are the
# source of truth. Frontend caps (where they exist) are advisory; these enforce.
# Truncation preserves word boundaries so rendered text doesn't end mid-word.

# CG-P0-7 (2026-04-27): caps raised after content-quality audit. Previous
# values were silently truncating LLM output and producing "AI-generated
# bullet soup" — speakerScript ≤1500 chars ≈ 60s of narration vs the 2-3 min
# a teacher would actually deliver per slide. SLIDE_BULLETS_MAX_COUNT 7 was
# dropping items 8+ on rich content slides. New caps line up with what the
# slide canvas can actually render at typical teacher widths.
SLIDE_TITLE_MAX_CHARS = 160
SLIDE_BULLET_MAX_CHARS = 400
SLIDE_BULLETS_MAX_COUNT = 12
SPEAKER_NOTES_MAX_CHARS = 4000
SCENE_SPEECH_MAX_CHARS = 5000
QUIZ_QUESTION_MAX_CHARS = 600
QUIZ_OPTION_MAX_CHARS = 300


def _truncate_to_word_boundary(text: str, max_chars: int) -> str:
    """Truncate *text* to *max_chars*, snapping back to the last word boundary.

    If the text is already within budget the original string is returned
    unchanged (no copy). The result always has ``len(result) <= max_chars``.

    Defensive fallback: if snapping to a word boundary would produce an empty
    string (e.g. input is pure whitespace longer than *max_chars*), the
    function falls back to a hard character slice so the caller always gets
    a non-empty result when the original text is non-empty.
    """
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    # Walk backwards to the last whitespace so we don't cut mid-word.
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    result = truncated.rstrip()
    # F3 / SPRINT-2-BATCH-5-F5 defensive fallback: pure-whitespace input after
    # rstrip produces an empty string.  Trim leading whitespace first and
    # hard-slice — this returns meaningful content when the input starts with
    # spaces but has real words after.  If the ENTIRE input is whitespace,
    # lstrip() yields "" and we return "" so the upstream caller can decide
    # whether to substitute a placeholder.
    if not result:
        lstripped = text.lstrip()
        return lstripped[:max_chars]
    return result


def _enforce_length_budgets(
    parsed: dict,
    scene_type: str,
    classroom_id: str | None = None,
) -> dict:
    """Truncate over-budget LLM-generated fields in *parsed* in place.

    Covers:
    - slides[*].title              → SLIDE_TITLE_MAX_CHARS
    - slides[*].elements[*] bullet text → SLIDE_BULLET_MAX_CHARS (body elements)
    - slides[*].elements[] bullet count → SLIDE_BULLETS_MAX_COUNT
    - slides[*].speakerScript / speakerNotes → SPEAKER_NOTES_MAX_CHARS
    - actions[*].text (speech)     → SCENE_SPEECH_MAX_CHARS
    - questions[*].text            → QUIZ_QUESTION_MAX_CHARS
    - questions[*].options[*].text / options[*] string → QUIZ_OPTION_MAX_CHARS

    Logs a structured WARN for each field that required truncation so the ops
    team can track budget-hit rates per generation path.

    The helper is idempotent — running it twice on already-truncated output
    produces no further mutation and no second log emission.

    Parameters
    ----------
    parsed :
        The parsed LLM output dict (mutated in place).
    scene_type :
        Caller label (e.g. ``"lecture"``, ``"quiz"``, ``"scene_actions"``)
        forwarded into the structured log ``path`` field.
    classroom_id :
        Optional classroom UUID for log correlation. Forwarded into the
        structured WARN so ops can filter budget hits by classroom.

    Returns
    -------
    dict
        The (possibly mutated) *parsed* dict.
    """

    def _warn(field: str, original: int, truncated: int) -> None:
        logger.warning(
            "length_budget_truncate: %s.%s %d→%d chars",
            scene_type, field, original, truncated,
            extra=log_extra(
                MAICPhase.ENFORCE_BUDGETS,
                classroom_id,
                metric="length_budget_truncate",
                path=scene_type,
                field=field,
                original_chars=original,
                truncated_chars=truncated,
            ),
        )

    # ── slides ──────────────────────────────────────────────────────────────
    for slide in parsed.get("slides") or []:
        if not isinstance(slide, dict):
            continue

        # title
        title = slide.get("title")
        if isinstance(title, str):
            capped = _truncate_to_word_boundary(title, SLIDE_TITLE_MAX_CHARS)
            if len(capped) < len(title):
                _warn("slide.title", len(title), len(capped))
                slide["title"] = capped

        # speakerScript / speakerNotes
        for notes_key in ("speakerScript", "speakerNotes"):
            notes = slide.get(notes_key)
            if isinstance(notes, str):
                capped = _truncate_to_word_boundary(notes, SPEAKER_NOTES_MAX_CHARS)
                if len(capped) < len(notes):
                    _warn(f"slide.{notes_key}", len(notes), len(capped))
                    slide[notes_key] = capped

        # elements — bullet text + bullet count
        elements = slide.get("elements")
        if isinstance(elements, list):
            # Count-cap first (drop tail items)
            body_indices = [
                i for i, el in enumerate(elements)
                if isinstance(el, dict) and el.get("type") in ("text", "bullet", "bullets", "list")
            ]
            if len(body_indices) > SLIDE_BULLETS_MAX_COUNT:
                # Keep only the first N body elements; preserve non-bullet elements
                body_indices_set = set(body_indices)  # F5: hoisted out of comprehension
                keep_body = set(body_indices[:SLIDE_BULLETS_MAX_COUNT])
                new_elements = [
                    el for i, el in enumerate(elements)
                    if i not in body_indices_set or i in keep_body
                ]
                _warn("slide.bullets_count", len(body_indices), SLIDE_BULLETS_MAX_COUNT)
                slide["elements"] = new_elements
                elements = slide["elements"]

            # Per-bullet text cap
            for el in elements:
                if not isinstance(el, dict):
                    continue
                if el.get("type") in ("text", "bullet", "bullets", "list"):
                    content = el.get("content")
                    if isinstance(content, str):
                        capped = _truncate_to_word_boundary(content, SLIDE_BULLET_MAX_CHARS)
                        if len(capped) < len(content):
                            _warn("slide.bullet_text", len(content), len(capped))
                            el["content"] = capped

    # ── actions (scene_actions path) ─────────────────────────────────────────
    for action in parsed.get("actions") or []:
        if not isinstance(action, dict):
            continue
        if action.get("type") == "speech":
            text = action.get("text")
            if isinstance(text, str):
                capped = _truncate_to_word_boundary(text, SCENE_SPEECH_MAX_CHARS)
                if len(capped) < len(text):
                    _warn("action.speech.text", len(text), len(capped))
                    action["text"] = capped

    # ── quiz questions ────────────────────────────────────────────────────────
    for question in parsed.get("questions") or []:
        if not isinstance(question, dict):
            continue
        q_text = question.get("text") or question.get("question")
        q_key = "text" if "text" in question else "question"
        if isinstance(q_text, str):
            capped = _truncate_to_word_boundary(q_text, QUIZ_QUESTION_MAX_CHARS)
            if len(capped) < len(q_text):
                _warn("quiz.question_text", len(q_text), len(capped))
                question[q_key] = capped

        # options — may be list of strings or list of dicts with "text"
        for opt in question.get("options") or []:
            if isinstance(opt, str):
                # Can't mutate a list element directly without index — handled below
                pass
            elif isinstance(opt, dict):
                opt_text = opt.get("text")
                if isinstance(opt_text, str):
                    capped = _truncate_to_word_boundary(opt_text, QUIZ_OPTION_MAX_CHARS)
                    if len(capped) < len(opt_text):
                        _warn("quiz.option_text", len(opt_text), len(capped))
                        opt["text"] = capped

        # Handle string-list options (replace in list)
        options = question.get("options")
        if isinstance(options, list):
            new_opts = []
            changed = False
            for opt in options:
                if isinstance(opt, str):
                    capped = _truncate_to_word_boundary(opt, QUIZ_OPTION_MAX_CHARS)
                    if len(capped) < len(opt):
                        _warn("quiz.option_text", len(opt), len(capped))
                        changed = True
                    new_opts.append(capped)
                else:
                    new_opts.append(opt)
            if changed:
                question["options"] = new_opts

    return parsed


# ─── Agent Voice Mapping ─────────────────────────────────────────────────────
#
# Deterministic fallback when the LLM-chosen voice is missing or invalid.
# Keys are the scene-action roles that agents commonly play; values are
# en-IN Azure Neural voice IDs. Only consulted when validate_agents can't
# accept the LLM output and we need a safe default.

# CG-P1-1 (2026-04-27): only references voices Microsoft Edge TTS
# actually serves. AaravNeural/KavyaNeural were fictional (see audit
# in tasks/2026-04-27-deep-end-to-end-fix.md). Hindi-locale Madhur
# substitutes for student_rep/student because no en-IN male voice
# beyond Prabhat exists; Madhur reads English cleanly with a slight
# regional lilt that fits the Indian-school audience.
AGENT_VOICE_MAP = {
    "professor": "en-IN-PrabhatNeural",
    "teaching_assistant": "en-IN-NeerjaNeural",
    "student_rep": "hi-IN-MadhurNeural",
    "student": "hi-IN-MadhurNeural",
    "moderator": "en-IN-NeerjaExpressiveNeural",
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
    """Get the chat completions URL for the configured provider.

    SSRF guard (SEC-P0-3, 2026-04-23): ``config.llm_base_url`` is user-editable
    by SCHOOL_ADMIN. Without validation a malicious admin can point the proxy
    at AWS IMDS (169.254.169.254), local Redis, internal RFC1918 addresses, or
    custom hostnames that resolve to those. ``safe_outbound_url_or_fallback``
    runs scheme + DNS-resolution checks and silently falls back to the
    provider default on rejection (logged).
    """
    from utils.url_safety import safe_outbound_url_or_fallback
    provider_urls = {
        "openai": "https://api.openai.com/v1/chat/completions",
        "openrouter": "https://openrouter.ai/api/v1/chat/completions",
        "anthropic": "https://api.anthropic.com/v1/messages",
        "google": "https://generativelanguage.googleapis.com/v1beta/chat/completions",
    }
    default_url = provider_urls.get(
        config.llm_provider,
        "https://openrouter.ai/api/v1/chat/completions",
    )
    if config.llm_base_url:
        candidate = f"{config.llm_base_url.rstrip('/')}/chat/completions"
        return safe_outbound_url_or_fallback(candidate, default_url)
    return default_url


def _call_llm(config: TenantAIConfig, system_prompt: str, user_prompt: str,
              temperature: float = 0.7, max_tokens: int = 4096,
              caller: str = "unknown") -> str | None:
    """Call the tenant's LLM provider and return text response.

    ``caller`` is a free-form path tag piped into the
    ``maic_llm_call_duration_seconds`` Prometheus histogram so dashboards can
    slice latency by generation phase (e.g. ``"generate_scene_content:lecture"``).
    Defaults to ``"unknown"`` so existing call sites compile, but the
    JSON-retry wrapper threads its own ``caller`` through.
    """
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

    provider = (getattr(config, "llm_provider", None) or "unknown")

    # TEST-P1-10: Wrap the entire HTTP round-trip + parse so timeouts and
    # HTTPErrors still record into the long-tail bucket — that's exactly the
    # signal we want to alert on.
    with time_llm_call(provider=provider, path=caller):
        try:
            resp = http_requests.post(url, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices") or []
            if choices:
                text = choices[0].get("message", {}).get("content", "").strip()
                if text:
                    return text
            logger.warning(
                "LLM returned empty response from %s",
                config.llm_model,
                extra=log_extra(
                    MAICPhase.LLM_CALL,
                    metric="llm_empty_response",
                    outcome="empty",
                    provider=config.llm_provider,
                    model=config.llm_model,
                ),
            )
        except http_requests.HTTPError as e:
            logger.error(
                "LLM HTTP error: %s — %s",
                e.response.status_code if e.response else "?",
                e.response.text[:500] if e.response else str(e),
                extra=log_extra(
                    MAICPhase.LLM_CALL,
                    metric="llm_http_error",
                    outcome="http_error",
                    provider=config.llm_provider,
                    model=config.llm_model,
                    status_code=(e.response.status_code if e.response else None),
                    error_type=type(e).__name__,
                ),
            )
        except Exception as e:
            logger.error(
                "LLM call failed: %s",
                e,
                extra=log_extra(
                    MAICPhase.LLM_CALL,
                    metric="llm_call_failed",
                    outcome="exception",
                    provider=config.llm_provider,
                    model=config.llm_model,
                    error_type=type(e).__name__,
                ),
            )
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
    except Exception as exc:
        logger.warning(
            "Failed to parse LLM JSON output: %s...",
            cleaned[:200],
            extra=log_extra(
                MAICPhase.LLM_CALL,
                metric="llm_json_parse_failed",
                outcome="parse_failed",
                error_type=type(exc).__name__,
            ),
        )
        return None


def _call_llm_with_json_retry(
    config: TenantAIConfig,
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    max_attempts: int = 3,
    validator=None,
    post_process=None,
    context_label: str = "",
    classroom_id: str | None = None,
    caller: str,
) -> tuple[dict | list | None, str | None]:
    """Call the LLM and parse JSON, re-asking on parse failure.

    On JSON-parse failure we re-prompt at a lower temperature (0.2) with a
    continuation prompt that shows the LLM the last ~200 chars of its
    previous broken output and asks it to return ONLY valid JSON with the
    same schema. This covers almost-valid outputs (trailing commas,
    truncation, prose-before-JSON, etc.) that `json_repair` alone cannot
    salvage.

    Parameters
    ----------
    validator : callable, optional
        If provided, called as ``validator(parsed)`` and must return True
        for the attempt to be considered successful. Lets callers reject
        structurally-valid JSON that's missing a required key (e.g.
        ``"slides"`` or ``"actions"``).

        Contract details:
        - The validator receives ONLY the parsed Python object (``dict``,
          ``list``, or a primitive — never ``None``, which is short-circuited
          before this call, and never the raw LLM string).
        - Any exception raised by the validator is caught and treated as a
          failed attempt (same as returning ``False``). This keeps a buggy
          validator from crashing the generation pipeline mid-retry.
    post_process : callable, optional
        If provided, called as ``post_process(parsed)`` **after** successful
        parse and **before** the validator runs. Intended for idempotent
        in-place mutations (e.g. length-budget enforcement via
        ``_enforce_length_budgets``). Any exception raised is swallowed and
        the unprocessed ``parsed`` is passed to the validator instead. The
        callable may mutate ``parsed`` in place and/or return it; the return
        value is used if truthy, otherwise the original ``parsed`` is kept.
    context_label : str
        Short tag used in log messages (e.g. "scene-content"). Helps grep
        retry rates per path in production logs.
    classroom_id : str, optional
        Included in retry log lines when provided, per CG-P0-1 spec, so
        we can correlate retries with a specific classroom generation.
    caller : str
        Stable identifier for the code path that invoked this helper
        (e.g. ``"generate_scene_content:lecture"``). Used as the
        ``path`` field in structured WARN/ERROR log records so ops can
        aggregate retry rates per generation path without grep-ing free
        text. Defaults to ``"unknown"``.

    Returns
    -------
    (parsed, raw_text)
        ``parsed`` is the validated JSON (dict/list) on success, ``None``
        if every attempt failed. ``raw_text`` is the last raw string the
        LLM produced (useful for callers that want to log final failure).
        Both are ``None`` when the LLM itself returned empty on the first
        call (no text to retry against).
    """
    current_temp = temperature
    current_prompt = user_prompt
    last_raw: str | None = None

    for attempt in range(1, max_attempts + 1):
        raw = _call_llm(
            config,
            system_prompt,
            current_prompt,
            temperature=current_temp,
            max_tokens=max_tokens,
            caller=caller,
        )
        if not raw:
            # Empty LLM response — no tail to retry against, and the
            # caller's fallback is the right landing spot. Don't burn
            # more attempts chasing a silent provider.
            if attempt == 1:
                return None, None
            # Subsequent empty: also bail.
            return None, last_raw

        last_raw = raw
        parsed = _parse_json_from_llm(raw)
        # Apply optional post-processing (e.g. length-budget enforcement)
        # BEFORE the validator so schema constraints run on the cleaned output.
        if parsed is not None and post_process is not None:
            try:
                result = post_process(parsed)
                if result is not None:
                    parsed = result
            except Exception:
                pass  # post_process failure is non-fatal; validator decides fate
        validator_ok = True
        if parsed is not None and validator is not None:
            try:
                validator_ok = bool(validator(parsed))
            except Exception:
                validator_ok = False

        if parsed is not None and validator_ok:
            if attempt > 1:
                logger.info(
                    "LLM JSON recovered on attempt %d [%s]%s",
                    attempt,
                    context_label or "llm",
                    f" classroom={classroom_id}" if classroom_id else "",
                )
            return parsed, raw

        # Parse/validation failed — prepare retry.
        if attempt >= max_attempts:
            logger.error(
                "LLM JSON failed after %d attempts — falling back",
                attempt,
                extra=log_extra(
                    MAICPhase.JSON_RETRY,
                    classroom_id,
                    metric="llm_json_retry",
                    path=caller,
                    attempts=attempt,
                    outcome="fallback",
                ),
            )
            return None, raw

        tail = raw[-200:] if raw else ""
        logger.warning(
            "LLM JSON parse failed on attempt %d/%d — retrying at temp=0.2",
            attempt,
            max_attempts,
            extra=log_extra(
                MAICPhase.JSON_RETRY,
                classroom_id,
                metric="llm_json_retry",
                attempt=attempt,
                path=caller,
            ),
        )
        # Lower temperature + explicit continuation prompt biases the LLM
        # toward deterministic, schema-faithful output on the retry. We
        # keep the original system prompt intact so the JSON schema
        # remains the single source of truth for shape.
        current_temp = 0.2
        current_prompt = (
            f"{user_prompt}\n\n"
            "Your previous response was not valid JSON. "
            f"Here are the last 200 characters of what you returned: {tail!r}\n"
            "Please return ONLY valid JSON with the same schema, nothing else. "
            "No prose, no markdown fences, no commentary."
        )

    return None, last_raw


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
    # NOTE: Intentionally retains its own retry loop — the voice-gender
    # auto-fix below (_auto_fix_voice_gender_mismatches) is a mid-attempt
    # repair not modeled by _call_llm_with_json_retry(). Unifying would
    # lose that auto-fix branch. See SPRINT-2-BATCH-1 review 2026-04-24
    # (CG-P0-1-F4).
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


# ─── Audience / Context Guidance ─────────────────────────────────────────────
#
# The wizard passes optional grade_level / subject / syllabus_board /
# audience_role fields. We translate those into concrete prose guidance that
# gets injected into every system prompt so the LLM produces materially
# different content for (say) a Grade 4 reader vs. a Grade 12 reader, and so
# that CBSE/ICSE/IB board conventions nudge vocabulary and scope. Keep each
# helper cheap and deterministic — no LLM calls, no I/O.

_GRADE_BAND_ELEMENTARY = "elementary"
_GRADE_BAND_MIDDLE = "middle"
_GRADE_BAND_HIGH = "high"
_GRADE_BAND_TEACHER = "teacher_cpd"
_GRADE_BAND_GENERIC = "generic"


def _grade_band(grade_level: str) -> str:
    """Map a free-form grade label to one of the coarse bands we tune for.

    Accepts inputs like "Grade 8", "8", "Class VIII", "Teacher CPD", etc.
    Falls back to "generic" when nothing parses — callers rely on this to
    keep existing flows working.
    """
    if not grade_level:
        return _GRADE_BAND_GENERIC
    raw = str(grade_level).strip().lower()
    if not raw:
        return _GRADE_BAND_GENERIC
    if "teacher" in raw or "cpd" in raw or "professional" in raw:
        return _GRADE_BAND_TEACHER
    # Pick the first integer we see, if any.
    digits = ""
    for ch in raw:
        if ch.isdigit():
            digits += ch
        elif digits:
            break
    if digits:
        try:
            n = int(digits)
        except ValueError:
            return _GRADE_BAND_GENERIC
        if 1 <= n <= 5:
            return _GRADE_BAND_ELEMENTARY
        if 6 <= n <= 8:
            return _GRADE_BAND_MIDDLE
        if 9 <= n <= 12:
            return _GRADE_BAND_HIGH
    return _GRADE_BAND_GENERIC


# Guidance text, anchor examples, and register words per band. Kept short so
# the three prompts stay well under the ~2000-token budget.
_BAND_GUIDANCE: dict[str, dict[str, str]] = {
    _GRADE_BAND_ELEMENTARY: {
        "label": "Elementary (Grades 1–5)",
        "register": (
            "Use short, concrete sentences (max ~12 words). Prefer "
            "one- or two-syllable words. Introduce no more than one "
            "equation per concept, and only when unavoidable. Use "
            "concrete analogies grounded in daily life (toys, food, "
            "weather). Avoid domain jargon entirely; if a technical "
            "word appears, give a plain-language definition in the same "
            "sentence. Keep paragraph length to 1–2 sentences."
        ),
        "anchor": (
            "Anchor example (target reading level):\n"
            "  Topic 'Gravity' — write like: 'Gravity is the pull that "
            "keeps us on the ground. It is why a ball falls when you let "
            "it go.'"
        ),
    },
    _GRADE_BAND_MIDDLE: {
        "label": "Middle (Grades 6–8)",
        "register": (
            "Use plain-language explanations with concrete, real-world "
            "examples. Basic algebra and simple equations are OK. Limit "
            "domain vocabulary and always define a term the first time "
            "it appears. Sentences can be moderately complex (15–20 "
            "words); paragraphs 2–4 sentences."
        ),
        "anchor": (
            "Anchor example (target reading level):\n"
            "  Topic 'Gravity' — write like: 'Gravity is the force that "
            "pulls objects toward Earth. Heavier planets pull harder, "
            "which is why you weigh more on Jupiter than on the Moon.'"
        ),
    },
    _GRADE_BAND_HIGH: {
        "label": "High (Grades 9–12)",
        "register": (
            "Use rigorous, age-appropriate formal language and the "
            "standard domain vocabulary. Include precise definitions, "
            "mathematical formulations where they clarify, and common "
            "exam-style reasoning (derivations, cause-and-effect "
            "chains, labelled diagrams). Paragraphs can be 3–5 "
            "sentences; assume the learner can follow multi-step logic."
        ),
        "anchor": (
            "Anchor example (target reading level):\n"
            "  Topic 'Gravity' — write like: 'Gravitational force is "
            "given by F = G·m₁·m₂ / r², where G is the universal "
            "gravitational constant. The inverse-square dependence "
            "explains why orbital period grows with semi-major axis per "
            "Kepler's third law.'"
        ),
    },
    _GRADE_BAND_TEACHER: {
        "label": "Teacher CPD (professional development)",
        "register": (
            "Assume the audience is a practising teacher with domain "
            "expertise. Prioritise pedagogy over re-teaching facts: "
            "assessment strategies, common misconceptions, scaffolding "
            "moves, curriculum alignment, differentiation, and "
            "classroom examples. Technical vocabulary is welcome; skip "
            "basic definitions. Reference formative-assessment "
            "techniques and Bloom-style cognitive demand where useful."
        ),
        "anchor": (
            "Anchor example (target register):\n"
            "  Topic 'Gravity' — write like: 'Learners commonly "
            "conflate mass and weight; surface the distinction with a "
            "weigh-anywhere thought experiment before formalising "
            "F = mg. Pair with an exit-ticket that requires students "
            "to predict weight on the Moon given Earth-weight.'"
        ),
    },
    _GRADE_BAND_GENERIC: {
        "label": "General audience (no grade specified)",
        "register": (
            "Default to a clear, neutral register suitable for a "
            "motivated general learner. Define technical terms the "
            "first time they appear. Prefer concrete examples over "
            "abstractions when introducing a new idea."
        ),
        "anchor": "",
    },
}


_BOARD_GUIDANCE: dict[str, str] = {
    "CBSE": (
        "Follow NCERT scope and sequence. Prefer SI units, NCERT-style "
        "worked examples, and the terminology used in NCERT textbooks."
    ),
    "ICSE": (
        "Follow CISCE / ICSE syllabus conventions. Favour structured "
        "definitions, stepwise derivations, and the ICSE exam answer "
        "pattern (state · explain · illustrate)."
    ),
    "IB": (
        "Align with IB DP / MYP command terms (define, describe, "
        "explain, evaluate, justify). Use TOK-aware framing where "
        "natural, and prefer IB-style data-response examples."
    ),
    "CambridgeIGCSE": (
        "Align with Cambridge IGCSE syllabus and command terms. Prefer "
        "SI units and Cambridge-style mark-scheme phrasing ('state', "
        "'describe', 'explain')."
    ),
    "State": (
        "Follow a generic Indian State Board convention: keep examples "
        "locally relevant and vocabulary accessible; avoid assuming "
        "board-specific advanced topics."
    ),
    "Generic": (
        "No specific board — use widely-accepted conventions and SI "
        "units; avoid board-specific jargon."
    ),
}


def _normalize_board(syllabus_board: str) -> str:
    """Return a canonical board key or 'Generic' when unrecognized."""
    if not syllabus_board:
        return "Generic"
    raw = str(syllabus_board).strip()
    # Case-insensitive match against known keys.
    for key in _BOARD_GUIDANCE:
        if raw.lower() == key.lower():
            return key
    # A few common aliases.
    low = raw.lower().replace(" ", "")
    if low in {"igcse", "cambridge", "cambridgeigcse"}:
        return "CambridgeIGCSE"
    if low in {"stateboard", "state"}:
        return "State"
    return "Generic"


def _subject_guidance(subject: str) -> str:
    """Subject-specific guardrails. Free-form subject; we pattern-match a few
    common ones and fall back to a generic line that still mentions the
    subject name so it shows up in the prompt."""
    if not subject:
        return ""
    s = str(subject).strip()
    if not s:
        return ""
    low = s.lower()
    if "phys" in low:
        return (
            f"In {s}, use SI units; state assumptions (ideal gas, "
            "frictionless, point mass, etc.) before deriving equations; "
            "draw free-body diagrams when forces are discussed."
        )
    if "chem" in low:
        return (
            f"In {s}, balance all equations; include state symbols "
            "(s, l, g, aq); use IUPAC names on first mention."
        )
    if "bio" in low:
        return (
            f"In {s}, use italics for scientific names (Genus species), "
            "label diagrams clearly, and distinguish structure from "
            "function in every explanation."
        )
    if "math" in low or "algebra" in low or "geom" in low or "calc" in low:
        return (
            f"In {s}, show every non-trivial step; state the theorem or "
            "identity being applied; keep variables and constants "
            "consistently typeset."
        )
    if "english" in low or "literature" in low or "language" in low:
        return (
            f"In {s}, quote the text exactly, cite line/paragraph "
            "references when possible, and distinguish literal meaning "
            "from interpretation."
        )
    if "history" in low or "civic" in low or "social" in low:
        return (
            f"In {s}, anchor claims to dates and places; separate primary "
            "evidence from interpretation; name sources when asserting "
            "causation."
        )
    if "computer" in low or "cs" in low or "program" in low:
        return (
            f"In {s}, include runnable code snippets with consistent "
            "indentation; state time/space complexity where relevant; "
            "prefer pseudocode when teaching an algorithm before the "
            "language-specific implementation."
        )
    return f"Subject is {s}: use vocabulary and examples appropriate to this subject."


def _audience_preamble(audience_role: str) -> str:
    """One-line opening that flips content from learner-facing to teacher-CPD
    when the authenticated user is a teacher generating PD material."""
    if (audience_role or "").strip().lower() == "teacher":
        return (
            "AUDIENCE: practising teachers (professional development). "
            "Centre pedagogy, assessment design, and classroom moves — "
            "not remedial instruction."
        )
    return "AUDIENCE: students in the indicated grade band."


def _context_block(grade_level: str, subject: str, syllabus_board: str,
                   audience_role: str) -> str:
    """Compose the CONTEXT preamble injected at the top of every system
    prompt. Ordering matters: audience → grade band → subject → board → anchor
    example. Keep the label lines terse; LLMs pattern-match on them."""
    band = _grade_band(grade_level)
    band_info = _BAND_GUIDANCE[band]
    board = _normalize_board(syllabus_board)
    lines = [
        "=== AUDIENCE & CONTEXT ===",
        _audience_preamble(audience_role),
        f"Grade level: {grade_level or '(unspecified)'} — band: {band_info['label']}.",
        f"Register guidance: {band_info['register']}",
    ]
    subj_line = _subject_guidance(subject)
    if subj_line:
        lines.append(f"Subject guidance: {subj_line}")
    lines.append(f"Syllabus board: {board} — {_BOARD_GUIDANCE[board]}")
    if band_info["anchor"]:
        lines.append(band_info["anchor"])
    lines.append("=== END CONTEXT ===")
    return "\n".join(lines)


# ─── Outline Generation ──────────────────────────────────────────────────────

_OUTLINE_BODY = """You are an expert educational content designer creating a multi-agent interactive classroom.

You will receive a pre-configured agent roster. Do NOT invent new agents. Use the exact `id`s from the roster when assigning agents to scenes.

Return a valid JSON object:
{
  "scenes": [
    {
      "id": "scene-1",
      "title": "Scene title",
      "description": "Brief description of what this scene covers",
      "type": "introduction|lecture|discussion|quiz|activity|pbl|case_study|interactive|summary",
      "estimatedMinutes": 3,
      "agentIds": ["agent-1", "agent-2"],
      "slideCount": 6,
      "questionCount": 0,
      "teachingObjective": "By the end of this scene, students will be able to <verb> <specific concept>",
      "keyPoints": [
        "First substantive point the scene must cover (≤25 words, concrete & specific)",
        "Second point",
        "Third point",
        "Fourth point (optional, 4-5 if topic warrants)"
      ]
    }
  ],
  "totalMinutes": 20
}

Rules:
- Scene titles, descriptions, and the overall pacing MUST match the AUDIENCE & CONTEXT block above — vocabulary, depth, and examples should shift with the grade band and subject.
- `teachingObjective` is REQUIRED for every scene. Use a measurable Bloom's-taxonomy verb (define, explain, analyze, derive, compare, design, evaluate). One sentence, ≤30 words. Example: "Students will be able to derive Newton's second law from a free-body diagram."
- `keyPoints` is REQUIRED for every scene with type lecture|discussion|introduction|summary|activity|pbl|case_study. List 3-5 specific, substantive points the scene MUST cover. NOT generic ("understand the topic") — concrete claims, formulas, examples, or comparisons. These are the substance the slide-content step expands into slides.
- For `quiz` scenes: omit `keyPoints` (questionCount drives output instead).
- For `interactive` scenes: still include `keyPoints` (1-2 are fine) — they describe what the widget should let the student manipulate.
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
- For "interactive" scenes: set "slideCount" to 1 (the interactive HTML widget IS the scene — no flat slides). Use sparingly: at most ONE per classroom, and only when the topic benefits from hands-on exploration (e.g., a physics simulation, a flowchart the student can step through, a calculator / visualizer).
- Use agentIds ONLY from the provided roster — never invent new ids."""


def build_outline_system_prompt(grade_level: str = "", subject: str = "",
                                syllabus_board: str = "Generic",
                                audience_role: str = "student") -> str:
    """Compose the outline system prompt, with a context preamble tailored
    to the grade band, subject, board, and audience. Defaults mean callers
    that don't pass any context get near-identical behavior to the pre-
    refactor prompt."""
    return f"{_context_block(grade_level, subject, syllabus_board, audience_role)}\n\n{_OUTLINE_BODY}"


# Back-compat: some call sites / tests may still import this constant.
# Kept as the generic-audience rendering so legacy behavior is preserved.
OUTLINE_SYSTEM_PROMPT = build_outline_system_prompt()


def generate_outline_sse(topic: str, language: str, agents: list[dict],
                         scene_count: int, pdf_text: str | None,
                         config: TenantAIConfig,
                         grade_level: str = "",
                         subject: str = "",
                         syllabus_board: str = "Generic",
                         audience_role: str = "student"):
    """
    Generator that yields SSE-formatted strings for outline streaming.
    Used as the body of a StreamingHttpResponse.

    ``agents`` is the authoritative roster produced by ``generate_agent_profiles_json``
    (or a teacher-edited variant). The outline prompt no longer invents agents;
    it assigns the supplied agent ids to scenes only.

    The ``grade_level`` / ``subject`` / ``syllabus_board`` / ``audience_role``
    args are threaded through to the system-prompt builder so the same topic
    asked by an 8th grader vs. a 12th grader produces visibly different
    content. All four default to values that reproduce the pre-refactor
    (generic-audience) behavior so existing wizard flows keep working.
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
    )
    # Echo the structured context into the user prompt too — belt-and-braces
    # so the LLM doesn't drift past the system preamble when the outline
    # body is long. Cheap to include; big win for adherence.
    if grade_level:
        user_prompt += f"\nGrade level: {grade_level}"
    if subject:
        user_prompt += f"\nSubject: {subject}"
    if syllabus_board and syllabus_board != "Generic":
        user_prompt += f"\nSyllabus board: {syllabus_board}"
    if audience_role:
        user_prompt += f"\nAudience: {audience_role}"
    user_prompt += (
        "\n\nAgent roster (use these ids when assigning agents to scenes):\n"
        f"{json.dumps(agent_roster_for_prompt, indent=2)}\n"
    )
    if pdf_text:
        excerpt = pdf_text[:15000]
        user_prompt += f"\nReference material (excerpt):\n{excerpt}\n"

    # Send a progress event first
    yield _sse_event("generation_progress", {"progress": 10})

    system_prompt = build_outline_system_prompt(
        grade_level=grade_level,
        subject=subject,
        syllabus_board=syllabus_board,
        audience_role=audience_role,
    )

    # Call LLM. CG-P0-7: 4096 → 6144 so 9-12 scene outlines with the new
    # `keyPoints` / `teachingObjective` fields don't overflow.
    raw = _call_llm(config, system_prompt, user_prompt, temperature=0.7, max_tokens=6144)

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

_SCENE_CONTENT_BODY = """You are an expert educational content designer creating rich, visually appealing multi-slide presentations for an interactive AI classroom.

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
- **EVERY slide MUST include EXACTLY ONE image element.** No slide may be text-only. The image element's `content` field is the KEYWORD passed to the image generator — it MUST be a concrete, topic-relevant phrase describing what the image should depict (e.g. for a Geometry scene: "Diagram of a right triangle with labeled angles and hypotenuse" — NOT generic words like "education", "classroom", or "diagram").
- Image placement: for title slides use full-width (x=100, y=200, width=600, height=260); for text-with-image slides place the image at the right side (x=460, y=90, width=300, height=240) and keep text elements on the left (x=40, width=400).
- Leave `src: ""` on every image element — the backend fills real URLs via the image generation pipeline post-return.
- Use \\n\\n for paragraph breaks in bullet content (NOT just \\n)
- Heading: bold, 28-36px, dark color (#1E293B)
- Body: 16-20px, readable color (#334155)
- Takeaway/highlight: distinctive color (#0F766E), smaller font
- Speaker script MUST be 3-5 sentences per slide, written in first person as the presenting agent
- Speaker script should add context BEYOND what is on the slide (do not just read the bullets)
- For introduction scenes: the speaker script should introduce the agent and preview the lesson
- Duration should be 30-60 seconds per slide
- Vary the background colors subtly: #FFFFFF, #F8FAFC, #F1F5F9, #FFFBEB for visual interest
- Slide bullet text, speaker script vocabulary, and worked-example depth MUST reflect the AUDIENCE & CONTEXT block above. A Grade 4 slide on the same topic should read visibly different from a Grade 12 slide: shorter sentences, simpler vocabulary, fewer/ no equations.
- Quiz question difficulty and distractor plausibility MUST also track the grade band — elementary quizzes stay factual and concrete; high-school quizzes can require multi-step reasoning and computation.

HARD LENGTH BUDGETS (reject-if-exceeded — the renderer overflows otherwise):
- Title text: ≤ 60 characters (single line at 28-36px).
- Subtitle text: ≤ 90 characters (single line at 16-18px).
- Bullet item: ≤ 90 characters each. Max 4 bullets per text block.
- Key-takeaway text: ≤ 100 characters.
- speakerScript: 2-4 sentences, ≤ 280 characters total.

STRICT NO-OVERLAP LAYOUT (this is what was breaking the player: images and text rectangles were sharing pixels and occluding each other):
- Before emitting a slide, verify every element's bounding box (x, y, x+width, y+height) does NOT overlap any other element's bounding box. They may touch edges but must not overlap interior pixels.
- Reserve a 20-pixel gutter between any image and any text rectangle on the same slide.
- Use the following SAFE ZONES for multi-element slides on the 800x450 canvas:
  * Title region: x=40, y=20, width=720, height=60 (single-line heading only).
  * Left text column: x=40, y=100, width=360, height=300.
  * Right image column: x=420, y=100, width=340, height=240.
  * Footer takeaway: x=40, y=400, width=720, height=40.
- For single-focus slides (title slide, diagram-only slide), center one element with 40px margins.
- NEVER place any text rectangle where the image rectangle sits; NEVER place the image rectangle on top of the title.

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


def build_scene_content_system_prompt(grade_level: str = "",
                                      subject: str = "",
                                      syllabus_board: str = "Generic",
                                      audience_role: str = "student") -> str:
    """Compose the scene-content system prompt with an audience/grade/board
    preamble. Defaults preserve pre-refactor behavior for callers that don't
    thread the new params through."""
    return f"{_context_block(grade_level, subject, syllabus_board, audience_role)}\n\n{_SCENE_CONTENT_BODY}"


# Back-compat constant.
SCENE_CONTENT_SYSTEM_PROMPT = build_scene_content_system_prompt()


def _fill_image_urls(parsed: dict, scene_id: str, *,
                     image_provider: str = "disabled",
                     tenant_id: str | None = None,
                     classroom_id: str | None = None,
                     scene_idx: int | None = None) -> dict:
    """Post-process slides to fill in image URLs using image_service.

    When `image_provider == 'disabled'`, skip the fetch entirely and stamp
    `meta.imageProviderDisabled = true` on each image element so the
    frontend renders an honest "AI images off" placeholder rather than a
    random Unsplash photo. Any fetch error is logged (not silenced) so
    ops can see what providers are failing.

    CG-P0-9: when ``tenant_id`` + ``classroom_id`` + ``scene_idx`` are all
    provided, ``fetch_scene_image`` will save Imagen/Nano-Banana bytes to
    ``default_storage`` (real /media URL) instead of returning a base64
    ``data:`` URL that the frontend strips. Per-slide ``slide_idx`` is
    appended into the storage path so multi-slide scenes don't collide.
    """
    from apps.courses.image_service import fetch_scene_image

    disabled = (image_provider or "disabled").lower() == "disabled"
    slides = parsed.get("slides", [])
    have_storage_ctx = bool(tenant_id and classroom_id and scene_idx is not None)
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
                if have_storage_ctx:
                    # Compose a unique scene_index per (scene_idx, slide_idx)
                    # so multiple images in the same scene don't overwrite
                    # each other in storage. 100 slides per scene is far
                    # beyond anything we generate so the multiplier is safe.
                    composite_idx = (scene_idx * 100) + slide_idx
                    url = fetch_scene_image(
                        keyword,
                        tenant_id=tenant_id,
                        lesson_id=classroom_id,
                        scene_index=composite_idx,
                    )
                else:
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


SCENE_INTERACTIVE_SYSTEM_PROMPT = """You are an expert educational content designer creating a self-contained HTML simulation for a classroom scene.

Return a valid JSON object of shape:
{
  "html": "<!doctype html>...full standalone HTML document..."
}

Rules for the HTML:
- MUST be a single, self-contained HTML document — inline <style> and <script> only, no external URLs, no <script src>, no <link rel>, no @import, no network fetch() calls.
- MUST work in a sandboxed iframe with `sandbox="allow-scripts"` (so NO access to localStorage, cookies, same-origin APIs, top.location, etc.).
- Keep total size under 12 KB.
- Centered, responsive layout; works inside a 16:9 container at any width. No fixed pixel dimensions that break under 640px wide.
- Educational: an interactive widget the student can actually manipulate — a slider-driven visualization, a clickable diagram, a simple calculator, a step-through flowchart, etc. — directly related to the scene topic.
- Include a visible title and a one-line instruction at the top.
- Accessible: use semantic elements, label controls, keyboard-reachable.
- No tracking, no analytics, no remote resources of any kind."""


def generate_scene_content(scene: dict, agents: list, language: str,
                           config: TenantAIConfig,
                           grade_level: str = "",
                           subject: str = "",
                           syllabus_board: str = "Generic",
                           audience_role: str = "student",
                           classroom_id: str | None = None,
                           tenant_id: str | None = None,
                           scene_idx: int | None = None) -> dict | None:
    """Generate multi-slide content for a single scene. Returns parsed dict with 'slides' array.

    ``grade_level`` / ``subject`` / ``syllabus_board`` / ``audience_role``
    tune the system prompt so the same scene title produces different prose
    for different audiences. Defaults preserve existing behavior.

    ``classroom_id`` is the UUID of the parent MAICClassroom (when available
    from the caller). It is only used in the retry-log field so ops can
    grep retries back to a specific classroom. Optional — pass ``None`` if
    the caller is an ad-hoc generation path with no stable classroom id.

    ``tenant_id`` + ``classroom_id`` + ``scene_idx`` (CG-P0-9): when ALL three
    are present, the inline ``_fill_image_urls`` call has the storage
    context it needs to save Imagen bytes to ``default_storage`` and return
    a real ``/media/...`` URL. Without them, Imagen returns a base64
    ``data:`` URL that the frontend's ``scrubSlideDataUrls`` strips —
    leaving every slide image broken.
    """
    scene_type = scene.get("type", "lecture")
    scene_id = scene.get("id", "scene-1")
    slide_count = max(3, min(12, scene.get("slideCount", 6)))
    question_count = max(2, min(8, scene.get("questionCount", 4)))

    if scene_type == "interactive":
        assigned_names = json.dumps(
            [a["name"] for a in agents if a["id"] in scene.get("agentIds", [])]
        )
        user_prompt = (
            f"Generate an interactive HTML simulation for this classroom scene:\n\n"
            f"Scene title: {scene['title']}\n"
            f"Scene description: {scene.get('description', '')}\n"
            f"Language: {language}\n"
            f"Assigned agents: {assigned_names}\n\n"
            "Produce a single JSON object with an `html` field containing a "
            "complete self-contained HTML document that teaches the topic "
            "through direct manipulation (slider, clickable elements, "
            "step-through, etc.). No external resources."
        )
        parsed, _raw = _call_llm_with_json_retry(
            config, SCENE_INTERACTIVE_SYSTEM_PROMPT, user_prompt,
            temperature=0.5, max_tokens=6144,
            validator=lambda p: isinstance(p, dict) and bool(p.get("html")),
            post_process=lambda p: _enforce_length_budgets(p, "interactive"),
            context_label="scene-interactive",
            classroom_id=classroom_id,
            # SPRINT-2-BATCH-8-F9: pinned LLMCallPath value.
            caller="scene_content_interactive",
        )
        if not parsed or not isinstance(parsed, dict) or not parsed.get("html"):
            # TEST-P1-10: interactive LLM bailed → deterministic fallback.
            maic_scene_generation_total.labels(
                scene_type="interactive", outcome="fallback"
            ).inc()
            return _fallback_interactive_scene(scene)
        html = str(parsed["html"])
        # Trivial containment: strip any <script src= / <link rel= / fetch(
        # smells that would bypass the iframe sandbox or phone home. This is
        # belt-and-suspenders — the sandbox already blocks network, but
        # dropping the strings keeps the markup honest.
        for bad in ("<script src=", "<link rel=\"stylesheet\"",
                    "<link rel='stylesheet'"):
            if bad.lower() in html.lower():
                # Sandbox-violating tag detected → also a fallback exit.
                maic_scene_generation_total.labels(
                    scene_type="interactive", outcome="fallback"
                ).inc()
                return _fallback_interactive_scene(scene)
        maic_scene_generation_total.labels(
            scene_type="interactive", outcome="ok"
        ).inc()
        return {"type": "interactive", "html": html, "slides": []}

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

Generate exactly {slide_count} slides following the layout guidelines (title slide, content slides with images, diagram slide, deep dive, key concepts, transition). EVERY slide MUST have exactly one image element with a concrete topic-relevant keyword in its `content` field. Each slide must have a unique speakerScript.
"""

    # Echo the grade/subject/board/audience into the user prompt so the
    # LLM can't ignore the system preamble when the scene body is long.
    ctx_lines = []
    if grade_level:
        ctx_lines.append(f"Grade level: {grade_level}")
    if subject:
        ctx_lines.append(f"Subject: {subject}")
    if syllabus_board and syllabus_board != "Generic":
        ctx_lines.append(f"Syllabus board: {syllabus_board}")
    if audience_role:
        ctx_lines.append(f"Audience: {audience_role}")
    if ctx_lines:
        user_prompt += "\nContext:\n" + "\n".join(f"  - {line}" for line in ctx_lines) + "\n"

    # CG-P0-7 (2026-04-27): inject the outline-committed substance
    # (`teachingObjective` + `keyPoints`) so the slide-content LLM call
    # expands an anchored lesson plan instead of re-deriving the topic.
    # This is the OpenMAIC outline→content pipeline pattern: outline
    # commits the substance, scene-content expands it. Without these,
    # slides drift off-topic and feel generic. Both fields are optional
    # for backward compat — pre-CG-P0-7 outlines without them still work.
    teaching_objective = (scene.get("teachingObjective") or "").strip()
    key_points = scene.get("keyPoints") or []
    substance_lines = []
    if teaching_objective:
        substance_lines.append(f"Teaching objective: {teaching_objective}")
    if isinstance(key_points, list) and key_points:
        substance_lines.append("Key points the slides MUST cover:")
        for kp in key_points:
            kp_str = str(kp).strip()
            if kp_str:
                substance_lines.append(f"  - {kp_str}")
    if substance_lines:
        user_prompt += "\nLesson substance (anchor — do NOT drift from these):\n" + "\n".join(substance_lines) + "\n"

    scene_system_prompt = build_scene_content_system_prompt(
        grade_level=grade_level,
        subject=subject,
        syllabus_board=syllabus_board,
        audience_role=audience_role,
    )
    # Pick the validator for the shape the current branch actually needs:
    # quiz scenes must contain "questions"; lecture/other scenes must
    # contain "slides" (or the legacy "slide" single-slide form). Both
    # accept dicts with the right key so genuine schema drift (e.g. the
    # LLM returning `{"text": "..."}` with no keys we use) now triggers
    # a retry rather than being silently accepted.
    if scene_type == "quiz":
        def _scene_content_validator(p):
            return isinstance(p, dict) and "questions" in p
    else:
        def _scene_content_validator(p):
            return isinstance(p, dict) and ("slides" in p or "slide" in p)

    parsed, _raw = _call_llm_with_json_retry(
        config, scene_system_prompt, user_prompt,
        # CG-P0-7: 8192 → 12288. Lecture scenes with 6+ slides + speakerScript
        # were getting truncated mid-slide; raised to give the LLM room to
        # finish a full lesson without OpenMAIC-style follow-ups.
        temperature=0.6, max_tokens=12288,
        validator=_scene_content_validator,
        post_process=lambda p: _enforce_length_budgets(p, scene_type),
        context_label="scene-content",
        classroom_id=classroom_id,
        # SPRINT-2-BATCH-8-F9: pin the path label to the LLMCallPath
        # Literal — clamp scene_type to {lecture,quiz} for the JSON-content
        # branch (the interactive branch uses its own caller above).
        # Anything else is silently bucketed as `scene_content_lecture`
        # to keep Prometheus label cardinality bounded.
        caller=(
            "scene_content_quiz" if scene_type == "quiz"
            else "scene_content_lecture"
        ),
    )
    image_provider = getattr(config, "image_provider", "disabled") or "disabled"
    if not parsed or not isinstance(parsed, dict):
        # TEST-P1-10: LLM exhausted retries / returned junk → deterministic
        # fallback content. Counter helps spot a regression in retry success.
        maic_scene_generation_total.labels(
            scene_type=scene_type, outcome="fallback"
        ).inc()
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
            # Guarantee every slide has an image element — the prompt
            # asks for one per slide, but LLMs sometimes skip. Synthesize
            # a placeholder image element using the slide title as the
            # image keyword; _fill_image_urls will fetch a real URL.
            _ensure_slide_has_image(slide, scene_title=scene.get("title", ""), slide_idx=i)
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
        _ensure_slide_has_image(slide, scene_title=scene.get("title", ""), slide_idx=0)
        parsed["slides"] = [slide]

    _fill_image_urls(
        parsed,
        scene_id,
        image_provider=image_provider,
        tenant_id=tenant_id,
        classroom_id=classroom_id,
        scene_idx=scene_idx,
    )
    # Post-gen layout fix: auto-resolve overlapping element rectangles that
    # the LLM still produces despite the STRICT NO-OVERLAP guidance in the
    # prompt. Mutates slides in place so the renderer receives a clean set.
    _fix_overlapping_elements(parsed.get("slides", []))
    # TEST-P1-10: clean LLM output → success.
    maic_scene_generation_total.labels(
        scene_type=scene_type, outcome="ok"
    ).inc()
    return parsed


def _fix_overlapping_elements(slides: list) -> None:
    """Detect and repair element rectangles that overlap on a slide.

    The renderer positions every element absolutely on an 800x450 canvas,
    so any two rects sharing pixels produces the "image on top of title"
    bug seen in the AI Classroom. Strategy:
      1. Sort elements by a "lock priority" — title text and body text
         keep their original bounds; images and shapes get moved.
      2. For each movable element whose rect overlaps a locked rect,
         push it down into the next free horizontal band, or shrink
         its height if no free band exists.
    Idempotent; safe to run multiple times on the same slide.
    """
    CANVAS_W, CANVAS_H = 800, 450
    GUTTER = 12  # pixels between any two rects

    def rects_overlap(a: dict, b: dict) -> bool:
        ax, ay = a.get("x", 0), a.get("y", 0)
        aw, ah = a.get("width", 0), a.get("height", 0)
        bx, by = b.get("x", 0), b.get("y", 0)
        bw, bh = b.get("width", 0), b.get("height", 0)
        return not (
            ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay
        )

    for slide in slides:
        elements = slide.get("elements") or []
        if len(elements) < 2:
            continue
        # Text and latex elements hold their position (readability wins);
        # images, shapes, charts, videos, and code blocks are movable.
        def is_locked(el: dict) -> bool:
            return el.get("type") in ("text", "latex")
        locked = [el for el in elements if is_locked(el)]
        movable = [el for el in elements if not is_locked(el)]
        for el in movable:
            # If this element overlaps any locked element, push it below
            # the lowest overlapping locked rect, clamped to canvas.
            for loc in locked:
                if not rects_overlap(el, loc):
                    continue
                new_y = loc.get("y", 0) + loc.get("height", 0) + GUTTER
                if new_y + el.get("height", 0) > CANVAS_H:
                    # Shrink to fit bottom region with min 60px height
                    new_y = max(0, CANVAS_H - el.get("height", 60) - 10)
                el["y"] = new_y
            # Clamp to canvas
            if el.get("x", 0) + el.get("width", 0) > CANVAS_W:
                el["x"] = max(0, CANVAS_W - el.get("width", 0))
            if el.get("y", 0) + el.get("height", 0) > CANVAS_H:
                el["height"] = max(60, CANVAS_H - el.get("y", 0) - 10)


def _ensure_slide_has_image(slide: dict, *, scene_title: str, slide_idx: int) -> None:
    """Guarantee the slide has at least one image element.

    Called after the LLM response is parsed. If the LLM produced a
    text-only slide (ignoring the prompt's "every slide must have an
    image" rule), synthesize a well-positioned image element with a
    topic-derived keyword so the image pipeline can fetch a real URL.
    Mutates `slide['elements']` in place.
    """
    elements = slide.get("elements", [])
    has_image = any(
        isinstance(el, dict) and el.get("type") == "image"
        for el in elements
    )
    if has_image:
        return

    # Derive a keyword from the slide title + scene title so the image is
    # at least topically anchored rather than generic.
    slide_title = str(slide.get("title") or "").strip()
    keyword_parts = [p for p in [slide_title, scene_title] if p]
    keyword = " — ".join(keyword_parts) or "educational illustration"
    # Keep the keyword bounded so the image endpoint URL doesn't bloat.
    keyword = f"Educational illustration: {keyword[:120]}"

    synthesized = {
        "type": "image",
        "id": f"el-s{slide_idx + 1}-img-auto",
        # Right-half layout — non-destructive for existing text elements
        # on the left.
        "x": 460, "y": 90, "width": 300, "height": 240,
        "content": keyword,
        "src": "",
    }
    elements.append(synthesized)
    slide["elements"] = elements


def _fallback_interactive_scene(scene: dict) -> dict:
    """Deterministic fallback when the LLM can't produce a safe interactive
    HTML payload. Returns a minimal self-contained widget that at least
    reflects the scene title so the student sees something coherent
    rather than a blank iframe.
    """
    title = str(scene.get("title") or "Interactive activity")
    description = str(scene.get("description") or "")
    # Keep this tiny and static — no scripts needed.
    safe_title = title.replace("<", "&lt;").replace(">", "&gt;")
    safe_desc = description.replace("<", "&lt;").replace(">", "&gt;")
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<style>"
        "html,body{margin:0;height:100%;font-family:system-ui,sans-serif;"
        "background:#f8fafc;color:#0f172a;display:flex;align-items:center;"
        "justify-content:center;padding:24px}"
        ".card{max-width:560px;text-align:center}"
        "h1{font-size:20px;margin:0 0 8px}p{margin:0;color:#475569;line-height:1.5}"
        "</style></head><body>"
        f"<div class='card'><h1>{safe_title}</h1><p>{safe_desc}</p>"
        "<p style='margin-top:12px;font-size:12px;color:#94a3b8'>"
        "Interactive content is being prepared.</p></div></body></html>"
    )
    return {"type": "interactive", "html": html, "slides": []}


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

_ACTIONS_BODY = """You are an expert director choreographing a multi-agent interactive classroom. Your job is to create a dynamic, engaging sequence where MULTIPLE agents teach together across MULTIPLE SLIDES — like a real classroom with a professor and teaching assistants.

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

ACTION TYPES (15 types — use all of these for maximum engagement):

1. speech       — Agent speaks (requires: agentId, text). 1-3 sentences each.
2. spotlight    — Highlight element glow (requires: elementId, duration in ms)
3. highlight    — Color overlay on element (requires: elementId, color hex like "#DBEAFE")
4. pause        — Dramatic pause (requires: duration in ms, 500-1500)
5. transition   — Advance to next slide (requires: slideIndex — 0-based index of the target slide). CRITICAL for multi-slide scenes.
6. wb_open      — Open whiteboard overlay (no params)
7. wb_draw_text — Draw text on whiteboard (requires: text, x, y, fontSize, color)
8. wb_draw_shape— Draw shape on whiteboard (requires: shape ["circle"|"rect"|"arrow"], x, y, width, height, color)
9. wb_draw_line — Draw line on whiteboard (requires: x1, y1, x2, y2, color, strokeWidth)
10. wb_draw_latex — Draw a LaTeX equation on the whiteboard (requires: id, latex, left, top, width, fontSize). Use for formulas, derivations.
11. wb_draw_code  — Seed a code block on the whiteboard (requires: id, lines, left, top, width; optional: language, fontSize). Lines can be empty to seed a block the agent then fills via wb_edit_code.
12. wb_edit_code  — Mutate an existing code block (requires: targetId matching a prior wb_draw_code id, operation ["insert_after"|"replace_lines"|"delete_lines"], lineStart, optional lineEnd, optional content[]). Use to make code appear a few lines at a time, interleaved with speech, so the agent is "typing" the code live.
13. wb_close    — Close whiteboard overlay (no params)
14. wb_clear    — Clear whiteboard content (no params)
15. discussion  — Start discussion segment (requires: sessionType ["qa"|"roundtable"], topic, agentIds)

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
- Use WHITEBOARD at least once per scene for formulas, diagrams, or key concepts.
  NARRATED DRAWING: decompose a whiteboard explanation into SHORT alternating steps — one draw action, then one speech action referencing what just appeared, then the next draw. Do NOT emit one large draw followed by one large speech. Example rhythm for a formula:
    wb_open
    wb_draw_latex (the left-hand side)
    speech ("Start from the left-hand side — mass times acceleration…")
    wb_draw_latex (the right-hand side)
    speech ("…equals the net force acting on the body.")
    wb_close
  For code walkthroughs, prefer wb_draw_code (seed) + a sequence of wb_edit_code inserts so the code appears a few lines at a time, each chunk narrated by a brief speech action. That produces the "typing code live" feel.
- Discussion segments: if you include a "discussion" action, set `"triggerMode": "manual"` so the panel only opens when the teacher clicks the Roundtable button. Never rely on discussions auto-popping mid-scene.
- Speech text should feel like a real conversation, not reading from notes
- Each speech should be 1-3 sentences (short, punchy, conversational)
- Use the speaker's role style: professors explain authoritatively, assistants ask clarifying questions, student reps voice common confusions
- Spotlight the heading element first, then key content elements on each slide
- Speaker handoff: optionally insert ONE `{"type":"pause","duration": 80}` action between speakers — the engine caps pauses to 100ms anyway and a 0-80ms beat reads as natural breath, while anything larger compounds with audio decode latency into noticeable dead air. Do NOT add pauses between same-speaker turns; natural TTS cadence covers it.
- For introduction scenes: each agent introduces themselves personally
- Use element IDs from the slide content for spotlight/highlight actions
- End with a strong summary or transition statement
- The action flow should follow the slide order: discuss slide 0, transition to 1, discuss 1, transition to 2, etc.
- SPEECH REGISTER MUST TRACK AUDIENCE: the AUDIENCE & CONTEXT block above dictates vocabulary, sentence length, and analogy complexity for every speech line. Dialogue for Grade 4 should use short, concrete sentences and familiar analogies; dialogue for Grade 12 can use formal domain vocabulary, definitions, and multi-clause reasoning. Teacher-CPD dialogue should foreground pedagogy (misconceptions, formative checks, scaffolding) rather than re-teaching the topic."""


def build_actions_system_prompt(grade_level: str = "", subject: str = "",
                                syllabus_board: str = "Generic",
                                audience_role: str = "student") -> str:
    """Compose the actions/director system prompt with a context preamble.
    Defaults preserve the pre-refactor (generic-audience) behavior."""
    return f"{_context_block(grade_level, subject, syllabus_board, audience_role)}\n\n{_ACTIONS_BODY}"


# Back-compat constant.
ACTIONS_SYSTEM_PROMPT = build_actions_system_prompt()


def generate_scene_actions(scene: dict, agents: list, language: str,
                           config: TenantAIConfig,
                           grade_level: str = "",
                           subject: str = "",
                           syllabus_board: str = "Generic",
                           audience_role: str = "student",
                           classroom_id: str | None = None) -> dict | None:
    """Generate rich playback actions for a multi-slide scene. Returns parsed dict.

    Context params tune register/vocabulary of generated dialogue. Defaults
    preserve pre-refactor behavior.

    ``classroom_id`` is threaded into the retry log field so ops can
    correlate retry rates with a specific MAICClassroom. Optional.
    """
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

    ctx_lines = []
    if grade_level:
        ctx_lines.append(f"Grade level: {grade_level}")
    if subject:
        ctx_lines.append(f"Subject: {subject}")
    if syllabus_board and syllabus_board != "Generic":
        ctx_lines.append(f"Syllabus board: {syllabus_board}")
    if audience_role:
        ctx_lines.append(f"Audience: {audience_role}")
    if ctx_lines:
        user_prompt += "\nContext:\n" + "\n".join(f"  - {line}" for line in ctx_lines) + "\n"

    actions_system_prompt = build_actions_system_prompt(
        grade_level=grade_level,
        subject=subject,
        syllabus_board=syllabus_board,
        audience_role=audience_role,
    )
    parsed, _raw = _call_llm_with_json_retry(
        config, actions_system_prompt, user_prompt,
        temperature=0.5, max_tokens=4096,
        validator=lambda p: isinstance(p, dict) and "actions" in p,
        post_process=lambda p: _enforce_length_budgets(p, "scene_actions"),
        context_label="scene-actions",
        classroom_id=classroom_id,
        caller="generate_scene_actions",
    )
    if not parsed or not isinstance(parsed, dict) or "actions" not in parsed:
        # TEST-P1-10: LLM bailed on actions → deterministic fallback.
        maic_scene_generation_total.labels(
            scene_type="scene_actions", outcome="fallback"
        ).inc()
        fallback = _fallback_actions(scene, assigned_agents)
        _stamp_action_durations(fallback.get("actions", []))
        return fallback

    _stamp_action_durations(parsed["actions"])
    maic_scene_generation_total.labels(
        scene_type="scene_actions", outcome="ok"
    ).inc()
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

# ─── Multi-agent Director (Porting P3.1) ─────────────────────────────────────
#
# Round-robin turn order feels mechanical — every agent speaks once, in
# roster order, regardless of whether they have anything useful to say.
# This director picks the next speaker given the conversation so far:
# whoever would most naturally take the turn (the one being addressed,
# the domain expert for the current sub-topic, the Socratic voice when
# the group has agreed too quickly, etc.).
#
# Returns JSON: {"next_speaker_id": "...", "reasoning": "one short sentence"}
# Front-end falls back to round-robin on empty / malformed output.

DIRECTOR_TURN_SYSTEM_PROMPT = """You are a silent classroom director deciding which agent should speak next in a multi-agent discussion. You do NOT speak yourself — you only pick the next turn.

Rules:
- Return a valid JSON object with exactly two fields: `next_speaker_id` (one of the agent ids in the provided roster) and `reasoning` (one short sentence, <= 140 chars, explaining the pick).
- Pick the agent who would most naturally speak next given the conversation state:
  * If a prior turn directly addressed or named someone, pick them.
  * If the group has agreed too quickly, pick someone whose persona adds friction (a Socratic questioner, a skeptic, the professor asking for evidence).
  * If a sub-topic surfaced that matches an agent's domain or speakingStyle, pick them.
  * Avoid picking the agent who JUST spoke unless the student explicitly asked them something.
  * End the discussion (`next_speaker_id` = "" ) only if the conversation has reached a clear resolution.
- Do NOT invent speaker ids outside the roster.
- Do NOT include extra fields or prose outside the JSON object."""


def director_next_turn(agents: list[dict], transcript: list[dict], topic: str,
                        last_speaker_id: str | None, student_input: str | None,
                        config: TenantAIConfig) -> dict | None:
    """Decide which agent speaks next in a discussion. Returns
    ``{"next_speaker_id": str, "reasoning": str}`` or ``None`` when the
    LLM can't produce a useful answer — caller should fall back to
    round-robin.

    ``transcript`` is the prior AgentTurnSummary list (agentId, agentName,
    contentPreview). Keeping it as a list of dicts avoids coupling to the
    TS types; the caller passes them through unchanged.
    """
    roster = [{
        "id": a.get("id"),
        "name": a.get("name"),
        "role": a.get("role", "professor"),
        "persona": a.get("persona") or a.get("personality", ""),
        "speakingStyle": a.get("speakingStyle", ""),
    } for a in agents if a.get("id")]
    if len(roster) < 2:
        return None

    # Cap transcript to the last ~8 turns so the prompt stays cheap even
    # on long discussions; the rolling summary (P3.3) carries the rest.
    tail = transcript[-8:] if len(transcript) > 8 else transcript
    compact = [{
        "agentId": t.get("agentId"),
        "agentName": t.get("agentName"),
        "preview": (t.get("contentPreview") or "")[:320],
    } for t in tail]

    user_prompt = (
        f"Topic: {topic or '(no topic)'}\n"
        f"Last speaker: {last_speaker_id or '(none yet)'}\n"
        + (f"Student just said: {student_input[:500]}\n" if student_input else "")
        + "\nAgent roster:\n"
        + json.dumps(roster, indent=2)
        + "\n\nTranscript so far (most recent last):\n"
        + json.dumps(compact, indent=2)
        + "\n\nReturn ONLY the JSON object. Empty next_speaker_id ends the discussion."
    )

    raw = _call_llm(config, DIRECTOR_TURN_SYSTEM_PROMPT, user_prompt,
                    temperature=0.4, max_tokens=256)
    if not raw:
        return None
    parsed = _parse_json_from_llm(raw)
    if not parsed or not isinstance(parsed, dict):
        return None
    next_id = parsed.get("next_speaker_id")
    if next_id is None:
        return None
    # Coerce and validate against the roster. Empty string is a valid
    # "end discussion" signal; anything else must match a real id.
    next_id = str(next_id).strip()
    if next_id and next_id not in {a["id"] for a in roster}:
        return None
    return {
        "next_speaker_id": next_id,
        "reasoning": str(parsed.get("reasoning") or "")[:200],
    }


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
        logger.warning(
            "chat LLM call failed: %s",
            exc,
            extra=log_extra(
                MAICPhase.CHAT,
                metric="chat_llm_failed",
                outcome="exception",
                error_type=type(exc).__name__,
            ),
        )
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
        logger.warning(
            "chat LLM parse failed err=%s raw=%s",
            exc, str(raw)[:500],
            extra=log_extra(
                MAICPhase.CHAT,
                metric="chat_parse_failed",
                outcome="parse_failed",
                error_type=type(exc).__name__,
            ),
        )
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
            logger.warning(
                "chat LLM returned list with no valid entries; raw=%s",
                str(raw)[:500],
                extra=log_extra(
                    MAICPhase.CHAT,
                    metric="chat_no_valid_entries",
                    outcome="empty_entries",
                ),
            )
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
            extra=log_extra(
                MAICPhase.TTS,
                metric="tts_edge_fallback",
                outcome="edge_failed",
                voice_id=effective_voice,
                provider=config.tts_provider,
            ),
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
        logger.info(
            "No TTS API key for %s, falling back to Edge TTS",
            tts_provider,
            extra=log_extra(
                MAICPhase.TTS,
                metric="tts_no_api_key",
                outcome="edge_fallback",
                provider=tts_provider,
            ),
        )
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
            logger.warning(
                "Unsupported TTS provider: %s, falling back to Edge TTS",
                tts_provider,
                extra=log_extra(
                    MAICPhase.TTS,
                    metric="tts_unsupported_provider",
                    outcome="edge_fallback",
                    provider=tts_provider,
                ),
            )
            return _tts_edge(text, effective_voice)
    except Exception as e:
        logger.error(
            "TTS generation failed (%s): %s — falling back to Edge TTS",
            tts_provider, e,
            extra=log_extra(
                MAICPhase.TTS,
                metric="tts_generation_failed",
                outcome="edge_fallback",
                provider=tts_provider,
                error_type=type(e).__name__,
            ),
        )
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
        logger.error(
            "Edge TTS generation failed: %s",
            e,
            extra=log_extra(
                MAICPhase.TTS,
                metric="tts_edge_failed",
                outcome="edge_failed",
                provider="edge_tts",
                error_type=type(e).__name__,
            ),
        )
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
