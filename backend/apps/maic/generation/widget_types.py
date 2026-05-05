"""Widget Configuration Types for Ultra Interaction Mode.

Source: THU-MAIC/OpenMAIC lib/types/widgets.ts (lines 1-201)
        Lifted under ADR-001a (full OpenMAIC license ownership).

Pydantic port of upstream's 5 widget config interfaces. Used by
`_generate_widget_content` (scene_generator.py) to validate the
embedded `<script id="widget-config">` JSON extracted from generated
HTML. Validation is a quality gate — failure logs a warning and the
caller proceeds with the raw dict so the widget still renders. The
gate is for catching schema regressions in generation, not for
transforming wire data.

Field-for-field map of the upstream TS shapes. Adding a field here
without a corresponding upstream field is a smell — keep these in
lockstep.
"""
from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, ValidationError


# ── Base types ─────────────────────────────────────────────────────────


WidgetType = Literal["simulation", "diagram", "code", "game", "visualization3d"]


class TeacherAction(BaseModel):
    """One teacher-driven action that can be dispatched into the widget
    via postMessage at playback time. The 4 verb types here line up
    with the protocol actions in apps.maic.protocol.actions:
    widget_highlight / widget_annotation / widget_reveal / widget_setState
    plus the speech synthesis path which is handled at the agent layer."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["speech", "highlight", "annotation", "reveal", "setState"]
    target: str | None = None
    content: str | None = None
    state: dict[str, Any] | None = None
    label: str | None = None


# ── Simulation widget ──────────────────────────────────────────────────


class SimulationVariable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    label: str
    min: float
    max: float
    default: float
    unit: str | None = None
    step: float | None = None


class _SimulationPreset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    variables: dict[str, float]


class SimulationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["simulation"]
    concept: str
    description: str
    variables: list[SimulationVariable]
    presets: list[_SimulationPreset] | None = None
    teacherActions: list[TeacherAction] | None = None


# ── Diagram widget ─────────────────────────────────────────────────────


class _DiagramPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float


class DiagramNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    position: _DiagramPosition | None = None
    details: str | None = None
    type: Literal["default", "decision", "start", "end"] | None = None


class DiagramEdge(BaseModel):
    # `from` is a Python keyword — expose it as `from_` on the model
    # while preserving the wire-shape alias. populate_by_name lets
    # both names parse; alias_generator forces dump to emit `from`.
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        alias_generator=lambda name: "from" if name == "from_" else name,
    )

    id: str
    from_: str
    to: str
    label: str | None = None


class DiagramConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["diagram"]
    diagramType: Literal["flowchart", "mindmap", "hierarchy", "system"]
    description: str
    nodes: list[DiagramNode]
    edges: list[DiagramEdge]
    revealOrder: list[str] | None = None
    teacherActions: list[TeacherAction] | None = None


# ── Code widget ────────────────────────────────────────────────────────


class CodeTestCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    input: str
    expected: str
    description: str | None = None
    isHidden: bool | None = None


class CodeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["code"]
    language: Literal["python", "javascript", "typescript", "java", "cpp"]
    description: str
    starterCode: str
    testCases: list[CodeTestCase]
    hints: list[str]
    solution: str
    teacherActions: list[TeacherAction] | None = None


# ── Game widget ────────────────────────────────────────────────────────


class GameQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    question: str
    type: Literal["single", "multiple"]
    options: list[str]
    correct: int | list[int]
    explanation: str | None = None
    points: int | None = None


class _GameScoring(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correctPoints: float
    speedBonus: float | None = None
    comboMultiplier: float | None = None
    penalty: float | None = None


class _GameAchievement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    icon: str
    condition: str


class GameConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["game"]
    gameType: Literal["quiz", "puzzle", "strategy", "card"]
    description: str
    questions: list[GameQuestion] | None = None
    scoring: _GameScoring
    achievements: list[_GameAchievement] | None = None
    teacherActions: list[TeacherAction] | None = None


# ── 3D Visualization widget ────────────────────────────────────────────


class _Vec3(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    z: float


class _Visualization3DMaterial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["basic", "lambert", "phong", "standard", "emissive"]
    color: str | None = None
    emissive: str | None = None
    wireframe: bool | None = None
    transparent: bool | None = None
    opacity: float | None = None


class _Visualization3DAnimation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["orbit", "rotate", "bounce", "pulse"]
    speed: float | None = None
    axis: Literal["x", "y", "z"] | None = None


class Visualization3DObject(BaseModel):
    """Recursive — supports `children` for hierarchical scenes
    (e.g. solar systems, articulated anatomy)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["sphere", "box", "cylinder", "cone", "torus", "plane", "custom"]
    name: str | None = None
    position: _Vec3 | None = None
    rotation: _Vec3 | None = None
    # Upstream allows `scale: number | { x, y, z }`; mirror that union.
    scale: float | _Vec3 | None = None
    material: _Visualization3DMaterial | None = None
    animation: _Visualization3DAnimation | None = None
    children: "list[Visualization3DObject] | None" = None


Visualization3DObject.model_rebuild()


class Visualization3DInteraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["orbit", "zoom", "pan", "slider", "button", "toggle"]
    target: str | None = None
    label: str | None = None
    param: str | None = None
    min: float | None = None
    max: float | None = None
    default: float | None = None
    step: float | None = None


class _Visualization3DCamera(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: _Vec3 | None = None
    target: _Vec3 | None = None
    fov: float | None = None


class _Visualization3DAmbientLight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    color: str | None = None
    intensity: float | None = None


class _Visualization3DDirectionalLight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    color: str | None = None
    intensity: float | None = None
    position: _Vec3 | None = None


class _Visualization3DPointLight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    color: str | None = None
    intensity: float | None = None
    position: _Vec3 | None = None


class _Visualization3DLighting(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ambient: _Visualization3DAmbientLight | None = None
    directional: list[_Visualization3DDirectionalLight] | None = None
    point: list[_Visualization3DPointLight] | None = None


class _Visualization3DPreset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    state: dict[str, Any]


class Visualization3DConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["visualization3d"]
    visualizationType: Literal[
        "molecular", "solar", "anatomy", "geometry", "physics", "custom"
    ]
    description: str
    objects: list[Visualization3DObject]
    interactions: list[Visualization3DInteraction] | None = None
    camera: _Visualization3DCamera | None = None
    lighting: _Visualization3DLighting | None = None
    presets: list[_Visualization3DPreset] | None = None
    teacherActions: list[TeacherAction] | None = None


# ── Union ──────────────────────────────────────────────────────────────


WidgetConfig = Union[
    SimulationConfig,
    DiagramConfig,
    CodeConfig,
    GameConfig,
    Visualization3DConfig,
]


_CONFIG_BY_WIDGET_TYPE: dict[str, type[BaseModel]] = {
    "simulation": SimulationConfig,
    "diagram": DiagramConfig,
    "code": CodeConfig,
    "game": GameConfig,
    "visualization3d": Visualization3DConfig,
}


# ── Validation entry point ─────────────────────────────────────────────


def validate_widget_config(
    widget_type: str,
    config: dict[str, Any],
) -> tuple[bool, str | None]:
    """Validate an extracted widget-config dict against the matching
    Pydantic model.

    Returns:
        (True, None) on success.
        (False, reason) on failure — `reason` is a single-line summary
        suitable for logger.warning. The caller MUST keep using the
        raw `config` dict either way (graceful degrade — the widget
        renders even when the embedded JSON has schema drift).

    This is a QUALITY GATE, not a transform: we don't return the
    validated/normalized model. Callers stick with the wire dict so
    behavior stays identical to the pre-validation path on success
    AND failure.
    """
    if not isinstance(config, dict):
        return False, f"widget config is {type(config).__name__}, expected dict"

    model_cls = _CONFIG_BY_WIDGET_TYPE.get(widget_type)
    if model_cls is None:
        return False, f"unknown widget_type {widget_type!r}"

    try:
        model_cls.model_validate(config)
        return True, None
    except ValidationError as exc:
        # Compact summary — full pydantic error tree is verbose; the
        # first error's loc + msg is usually the most actionable signal
        # in production logs.
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []))
        msg = first.get("msg", str(exc))
        return False, f"{widget_type} config invalid at {loc!r}: {msg}"
