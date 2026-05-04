"""JSON parsing with fallback strategies for AI-generated responses.

Direct port of upstream `lib/generation/json-repair.ts` (189 lines).

Source:
    https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/generation/json-repair.ts
    /Volumes/CrucialX9/OpenMAIC/lib/generation/json-repair.ts

Used by:
    - apps.maic.generation.outline_generator (MAIC-421)
    - apps.maic.generation.scene_generator (MAIC-422.x)
    - apps.maic.generation.action_parser (MAIC-424)

Strategy stack (mirrors upstream `parseJsonResponse`):
    1. Extract from markdown code blocks: ```json ... ``` or ``` ... ```
    2. Find JSON structure directly in the response (bracket-balanced
       extraction with string + escape awareness).
    3. Last resort — try the whole trimmed response.

Each candidate string runs through `try_parse_json`, which itself has
4 attempts (mirrors upstream `tryParseJson`):
    1. Plain `json.loads(...)`.
    2. Fix LaTeX-style escapes + invalid escape sequences + truncated
       arrays/objects.
    3. Use the `json_repair` package (Python equivalent of upstream's
       `jsonrepair` npm package) for last-resort malformed JSON.
    4. Strip control characters, then try again.

Returns `None` (not raising) on every parse failure — the generation
pipeline wraps None into a `GenerationResult{success: False, ...}`
envelope upstream.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, TypeVar

import json_repair as _json_repair_lib


_logger = logging.getLogger("apps.maic.generation.json_repair")


# Generic return type. The upstream signature is `<T> -> T | null`;
# Python doesn't have a clean way to keep that constraint at runtime
# (the parser doesn't validate against T), so callers downcast via
# `cast(...)` or pydantic validation as needed.
T = TypeVar("T")


# ── Public API ────────────────────────────────────────────────────


def parse_json_response(response: str) -> Any | None:
    """Parse JSON out of an AI-generated response with multi-strategy
    fallbacks. Returns None on every parse failure.

    Mirrors upstream `parseJsonResponse<T>(response: string): T | null`.

    Strategy 1 — markdown code blocks: matches every ```json ... ```
    or ``` ... ``` block and tries each. Returns the first that parses.

    Strategy 2 — bracket-balanced extraction: finds the first `[` or
    `{` and walks forward, tracking string boundaries + escapes, to
    locate the matching close bracket. Tries the substring.

    Strategy 3 — whole response: trim + try.
    """
    # Strategy 1: code blocks. Find every ```json ... ``` (or ``` ... ```)
    # and try each. The (?:json)? makes the language tag optional.
    code_block_re = re.compile(r"```(?:json)?\s*([\s\S]*?)```")
    for match in code_block_re.finditer(response):
        extracted = match.group(1).strip()
        # Only try if it looks like JSON (starts with { or [)
        if extracted.startswith("{") or extracted.startswith("["):
            result = try_parse_json(extracted)
            if result is not None:
                _logger.debug("Successfully parsed JSON from code block")
                return result

    # Strategy 2: scan for the first [ or { and walk forward.
    json_start_array = response.find("[")
    json_start_object = response.find("{")

    if json_start_array != -1 or json_start_object != -1:
        if json_start_array == -1:
            start_index = json_start_object
        elif json_start_object == -1:
            start_index = json_start_array
        else:
            start_index = min(json_start_array, json_start_object)

        end_index = _find_matching_close(response, start_index)
        if end_index != -1:
            json_str = response[start_index : end_index + 1]
            result = try_parse_json(json_str)
            if result is not None:
                _logger.debug("Successfully parsed JSON from response body")
                return result

    # Strategy 3: try the whole trimmed response.
    result = try_parse_json(response.strip())
    if result is not None:
        _logger.debug("Successfully parsed raw response as JSON")
        return result

    _logger.error("Failed to parse JSON from response")
    _logger.error("Raw response (first 500 chars): %s", response[:500])
    return None


def try_parse_json(json_str: str) -> Any | None:
    """Parse a JSON string with progressively-aggressive fixes.

    Mirrors upstream `tryParseJson<T>(jsonStr: string): T | null`.
    Returns None on every parse failure.

    Attempt 1 — `json.loads(json_str)`.
    Attempt 2 — fix LaTeX-style escapes + invalid escapes + truncated
                arrays/objects, then `json.loads`.
    Attempt 3 — `json_repair.repair_json(...)` (Python `json-repair`
                package; equivalent of upstream's `jsonrepair` npm).
    Attempt 4 — strip/escape control characters, then `json.loads`.
    """
    # Attempt 1: plain
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        pass

    # Attempt 2: common AI-response fixes
    try:
        fixed = _apply_common_fixes(json_str)
        return json.loads(fixed)
    except (json.JSONDecodeError, ValueError):
        pass

    # Attempt 3: json-repair library
    try:
        repaired = _json_repair_lib.repair_json(json_str)
        # repair_json may return either a JSON string or the parsed
        # value depending on the version. Both are acceptable downstream
        # if json.loads succeeds; if repair_json already gave us a
        # parsed object, use it directly.
        if isinstance(repaired, str):
            return json.loads(repaired)
        return repaired
    except (json.JSONDecodeError, ValueError, Exception):  # noqa: BLE001
        pass

    # Attempt 4: remove control characters, then try again
    try:
        fixed = _strip_control_chars(json_str)
        return json.loads(fixed)
    except (json.JSONDecodeError, ValueError):
        return None


# ── Internal helpers ──────────────────────────────────────────────


def _find_matching_close(response: str, start_index: int) -> int:
    """Walk forward from `start_index` (a `[` or `{`) tracking
    bracket depth, string boundaries, and escapes. Returns the index
    of the matching close bracket, or -1 if unmatched."""
    depth = 0
    in_string = False
    escape_next = False

    for i in range(start_index, len(response)):
        char = response[i]

        if escape_next:
            escape_next = False
            continue

        if char == "\\" and in_string:
            escape_next = True
            continue

        if char == '"' and not escape_next:
            in_string = not in_string
            continue

        if not in_string:
            if char in ("[", "{"):
                depth += 1
            elif char in ("]", "}"):
                depth -= 1
                if depth == 0:
                    return i
    return -1


# Valid JSON escape characters (per RFC 8259):
#   \"  \\  \/  \b  \f  \n  \r  \t  \uXXXX
# When we see `\<letter>`, treat it as a LaTeX command and double-escape.
_VALID_JSON_ESCAPE_LETTERS = frozenset("bfnrtu")


def _apply_common_fixes(json_str: str) -> str:
    """Apply Fix 1 + Fix 2 + Fix 3 from upstream `tryParseJson`.

    Fix 1: Inside string literals, double-escape `\\<letter>` unless
        the letter is a valid JSON escape letter (b/f/n/r/t/u).
        This handles LaTeX commands like `\\frac`, `\\left`, etc.

    Fix 2: For backslashes outside string content (rare; usually the
        regex catches it inside strings), double-escape `\\<letter>`
        for non-JSON-escape letters.

    Fix 3: Truncated JSON arrays/objects — close them as best we can.
    """
    fixed = json_str

    # Fix 1: double-escape LaTeX commands inside strings.
    # Matches "..." capturing the content; replaces \<letter> with
    # \\<letter> when <letter> is not a valid JSON escape letter.
    string_re = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')

    def _fix_string_content(match: re.Match[str]) -> str:
        content = match.group(1)

        def _fix_escape(esc: re.Match[str]) -> str:
            ch = esc.group(1)
            if ch in _VALID_JSON_ESCAPE_LETTERS:
                return f"\\{ch}"
            return f"\\\\{ch}"

        fixed_content = re.sub(r"\\([a-zA-Z])", _fix_escape, content)
        return f'"{fixed_content}"'

    fixed = string_re.sub(_fix_string_content, fixed)

    # Fix 2: catch any remaining `\<non-json-escape>` outside strings.
    # Valid JSON escapes: \", \\, \/, \b, \f, \n, \r, \t, \u
    # The negative class catches everything else; if it's a letter,
    # double-escape (LaTeX); otherwise leave alone (could be malformed).
    def _fix_loose_escape(match: re.Match[str]) -> str:
        char = match.group(1)
        if re.match(r"[a-zA-Z]", char):
            return f"\\\\{char}"
        return match.group(0)

    fixed = re.sub(r'\\([^"\\\/bfnrtu\n\r])', _fix_loose_escape, fixed)

    # Fix 3: truncated arrays/objects.
    trimmed = fixed.strip()
    if trimmed.startswith("[") and not trimmed.endswith("]"):
        last_complete = fixed.rfind("}")
        if last_complete > 0:
            fixed = fixed[: last_complete + 1] + "]"
            _logger.warning("Fixed truncated JSON array")
    elif trimmed.startswith("{") and not trimmed.endswith("}"):
        open_braces = fixed.count("{")
        close_braces = fixed.count("}")
        if open_braces > close_braces:
            fixed += "}" * (open_braces - close_braces)
            _logger.warning("Fixed truncated JSON object")

    return fixed


def _strip_control_chars(json_str: str) -> str:
    """Replace control characters (Attempt 4 in upstream).

    \\n / \\r / \\t become their JSON-escape forms; other control
    characters (0x00–0x1F, 0x7F) are removed entirely.
    """
    def _replace(match: re.Match[str]) -> str:
        ch = match.group(0)
        if ch == "\n":
            return "\\n"
        if ch == "\r":
            return "\\r"
        if ch == "\t":
            return "\\t"
        return ""

    return re.sub(r"[\x00-\x1F\x7F]", _replace, json_str)
