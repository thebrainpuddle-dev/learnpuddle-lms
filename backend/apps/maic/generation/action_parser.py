"""Action Parser — converts structured JSON Array output to Action[].

Direct port of upstream `lib/generation/action-parser.ts` (153 lines).

Source:
    https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/generation/action-parser.ts
    /Volumes/CrucialX9/OpenMAIC/lib/generation/action-parser.ts

Bridges the stateless-generate parser (Phase 1, online streaming) with
the offline generation pipeline (Phase 4), producing typed Action
dicts that preserve the original interleaving order from the LLM.

For complete (non-streaming) responses, uses `json.loads` with
json_repair fallback for robustness.

Used by:
    - apps.maic.generation.scene_generator (Stage 2 actions LLM call)
"""
from __future__ import annotations

import json
import logging
import re
import secrets
from typing import Any

import json_repair as _json_repair_lib

from apps.maic.protocol import SLIDE_ONLY_ACTIONS


_logger = logging.getLogger("apps.maic.generation.action_parser")


# ── Public API ────────────────────────────────────────────────────


def parse_actions_from_structured_output(
    response: str,
    scene_type: str | None = None,
    allowed_actions: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Parse a complete LLM response into an ordered list of Action dicts.

    Mirrors upstream `parseActionsFromStructuredOutput`.

    Expected format (new):
        [{"type":"action","name":"spotlight","params":{"elementId":"..."}},
         {"type":"text","content":"speech content"}, ...]

    Also supports legacy format:
        [{"type":"action","tool_name":"spotlight","parameters":{...}}, ...]

    Text items become `speech` actions; action items are converted to
    their respective action types (spotlight, discussion, etc.) with
    a generated `id`. Original interleaving order is preserved.

    Post-processing:
        - `discussion` must be the LAST action; if found earlier,
          everything after it is dropped (mirrors upstream).
        - For non-slide scenes, `spotlight` and `laser` are stripped
          (defense-in-depth on top of the prompt-builder filter).
        - `allowed_actions` whitelist filters out hallucinated actions
          a role-restricted agent shouldn't emit. `speech` is always
          permitted.

    Returns an empty list on any parse failure (no exceptions raised).
    The generation pipeline wraps the empty list into a higher-level
    `GenerationResult{success: False, ...}` if it cares.
    """
    # Step 1: strip markdown code fences if present.
    cleaned = _strip_code_fences(response.strip())

    # Step 2: locate the JSON array range.
    start_idx = cleaned.find("[")
    end_idx = cleaned.rfind("]")
    if start_idx == -1:
        _logger.warning("No JSON array found in response")
        return []
    if end_idx > start_idx:
        json_str = cleaned[start_idx : end_idx + 1]
    else:
        # Unclosed array — let json_repair handle it.
        json_str = cleaned[start_idx:]

    # Step 3: parse — plain → json_repair → fail.
    items = _parse_array_robust(json_str)
    if items is None:
        return []

    # Step 4: convert items to Action dicts.
    actions: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or "type" not in item:
            continue

        if item["type"] == "text":
            text = (item.get("content") or "").strip()
            if text:
                actions.append({
                    "id": _generate_action_id(),
                    "type": "speech",
                    "text": text,
                })
        elif item["type"] == "action":
            # Support both new format (name/params) and legacy format
            # (tool_name/parameters).
            action_name = _normalize_action_name(
                _first_non_empty(
                    item,
                    ("name", "tool_name", "toolName", "actionName", "action_name"),
                )
            )
            if not action_name:
                _logger.warning(
                    "Invalid action item (no name): %s",
                    json.dumps(item)[:100],
                )
                continue
            action_params = _extract_action_params(item)
            if not isinstance(action_params, dict):
                _logger.warning(
                    "Invalid action params (not dict): %s",
                    json.dumps(item)[:100],
                )
                continue
            action_params = _normalize_action_params(action_name, action_params)
            action_id = (
                item.get("action_id")
                or item.get("actionId")
                or item.get("tool_id")
                or item.get("toolId")
                or item.get("id")
                or _generate_action_id()
            )
            actions.append({
                "id": action_id,
                "type": action_name,
                **action_params,
            })

    # Step 5: post-processing — discussion must be last and at most one.
    discussion_idx = next(
        (i for i, a in enumerate(actions) if a.get("type") == "discussion"),
        -1,
    )
    if discussion_idx != -1 and discussion_idx < len(actions) - 1:
        actions = actions[: discussion_idx + 1]

    # Step 6: strip slide-only actions for non-slide scenes
    # (defense in depth — the prompt-builder also filters these).
    result = actions
    if scene_type and scene_type != "slide":
        before = len(result)
        result = [
            a for a in result
            if a.get("type") not in SLIDE_ONLY_ACTIONS
        ]
        if len(result) < before:
            _logger.info(
                "Stripped %d slide-only action(s) from %s scene",
                before - len(result),
                scene_type,
            )

    # Step 7: filter by allowed_actions whitelist (role-based isolation).
    # `speech` is always permitted (it's the agent's voice).
    if allowed_actions:
        allowed_set = set(allowed_actions)
        before = len(result)
        result = [
            a for a in result
            if a.get("type") == "speech" or a.get("type") in allowed_set
        ]
        if len(result) < before:
            _logger.info(
                "Stripped %d disallowed action(s) by allowed_actions whitelist",
                before - len(result),
            )

    return result


# ── Internal helpers ──────────────────────────────────────────────


_CODE_FENCE_OPEN = re.compile(r"^```(?:json)?\s*\n?", re.IGNORECASE)
_CODE_FENCE_CLOSE = re.compile(r"\n?\s*```\s*$", re.IGNORECASE)

_ACTION_NAME_ALIASES = {
    "focus": "spotlight",
    "focus_element": "spotlight",
    "highlight": "spotlight",
    "highlight_element": "spotlight",
    "laser_pointer": "laser",
    "laserpointer": "laser",
    "point": "laser",
    "pointer": "laser",
    "playvideo": "play_video",
    "play_video_element": "play_video",
    "video_play": "play_video",
    "whiteboard_open": "wb_open",
    "whiteboard_close": "wb_close",
    "whiteboard_clear": "wb_clear",
    "whiteboard_delete": "wb_delete",
    "draw_text": "wb_draw_text",
    "draw_shape": "wb_draw_shape",
    "draw_line": "wb_draw_line",
    "draw_latex": "wb_draw_latex",
    "draw_chart": "wb_draw_chart",
    "draw_table": "wb_draw_table",
    "draw_code": "wb_draw_code",
    "edit_code": "wb_edit_code",
    "widget_setstate": "widget_setState",
    "widget_set_state": "widget_setState",
}

_ACTION_PARAM_KEYS = ("params", "parameters", "arguments", "args", "input")
_ELEMENT_ID_ACTIONS = frozenset({
    "spotlight",
    "laser",
    "play_video",
    "wb_delete",
    "wb_edit_code",
    "wb_draw_text",
    "wb_draw_shape",
    "wb_draw_chart",
    "wb_draw_latex",
    "wb_draw_table",
    "wb_draw_line",
    "wb_draw_code",
})
_ELEMENT_ID_ALIASES = (
    "element_id",
    "elementID",
    "element",
    "targetId",
    "target_id",
    "target",
    "videoId",
    "video_id",
)
_SPOTLIGHT_DIM_ALIASES = ("dimness", "dim_opacity", "opacity", "dim")


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences (```json ... ``` or ``` ... ```)."""
    text = _CODE_FENCE_OPEN.sub("", text)
    text = _CODE_FENCE_CLOSE.sub("", text)
    return text


def _first_non_empty(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Return the first non-empty value from any of `keys`."""
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _normalize_action_name(raw: Any) -> str:
    """Normalize common LLM action-name variants to protocol names."""
    if raw is None:
        return ""
    name = str(raw).strip()
    if not name:
        return ""
    compact = re.sub(r"[\s-]+", "_", name).strip("_")
    alias_key = compact.lower()
    return _ACTION_NAME_ALIASES.get(alias_key, compact)


def _extract_action_params(item: dict[str, Any]) -> Any:
    """Extract params from common tool-call wrappers.

    Models sometimes return `arguments`/`args` or a JSON-encoded string
    instead of the preferred `params` object. Keep the preferred shape,
    but recover the common variants.
    """
    empty: dict[str, Any] | None = None
    invalid: Any = None
    for key in _ACTION_PARAM_KEYS:
        if key not in item:
            continue
        value = item.get(key)
        if isinstance(value, dict):
            if value:
                return value
            empty = value
        elif isinstance(value, str) and value.strip():
            parsed = _parse_object_robust(value)
            if parsed is not None:
                return parsed
            invalid = value
        elif value not in (None, ""):
            invalid = value
    if invalid is not None:
        return invalid
    return empty or {}


def _normalize_action_params(
    action_name: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Normalize common param aliases while preserving action semantics."""
    normalized = dict(params)

    if action_name in _ELEMENT_ID_ACTIONS:
        _move_first_alias(normalized, "elementId", _ELEMENT_ID_ALIASES)

    if action_name == "spotlight":
        _move_first_alias(normalized, "dimOpacity", _SPOTLIGHT_DIM_ALIASES)
        if "dimOpacity" in normalized:
            normalized["dimOpacity"] = _normalize_opacity(
                normalized["dimOpacity"]
            )

    if action_name == "laser":
        _move_first_alias(normalized, "color", ("colour",))

    if action_name == "discussion":
        _move_first_alias(normalized, "agentId", ("agent_id", "agentID"))

    return normalized


def _move_first_alias(
    params: dict[str, Any],
    canonical: str,
    aliases: tuple[str, ...],
) -> None:
    """Move the first available alias to `canonical` and drop duplicates."""
    chosen_alias: str | None = None
    if canonical not in params or params.get(canonical) in (None, ""):
        for alias in aliases:
            value = params.get(alias)
            if value not in (None, ""):
                params[canonical] = value
                chosen_alias = alias
                break

    for alias in aliases:
        if alias in params and alias != chosen_alias:
            params.pop(alias, None)
    if chosen_alias is not None:
        params.pop(chosen_alias, None)


def _normalize_opacity(value: Any) -> Any:
    """Parse numeric opacity strings; leave unparseable values untouched."""
    if isinstance(value, str):
        stripped = value.strip()
        try:
            if stripped.endswith("%"):
                return float(stripped[:-1].strip()) / 100
            return float(stripped)
        except ValueError:
            return value
    return value


def _parse_array_robust(json_str: str) -> list[Any] | None:
    """Try `json.loads`; fall back to `json_repair`. Return None on
    every failure. Returns the parsed value only if it's a list."""
    parsed: Any = None

    try:
        parsed = json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        # Try json_repair (Python equivalent of upstream's npm
        # jsonrepair + partial-json combined coverage).
        try:
            repaired = _json_repair_lib.repair_json(json_str)
            if isinstance(repaired, str):
                parsed = json.loads(repaired)
            else:
                parsed = repaired
            _logger.info("Recovered malformed JSON via json_repair")
        except (json.JSONDecodeError, ValueError, Exception) as e:  # noqa: BLE001
            _logger.warning("Failed to parse JSON array: %s", e)
            return None

    if not isinstance(parsed, list):
        _logger.warning("Parsed result is not an array")
        return None
    return parsed


def _parse_object_robust(json_str: str) -> dict[str, Any] | None:
    """Parse a params object from a JSON string using the same repair path."""
    parsed: Any = None
    try:
        parsed = json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        try:
            repaired = _json_repair_lib.repair_json(json_str)
            if isinstance(repaired, str):
                parsed = json.loads(repaired)
            else:
                parsed = repaired
        except (json.JSONDecodeError, ValueError, Exception):  # noqa: BLE001
            return None

    if not isinstance(parsed, dict):
        return None
    return parsed


def _generate_action_id() -> str:
    """8-char URL-safe ID prefixed with `action_` (mirrors upstream's
    `action_${nanoid(8)}`). Uses `secrets.token_urlsafe(6)` which
    yields ~8 chars after base64 encoding (length is unstable; trim)."""
    raw = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8]
    if len(raw) < 8:
        # Pad if base64 stripped chars left it too short (rare).
        raw = (raw + secrets.token_urlsafe(4))[:8]
    return f"action_{raw}"
