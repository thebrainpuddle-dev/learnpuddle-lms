"""Prompt and context building utilities for the generation pipeline.

Direct port of upstream `lib/generation/prompt-formatters.ts` (150 lines).

Source:
    https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/generation/prompt-formatters.ts
    /Volumes/CrucialX9/OpenMAIC/lib/generation/prompt-formatters.ts

Used by:
    - apps.maic.generation.outline_generator
    - apps.maic.generation.scene_generator (per-scene action/content prompts)

Phase 4 deferrals signposted below:
    - `format_image_description`, `format_image_placeholder`,
      `build_vision_user_content` — port the helper SHAPES so future
      sync with upstream stays clean, but generation callers in
      Phase 4 ignore them. PDF image extraction + multimodal slides
      land in Phase 5+ (DEFERRED).
"""
from __future__ import annotations

from typing import TypedDict

from apps.maic.generation.types import AgentInfo, SceneGenerationContext


# ── PdfImage TypedDict ─────────────────────────────────────────────


class PdfImage(TypedDict, total=False):
    """Subset of upstream `lib/types/generation.PdfImage` that the
    formatters touch. Phase 4 doesn't extract PDF images, but the
    helpers ship for shape-parity with upstream.

    DEFERRED: full PDF image extraction pipeline — Phase 5+.
    """

    id: str
    pageNumber: int
    width: int
    height: int
    description: str
    src: str  # data: URI OR https URL


# ── Course context ────────────────────────────────────────────────


def build_course_context(ctx: SceneGenerationContext | None = None) -> str:
    """Build a course-context string for injection into action prompts.

    Mirrors upstream `buildCourseContext`. Includes:
      - course outline with `← current` marker on the active page
      - same-session reminder (no greetings after page 1)
      - position-specific transition guidance (first / middle / last)
      - last 150 chars of the previous page's speech for transition

    Returns empty string when ctx is None.
    """
    if ctx is None:
        return ""

    lines: list[str] = []

    # Course outline with position marker
    lines.append("Course Outline:")
    page_index = ctx["pageIndex"]
    for i, t in enumerate(ctx["allTitles"]):
        marker = " ← current" if i == page_index - 1 else ""
        lines.append(f"  {i + 1}. {t}{marker}")

    # Position information
    lines.append("")
    lines.append(
        "IMPORTANT: All pages belong to the SAME class session. Do NOT "
        "greet again after the first page. When referencing content from "
        'earlier pages, say "we just covered" or "as mentioned on page N" '
        '— NEVER say "last class" or "previous session" because there is '
        "no previous session."
    )
    lines.append("")
    total_pages = ctx["totalPages"]
    if page_index == 1:
        lines.append(
            "Position: This is the FIRST page. Open with a greeting and "
            "course introduction."
        )
    elif page_index == total_pages:
        lines.append(
            "Position: This is the LAST page. Conclude the course with "
            "a summary and closing."
        )
        lines.append(
            "Transition: Continue naturally from the previous page. Do "
            "NOT greet or re-introduce."
        )
    else:
        lines.append(
            f"Position: Page {page_index} of {total_pages} (middle of "
            "the course)."
        )
        lines.append(
            "Transition: Continue naturally from the previous page. Do "
            "NOT greet or re-introduce."
        )

    # Previous page speech for transition reference
    previous_speeches = ctx.get("previousSpeeches", [])
    if previous_speeches:
        lines.append("")
        lines.append("Previous page speech (for transition reference):")
        last_speech = previous_speeches[-1]
        lines.append(f'  "...{last_speech[-150:]}"')

    return "\n".join(lines)


# ── Agent formatting ──────────────────────────────────────────────


def format_agents_for_prompt(agents: list[AgentInfo] | None = None) -> str:
    """Format the classroom agent roster for injection into action prompts.

    Mirrors upstream `formatAgentsForPrompt`. Empty string when no agents.
    """
    if not agents:
        return ""

    lines: list[str] = ["Classroom Agents:"]
    for a in agents:
        persona_part = f" — {a['persona']}" if a.get("persona") else ""
        lines.append(
            f'- id: "{a["id"]}", name: "{a["name"]}", role: {a["role"]}{persona_part}'
        )
    return "\n".join(lines)


def format_teacher_persona_for_prompt(
    agents: list[AgentInfo] | None = None,
) -> str:
    """Extract the teacher agent's persona for injection into
    outline/content prompts.

    Mirrors upstream `formatTeacherPersonaForPrompt`. Returns empty
    string when no teacher is found OR the teacher has no persona.

    Includes the explicit "no teacher name on slides" guard from
    upstream — slides should read as neutral, professional visual aids.
    """
    if not agents:
        return ""

    teacher = next((a for a in agents if a.get("role") == "teacher"), None)
    if teacher is None or not teacher.get("persona"):
        return ""

    return (
        f"Teacher Persona:\n"
        f"Name: {teacher['name']}\n"
        f"{teacher['persona']}\n"
        f"\n"
        f"Adapt the content style and tone to match this teacher's "
        f"personality. IMPORTANT: The teacher's name and identity must "
        f'NOT appear on the slides — no "Teacher {teacher["name"]}\'s '
        f'tips", no "Teacher\'s message", etc. Slides should read as '
        f"neutral, professional visual aids."
    )


# ── Image formatting (DEFERRED to Phase 5+) ───────────────────────


def format_image_description(img: PdfImage) -> str:
    """Format a single PdfImage description for prompt inclusion.

    Mirrors upstream `formatImageDescription`. Includes
    dimension/aspect-ratio info when available.

    DEFERRED: PDF image extraction pipeline ships in Phase 5+. This
    function exists for shape-parity with upstream so future ports
    can call it without a re-port.
    """
    dim_info = ""
    width = img.get("width")
    height = img.get("height")
    if width and height:
        ratio = f"{(width / height):.2f}"
        dim_info = f" | size: {width}×{height} (aspect ratio {ratio})"
    description = img.get("description")
    desc = f" | {description}" if description else ""
    return f"- **{img['id']}**: from PDF page {img['pageNumber']}{dim_info}{desc}"


def format_image_placeholder(img: PdfImage) -> str:
    """Format a short image placeholder for vision mode.

    Mirrors upstream `formatImagePlaceholder`. Used when the model can
    see the actual image (no need to inject the description).

    DEFERRED: vision/multimodal slides ship in Phase 5+.
    """
    dim_info = ""
    width = img.get("width")
    height = img.get("height")
    if width and height:
        ratio = f"{(width / height):.2f}"
        dim_info = f" | size: {width}×{height} (aspect ratio {ratio})"
    return (
        f"- **{img['id']}**: image from PDF page {img['pageNumber']}"
        f"{dim_info} [see attached]"
    )


def build_vision_user_content(
    user_prompt: str,
    images: list[dict] | None = None,
) -> list[dict]:
    """Build a multimodal user content array for vision-enabled models.

    Mirrors upstream `buildVisionUserContent`. Returns a list of
    `{type: 'text', text}` and `{type: 'image', image, mimeType}` parts.

    Each image label includes dimensions when available so the model
    knows the size before seeing the image (important for layout
    decisions).

    DEFERRED: vision/multimodal slides ship in Phase 5+. Phase 4
    callers pass `images=None` and get a single text-only part back.

    Strips `data:<mime>;base64,<payload>` URIs into separate
    `image` + `mimeType` fields (the AI SDK only accepts http(s)
    URLs or raw base64).
    """
    parts: list[dict] = [{"type": "text", "text": user_prompt}]
    if not images:
        return parts

    parts.append({"type": "text", "text": "\n\n--- Attached Images ---"})
    for img in images:
        dim_info = ""
        width = img.get("width")
        height = img.get("height")
        if width and height:
            ratio = f"{(width / height):.2f}"
            dim_info = f" ({width}×{height}, aspect ratio {ratio})"
        parts.append({"type": "text", "text": f"\n**{img['id']}**{dim_info}:"})
        # Strip data URI prefix
        src = img.get("src", "")
        if src.startswith("data:"):
            # Format: data:<mime>;base64,<payload>
            try:
                header, payload = src.split(",", 1)
                # header is like "data:image/png;base64"
                mime = header[len("data:") :].split(";")[0]
                parts.append({"type": "image", "image": payload, "mimeType": mime})
                continue
            except (IndexError, ValueError):
                # Fall through to plain URL handling
                pass
        parts.append({"type": "image", "image": src})
    return parts


# ── Language directive ────────────────────────────────────────────


def build_language_text(
    directive: str | None = None,
    scene_note: str | None = None,
) -> str:
    """Build language-instruction text from a course-level directive
    and an optional per-scene note.

    Mirrors upstream `buildLanguageText`. Used by scene content and
    action generators to inject into prompt templates.

    Returns empty string when both inputs are empty.
    """
    if not directive and not scene_note:
        return ""
    text = directive or ""
    if scene_note:
        if text:
            text += "\n\n"
        text += f"Additional language note for this scene: {scene_note}"
    return text
