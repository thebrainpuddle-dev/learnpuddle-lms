"""Action descriptions + scene filter — what an agent is told it CAN do.

Direct port of upstream lib/orchestration/tool-schemas.ts (72 lines).
Same descriptions, same scene-filtering rule, same fallback when an
agent has zero allowed actions.

Source:
    https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/orchestration/tool-schemas.ts

Used by:
    - apps.maic.orchestration.prompt_builder (Phase 3 MAIC-108)
      injects `get_action_descriptions(...)` into the agent system prompt
      so the LLM knows the schema of every action it may emit.
    - apps.maic.orchestration.director_graph._agent_generate_node
      (MAIC-105) calls `get_effective_actions(...)` to filter
      slide-only actions on non-slide scenes BEFORE handing the action
      list to the prompt builder.

The descriptions here are NOT a duplicate of the Pydantic models in
apps.maic.protocol — those describe the wire format we ACCEPT from the
LLM; these describe the schema we ASK the LLM to emit.
"""
from __future__ import annotations

from apps.maic.protocol import SLIDE_ONLY_ACTIONS


# ── Effective actions (scene-aware filter) ────────────────────────────


def get_effective_actions(
    allowed_actions: list[str],
    scene_type: str | None = None,
) -> list[str]:
    """Filter `allowed_actions` by scene type.

    Slide-only actions (`spotlight`, `laser`) are stripped for non-slide
    scenes. Same logic as upstream getEffectiveActions().

    A scene_type of None or "slide" → no filtering (full list returned).
    Anything else → strip slide-only actions.
    """
    if scene_type is None or scene_type == "slide":
        return list(allowed_actions)
    return [a for a in allowed_actions if a not in SLIDE_ONLY_ACTIONS]


# ── Action descriptions for prompt injection ──────────────────────────


_ACTION_DESCRIPTIONS: dict[str, str] = {
    "spotlight": (
        "Focus attention on a single key element by dimming everything else. "
        "Use sparingly — max 1-2 per response. "
        "Parameters: { elementId: string, dimOpacity?: number }"
    ),
    "laser": (
        "Point at an element with a laser pointer effect. "
        "Parameters: { elementId: string, color?: string }"
    ),
    "wb_open": (
        "Open the whiteboard for hand-drawn explanations, formulas, diagrams, or "
        "step-by-step derivations. Creates a new whiteboard if none exists. "
        "Call this before adding elements. Parameters: {}"
    ),
    "wb_draw_text": (
        "Add text to the whiteboard. Use for writing formulas, steps, or key points. "
        "Parameters: { content: string, x: number, y: number, width?: number, "
        "height?: number, fontSize?: number, color?: string, elementId?: string }"
    ),
    "wb_draw_shape": (
        "Add a shape to the whiteboard. Use for diagrams and visual explanations. "
        "Parameters: { shape: \"rectangle\"|\"circle\"|\"triangle\", x: number, "
        "y: number, width: number, height: number, fillColor?: string, "
        "elementId?: string }"
    ),
    "wb_draw_chart": (
        "Add a chart to the whiteboard. Use for data visualization (bar charts, "
        "line graphs, pie charts, etc.). Parameters: { chartType: \"bar\"|"
        "\"column\"|\"line\"|\"pie\"|\"ring\"|\"area\"|\"radar\"|\"scatter\", "
        "x: number, y: number, width: number, height: number, "
        "data: { labels: string[], legends: string[], series: number[][] }, "
        "themeColors?: string[], elementId?: string }"
    ),
    "wb_draw_latex": (
        "Add a LaTeX formula to the whiteboard. Use for mathematical equations "
        "and scientific notation. Parameters: { latex: string, x: number, "
        "y: number, width?: number, height?: number, color?: string, "
        "elementId?: string }"
    ),
    "wb_draw_table": (
        "Add a table to the whiteboard. Use for structured data display and "
        "comparisons. Parameters: { x: number, y: number, width: number, "
        "height: number, data: string[][] (first row is header), "
        "outline?: { width: number, style: string, color: string }, "
        "theme?: { color: string }, elementId?: string }"
    ),
    "wb_draw_line": (
        "Add a line or arrow to the whiteboard. Use for connecting elements, "
        "drawing relationships, flow diagrams, or annotations. Parameters: { "
        "startX: number, startY: number, endX: number, endY: number, "
        "color?: string (default \"#333333\"), width?: number (line thickness, "
        "default 2), style?: \"solid\"|\"dashed\" (default \"solid\"), "
        "points?: [startMarker, endMarker] where marker is \"\"|\"arrow\" "
        "(default [\"\",\"\"]), elementId?: string }"
    ),
    "wb_draw_code": (
        "Add a code block to the whiteboard with syntax highlighting. The code "
        "block has a header bar (~32px) showing the file name and language "
        "label, so the actual code area starts below that. When positioning, "
        "account for this: the effective code area top is about y+32. Use for "
        "demonstrating code, algorithms, or programming concepts. Parameters: "
        "{ language: string (e.g. \"python\", \"javascript\", \"typescript\", "
        "\"json\", \"go\", \"rust\", \"java\", \"c\", \"cpp\"), code: string "
        "(source code, use \\n for newlines), x: number, y: number, "
        "width?: number (default 500), height?: number (default 300, includes "
        "~32px header), fileName?: string (e.g. \"main.py\"), elementId?: string }"
    ),
    "wb_edit_code": (
        "Edit an existing code block on the whiteboard by inserting, deleting, "
        "or replacing lines. Each line has a stable ID (e.g. \"L1\", \"L2\") "
        "shown in the whiteboard state. Use this for step-by-step code "
        "demonstrations: first draw a code block, then incrementally add/modify "
        "lines with speech in between. Parameters: { elementId: string (target "
        "code block), operation: \"insert_after\"|\"insert_before\"|"
        "\"delete_lines\"|\"replace_lines\", lineId?: string (reference line "
        "for insert), lineIds?: string[] (target lines for delete/replace), "
        "content?: string (new code for insert/replace, use \\n for newlines) }"
    ),
    "wb_clear": (
        "Clear all elements from the whiteboard. Use when whiteboard is too "
        "crowded before adding new elements. Parameters: {}"
    ),
    "wb_delete": (
        "Delete a specific element from the whiteboard by its ID. Use to remove "
        "an outdated, incorrect, or overlapping element without clearing the "
        "entire board. Parameters: { elementId: string }"
    ),
    "wb_close": (
        "Close the whiteboard and return to the slide view. Always close after "
        "you finish drawing. Parameters: {}"
    ),
    "play_video": (
        "Start playback of a video element on the current slide. Synchronous — "
        "blocks until the video finishes playing. Use a speech action before "
        "this to introduce the video. Parameters: { elementId: string }"
    ),
}


def get_action_descriptions(allowed_actions: list[str]) -> str:
    """Render the description block to inject into the agent system prompt.

    Empty allowed_actions → returns the upstream's no-actions message
    (the agent can still emit `text` items, just no actions).
    """
    if not allowed_actions:
        return "You have no actions available. You can only speak to students."

    lines = [
        f"- {action}: {desc}"
        for action in allowed_actions
        if (desc := _ACTION_DESCRIPTIONS.get(action))
    ]
    return "\n".join(lines)
