"""File-based prompt loader.

Direct port of upstream lib/prompts/loader.ts (145 lines). Same
template language, same processing order, same error semantics.

Source:
    https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/prompts/loader.ts
    https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/prompts/README.md

Template language (in processing order — applied by build_prompt):

  1. Snippet includes — `{{snippet:name}}` spliced from
     prompts/snippets/<name>.md
  2. Conditional blocks — `{{#if flag}}...{{/if}}` kept iff variables[flag] truthy
  3. Variable interpolation — `{{varName}}` replaced with str(value)

Conventions (per upstream README):

  - Placeholder names use camelCase (e.g. `{{agentName}}`).
  - Template IDs use kebab-case (e.g. `agent-system`, `pbl-design`).
  - The kebab-case `slide-content` template legacy uses snake_case
    placeholders for historical reasons; new templates should use
    camelCase.

Failure modes:

  - Missing snippet → raises MaicConfigError (we don't ship `{{snippet:foo}}`
    literal strings to the LLM; that always indicates a typo in a template).
  - Missing template directory or system.md → load_prompt returns None
    (callers handle as "prompt not configured"); build_prompt returns None.
  - Unknown variable in interpolation → silently leaves `{{varName}}` in
    the output. Same behavior as upstream — flagged in tests by
    snapshot/regex scans rather than the loader itself.

Cache: per-process LRU on snippet content (rare to change at runtime;
a sysadmin restart picks up changes).
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple

from apps.maic.exceptions import MaicConfigError

logger = logging.getLogger(__name__)


# ── Constants ──────────────────────────────────────────────────────────


_PROMPTS_DIR = Path(__file__).parent  # apps/maic/prompts/
_TEMPLATES_DIR = _PROMPTS_DIR / "templates"
_SNIPPETS_DIR = _PROMPTS_DIR / "snippets"

# upstream's regexes — translated 1:1
_RE_SNIPPET_INCLUDE = re.compile(r"\{\{snippet:(\w[\w-]*)\}\}")
_RE_CONDITIONAL_BLOCK = re.compile(r"\{\{#if (\w+)\}\}([\s\S]*?)\{\{/if\}\}")
_RE_VARIABLE = re.compile(r"\{\{(\w+)\}\}")


class LoadedPrompt(NamedTuple):
    """Result of load_prompt — system + optional user template."""

    id: str
    systemPrompt: str
    userPromptTemplate: str  # "" when no user.md exists


class BuiltPrompt(NamedTuple):
    """Result of build_prompt — fully interpolated system + user strings."""

    system: str
    user: str


# ── Snippet loading ────────────────────────────────────────────────────


@lru_cache(maxsize=64)
def _read_snippet_cached(snippet_id: str) -> str:
    """Read a snippet from disk. Cached for the process lifetime —
    snippets rarely change at runtime; a server restart picks up edits.
    """
    snippet_path = _SNIPPETS_DIR / f"{snippet_id}.md"
    if not snippet_path.is_file():
        raise MaicConfigError(f"Snippet not found: {snippet_id}")
    return snippet_path.read_text(encoding="utf-8").strip()


def load_snippet(snippet_id: str) -> str:
    """Load a snippet by ID. Raises MaicConfigError if missing — better
    to fail loud at load time than ship a literal `{{snippet:foo}}` to
    the LLM."""
    return _read_snippet_cached(snippet_id)


def clear_cache() -> None:
    """Clear the snippet cache. Tests use this to swap fixtures between
    cases without process restart."""
    _read_snippet_cached.cache_clear()


# ── Template processing steps ──────────────────────────────────────────


def process_snippets(template: str) -> str:
    """Replace `{{snippet:name}}` with the loaded snippet content.

    Snippets may themselves contain `{{snippet:...}}`, `{{#if}}`, and
    `{{var}}` placeholders — we intentionally do NOT recurse on snippet
    inclusion (matches upstream behavior; a reviewable templating
    surface is more important than nested includes).
    """
    return _RE_SNIPPET_INCLUDE.sub(
        lambda m: load_snippet(m.group(1)),
        template,
    )


def process_conditional_blocks(template: str, variables: dict[str, Any]) -> str:
    """Replace `{{#if flag}}...{{/if}}` blocks based on truthy `variables[flag]`.

    Blocks do not nest — same constraint as upstream. The non-greedy
    `[\\s\\S]*?` regex matches inner content up to the first `{{/if}}`.
    """
    return _RE_CONDITIONAL_BLOCK.sub(
        lambda m: m.group(2) if variables.get(m.group(1)) else "",
        template,
    )


def interpolate_variables(template: str, variables: dict[str, Any]) -> str:
    """Replace `{{varName}}` with `variables[varName]`.

    Behaviors mirror upstream lib/prompts/loader.ts:108-118:

      - Unknown placeholder → left intact (caller's tests should catch
        the literal `{{...}}` survival; we don't fail at this layer).
      - dict/list value → `json.dumps(..., indent=2)` (same as upstream's
        `JSON.stringify(value, null, 2)`).
      - Other types → `str(value)`.

    Note: regex `\\w+` matches only [A-Za-z0-9_], so kebab-case
    placeholders (e.g. `{{next-agent}}`) pass through unchanged. Per
    upstream README, kebab-case in placeholder names is a convention
    violation; tests should catch any.
    """
    def _replace(m: re.Match) -> str:
        key = m.group(1)
        if key not in variables:
            return m.group(0)
        value = variables[key]
        if isinstance(value, (dict, list)):
            return json.dumps(value, indent=2)
        return str(value)

    return _RE_VARIABLE.sub(_replace, template)


# ── Public API ─────────────────────────────────────────────────────────


def load_prompt(prompt_id: str) -> LoadedPrompt | None:
    """Load a prompt by ID from `templates/<prompt_id>/`.

    Returns None when the directory or required `system.md` is missing
    — calls log at ERROR level. `user.md` is optional.

    Snippets are processed BEFORE returning so the LoadedPrompt holds
    the post-snippet template; conditional + variable processing
    happens at build_prompt time.
    """
    prompt_dir = _TEMPLATES_DIR / prompt_id
    system_path = prompt_dir / "system.md"

    if not system_path.is_file():
        logger.error("Failed to load prompt %s — missing %s", prompt_id, system_path)
        return None

    try:
        system_prompt = system_path.read_text(encoding="utf-8").strip()
        system_prompt = process_snippets(system_prompt)

        user_path = prompt_dir / "user.md"
        if user_path.is_file():
            user_prompt = user_path.read_text(encoding="utf-8").strip()
            user_prompt = process_snippets(user_prompt)
        else:
            user_prompt = ""

        return LoadedPrompt(
            id=prompt_id,
            systemPrompt=system_prompt,
            userPromptTemplate=user_prompt,
        )
    except MaicConfigError:
        # Missing-snippet errors propagate — the agent can't be invoked
        # without a fully-resolved prompt.
        raise
    except Exception:
        logger.exception("Failed to load prompt %s", prompt_id)
        return None


def build_prompt(prompt_id: str, variables: dict[str, Any]) -> BuiltPrompt | None:
    """Load + fully process a prompt: snippets → conditionals → variables.

    Returns None if the template can't be loaded.
    """
    prompt = load_prompt(prompt_id)
    if prompt is None:
        return None

    system = interpolate_variables(
        process_conditional_blocks(prompt.systemPrompt, variables),
        variables,
    )
    user = interpolate_variables(
        process_conditional_blocks(prompt.userPromptTemplate, variables),
        variables,
    )
    return BuiltPrompt(system=system, user=user)


def list_available_prompts() -> list[str]:
    """Return all template IDs available on disk. Useful in MAIC-204
    landing for sanity checking that all expected templates are
    present."""
    if not _TEMPLATES_DIR.is_dir():
        return []
    return sorted([p.name for p in _TEMPLATES_DIR.iterdir() if p.is_dir()])


def list_available_snippets() -> list[str]:
    """Return all snippet IDs available on disk."""
    if not _SNIPPETS_DIR.is_dir():
        return []
    return sorted([p.stem for p in _SNIPPETS_DIR.glob("*.md")])
