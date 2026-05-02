"""File-based prompt loader + templates.

Templates live under `apps/maic/prompts/templates/<id>/system.md` (and
optional `user.md`); snippets under `apps/maic/prompts/snippets/<id>.md`.
The 21 templates and 11 snippets are populated by MAIC-204 / MAIC-205
(direct port from upstream OpenMAIC/lib/prompts/).
"""
from .loader import (
    BuiltPrompt,
    LoadedPrompt,
    build_prompt,
    clear_cache,
    interpolate_variables,
    list_available_prompts,
    list_available_snippets,
    load_prompt,
    load_snippet,
    process_conditional_blocks,
    process_snippets,
)

__all__ = [
    "BuiltPrompt",
    "LoadedPrompt",
    "build_prompt",
    "clear_cache",
    "interpolate_variables",
    "list_available_prompts",
    "list_available_snippets",
    "load_prompt",
    "load_snippet",
    "process_conditional_blocks",
    "process_snippets",
]
