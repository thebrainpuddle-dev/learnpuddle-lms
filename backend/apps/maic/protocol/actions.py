"""Action Protocol — the 21-type vocabulary OpenMAIC uses for everything an
agent can do during a classroom: speak, draw on the whiteboard, annotate
slides, play video, trigger a discussion, manipulate interactive widgets.

Source (verbatim port):
    https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/types/action.ts
    /Volumes/CrucialX9/OpenMAIC/lib/types/action.ts (286 lines)

Two structural categories — the playback engine (Phase 2) dispatches
each action against the right renderer based on the type:

  Fire-and-forget (visual overlay; do NOT await — queue next immediately):
    spotlight, laser
  Synchronous (must complete before the next action — drives the
  agent_generate stream cadence):
    speech, play_video, wb_*, discussion, widget_*

Two slide-only actions (stripped server-side if scene type ≠ 'slide'):
    spotlight, laser

Whiteboard coordinate space: 1000 × 562 (16:9). Every wb_* action with
x/y/width/height/startX/startY/endX/endY uses this exact frame; the
frontend renderer (Phase 2 MAIC-210) scales it to the actual canvas
size at render time.

Pydantic discriminated union via the `type` literal — `validate_action()`
parses untrusted input (LLM output, WS payloads) and raises
MaicProtocolError on shape violation. The union is exported as
`Action` for type annotations and `AnyAction` (the TypeAdapter) for
runtime parsing.
"""
from __future__ import annotations

from typing import Annotated, Any, Final, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from apps.maic.exceptions import MaicProtocolError


# ── Shared base ────────────────────────────────────────────────────────


class _ActionBase(BaseModel):
    """Common fields on every action. Mirrors upstream `ActionBase` at
    lib/types/action.ts:14-18.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(..., description="Unique action ID within the scene.")
    title: str | None = Field(default=None, description="Optional title for UI display.")
    description: str | None = Field(
        default=None, description="Optional human-readable description."
    )


# ── Fire-and-forget visual overlays (slide-only) ──────────────────────


class SpotlightAction(_ActionBase):
    """Focus the slide on a single element; dim everything else."""

    type: Literal["spotlight"] = "spotlight"
    elementId: str = Field(..., description="ID of the slide element to spotlight.")
    dimOpacity: float | None = Field(
        default=None, ge=0, le=1, description="0..1 dim opacity for non-targets (default 0.5)."
    )


class LaserAction(_ActionBase):
    """Animated laser pointer overlay on a single slide element."""

    type: Literal["laser"] = "laser"
    elementId: str
    color: str | None = Field(
        default=None, description="CSS color string, default '#ff0000'."
    )


# ── Speech ─────────────────────────────────────────────────────────────


class SpeechAction(_ActionBase):
    """Teacher narration. Synchronous — playback awaits TTS completion."""

    type: Literal["speech"] = "speech"
    text: str = Field(..., min_length=1)
    audioId: str | None = Field(default=None, description="TTS audio cache key.")
    audioUrl: str | None = Field(default=None, description="Server-generated TTS audio URL.")
    voice: str | None = None
    speed: float | None = Field(default=None, gt=0, le=4, description="Default 1.0.")


# ── Whiteboard ─────────────────────────────────────────────────────────


class WbOpenAction(_ActionBase):
    type: Literal["wb_open"] = "wb_open"


class WbCloseAction(_ActionBase):
    type: Literal["wb_close"] = "wb_close"


class WbClearAction(_ActionBase):
    type: Literal["wb_clear"] = "wb_clear"


class WbDeleteAction(_ActionBase):
    type: Literal["wb_delete"] = "wb_delete"
    elementId: str = Field(..., description="ID of the previously drawn element to remove.")


class WbDrawTextAction(_ActionBase):
    type: Literal["wb_draw_text"] = "wb_draw_text"
    elementId: str | None = None
    content: str = Field(..., description="HTML or plain text.")
    x: float
    y: float
    width: float | None = Field(default=None, gt=0, description="Default 400.")
    height: float | None = Field(default=None, gt=0, description="Default 100.")
    fontSize: float | None = Field(default=None, gt=0, description="Default 18.")
    color: str | None = Field(default=None, description="Default '#333333'.")


class WbDrawShapeAction(_ActionBase):
    type: Literal["wb_draw_shape"] = "wb_draw_shape"
    elementId: str | None = None
    shape: Literal["rectangle", "circle", "triangle"]
    x: float
    y: float
    width: float = Field(..., gt=0)
    height: float = Field(..., gt=0)
    fillColor: str | None = Field(default=None, description="Default '#5b9bd5'.")


class _WbChartData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    labels: list[str]
    legends: list[str]
    series: list[list[float]]


class WbDrawChartAction(_ActionBase):
    type: Literal["wb_draw_chart"] = "wb_draw_chart"
    elementId: str | None = None
    chartType: Literal["bar", "column", "line", "pie", "ring", "area", "radar", "scatter"]
    x: float
    y: float
    width: float = Field(..., gt=0)
    height: float = Field(..., gt=0)
    data: _WbChartData
    themeColors: list[str] | None = None


class WbDrawLatexAction(_ActionBase):
    type: Literal["wb_draw_latex"] = "wb_draw_latex"
    elementId: str | None = None
    latex: str = Field(..., min_length=1)
    x: float
    y: float
    width: float | None = Field(default=None, gt=0, description="Default 400.")
    height: float | None = Field(default=None, gt=0, description="Auto-computed if None.")
    color: str | None = Field(default=None, description="Default '#000000'.")


class WbDrawTableAction(_ActionBase):
    type: Literal["wb_draw_table"] = "wb_draw_table"
    elementId: str | None = None
    x: float
    y: float
    width: float = Field(..., gt=0)
    height: float = Field(..., gt=0)
    data: list[list[str]] = Field(
        ..., description="2D string array; first row is the header."
    )
    outline: dict[str, Any] | None = Field(
        default=None, description="{ width, style, color }."
    )
    theme: dict[str, Any] | None = Field(default=None, description="{ color }.")


class WbDrawLineAction(_ActionBase):
    """Line/arrow on the whiteboard. Coords in the 1000×562 frame."""

    type: Literal["wb_draw_line"] = "wb_draw_line"
    elementId: str | None = None
    startX: float = Field(..., ge=0, le=1000)
    startY: float = Field(..., ge=0, le=562)
    endX: float = Field(..., ge=0, le=1000)
    endY: float = Field(..., ge=0, le=562)
    color: str | None = Field(default=None, description="Default '#333333'.")
    width: float | None = Field(default=None, gt=0, description="Default 2.")
    style: Literal["solid", "dashed"] | None = Field(default=None, description="Default 'solid'.")
    points: tuple[Literal["", "arrow"], Literal["", "arrow"]] | None = Field(
        default=None,
        description=(
            "Endpoint markers. Default ('', ''). Permitted upstream variants: "
            "('', 'arrow'), ('arrow', ''), ('arrow', 'arrow')."
        ),
    )


class WbDrawCodeAction(_ActionBase):
    type: Literal["wb_draw_code"] = "wb_draw_code"
    elementId: str | None = None
    language: str = Field(..., description="lowlight language id (e.g. 'python').")
    code: str = Field(..., description="Raw code; lines separated by \\n.")
    x: float
    y: float
    width: float | None = Field(default=None, gt=0, description="Default 500.")
    height: float | None = Field(default=None, gt=0, description="Default 300.")
    fileName: str | None = None


class WbEditCodeAction(_ActionBase):
    """Line-level edit of a previously drawn code block."""

    type: Literal["wb_edit_code"] = "wb_edit_code"
    elementId: str = Field(..., description="Target wb_draw_code block ID.")
    operation: Literal["insert_after", "insert_before", "delete_lines", "replace_lines"]
    lineId: str | None = Field(default=None, description="Reference line ID for insert ops.")
    lineIds: list[str] | None = Field(
        default=None, description="Target line IDs for delete/replace ops."
    )
    content: str | None = Field(
        default=None, description="New content for insert/replace. Lines separated by \\n."
    )


# ── Media ──────────────────────────────────────────────────────────────


class PlayVideoAction(_ActionBase):
    type: Literal["play_video"] = "play_video"
    elementId: str = Field(..., description="ID of the slide video element to play.")


# ── Discussion ─────────────────────────────────────────────────────────


class DiscussionAction(_ActionBase):
    """Trigger a roundtable discussion. Frontend playback engine waits
    3 s then surfaces the ProactiveCard; on user-confirm enters live
    mode (Phase 3, MAIC-411)."""

    type: Literal["discussion"] = "discussion"
    topic: str = Field(..., min_length=1)
    prompt: str | None = Field(default=None)
    agentId: str | None = Field(
        default=None, description="If set, restricts the discussion to this agent."
    )


# ── Widget interaction ────────────────────────────────────────────────


class WidgetHighlightAction(_ActionBase):
    type: Literal["widget_highlight"] = "widget_highlight"
    target: str = Field(..., description="CSS selector or element ID inside the widget iframe.")
    content: str | None = Field(
        default=None, description="Speech text to accompany the highlight."
    )


class WidgetSetStateAction(_ActionBase):
    type: Literal["widget_setState"] = "widget_setState"
    state: dict[str, Any]
    content: str | None = None


class WidgetAnnotationAction(_ActionBase):
    type: Literal["widget_annotation"] = "widget_annotation"
    target: str
    content: str | None = None


class WidgetRevealAction(_ActionBase):
    type: Literal["widget_reveal"] = "widget_reveal"
    target: str
    content: str | None = None


# ── Discriminated union ────────────────────────────────────────────────


Action = Annotated[
    Union[
        SpotlightAction,
        LaserAction,
        SpeechAction,
        WbOpenAction,
        WbCloseAction,
        WbClearAction,
        WbDeleteAction,
        WbDrawTextAction,
        WbDrawShapeAction,
        WbDrawChartAction,
        WbDrawLatexAction,
        WbDrawTableAction,
        WbDrawLineAction,
        WbDrawCodeAction,
        WbEditCodeAction,
        PlayVideoAction,
        DiscussionAction,
        WidgetHighlightAction,
        WidgetSetStateAction,
        WidgetAnnotationAction,
        WidgetRevealAction,
    ],
    Field(discriminator="type"),
]

# TypeAdapter for runtime parsing of untrusted JSON.
_ActionAdapter: Final = TypeAdapter(Action)


# ── Categorization (mirror upstream constants) ─────────────────────────

ActionTypeLiteral = Literal[
    "spotlight", "laser", "speech",
    "wb_open", "wb_close", "wb_clear", "wb_delete",
    "wb_draw_text", "wb_draw_shape", "wb_draw_chart",
    "wb_draw_latex", "wb_draw_table", "wb_draw_line",
    "wb_draw_code", "wb_edit_code",
    "play_video", "discussion",
    "widget_highlight", "widget_setState", "widget_annotation", "widget_reveal",
]

ALL_ACTION_TYPES: Final[frozenset[str]] = frozenset({
    "spotlight", "laser", "speech",
    "wb_open", "wb_close", "wb_clear", "wb_delete",
    "wb_draw_text", "wb_draw_shape", "wb_draw_chart",
    "wb_draw_latex", "wb_draw_table", "wb_draw_line",
    "wb_draw_code", "wb_edit_code",
    "play_video", "discussion",
    "widget_highlight", "widget_setState", "widget_annotation", "widget_reveal",
})

# upstream lib/types/action.ts:245
FIRE_AND_FORGET_ACTIONS: Final[frozenset[str]] = frozenset({"spotlight", "laser"})

# upstream lib/types/action.ts:248
SLIDE_ONLY_ACTIONS: Final[frozenset[str]] = frozenset({"spotlight", "laser"})

# upstream lib/types/action.ts:251-271
SYNC_ACTIONS: Final[frozenset[str]] = ALL_ACTION_TYPES - FIRE_AND_FORGET_ACTIONS

assert ALL_ACTION_TYPES == FIRE_AND_FORGET_ACTIONS | SYNC_ACTIONS, (
    "ALL_ACTION_TYPES must be the disjoint union of FIRE_AND_FORGET + SYNC"
)
assert len(ALL_ACTION_TYPES) == 21, f"expected 21 action types, got {len(ALL_ACTION_TYPES)}"


# ── Public parsing API ─────────────────────────────────────────────────


def validate_action(payload: Any) -> Any:
    """Parse one Action from a dict (or already-parsed Pydantic model).

    Raises:
        MaicProtocolError: structural violation, unknown type, or
            constraint failure (e.g. negative width, out-of-range coords).
    """
    try:
        return _ActionAdapter.validate_python(payload)
    except ValidationError as exc:
        raise MaicProtocolError(
            f"action validation failed: {exc.errors(include_url=False)}"
        ) from exc


def validate_actions(payloads: list[Any]) -> list[Any]:
    """Parse a list of Actions; on first failure raises MaicProtocolError
    with the failing index and message preserved.
    """
    out = []
    for idx, p in enumerate(payloads):
        try:
            out.append(validate_action(p))
        except MaicProtocolError as exc:
            raise MaicProtocolError(f"actions[{idx}]: {exc}") from exc
    return out


def filter_for_scene(action_types: list[str], scene_type: str | None) -> list[str]:
    """Strip slide-only actions (`spotlight`, `laser`) when the current
    scene is not a slide. Mirrors upstream tool-schemas.ts (72 lines)
    `getEffectiveActions(allowedActions, sceneType)`.
    """
    if scene_type == "slide":
        return [a for a in action_types if a in ALL_ACTION_TYPES]
    return [a for a in action_types if a in ALL_ACTION_TYPES and a not in SLIDE_ONLY_ACTIONS]


def export_json_schema() -> dict[str, Any]:
    """Return the JSON Schema for the discriminated `Action` union.
    Used by frontend codegen — a future ticket may snapshot this to
    `frontend/src/lib/maic/actions.schema.json` for typed parsing
    on the client side. Phase 1 ships hand-mirrored TS types instead
    (see frontend/src/hooks/useMaicClassroomChannelV2.ts).
    """
    return _ActionAdapter.json_schema()
