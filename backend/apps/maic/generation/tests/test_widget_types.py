"""Unit tests for apps.maic.generation.widget_types (MAIC-602).

Each of the 5 widget types has:
  1. A "minimal-valid" sample that just hits the required fields.
  2. A "full-shape" sample exercising every optional field.

Plus error-path tests for the validate_widget_config gate:
  - mismatched type (e.g. config says "diagram" but caller said
    widget_type="simulation")
  - unknown widget_type
  - non-dict config
  - extra fields (extra="forbid" enforces strict matching against
    upstream's TS interface set)

The tests intentionally use raw dicts (not the Pydantic models) so
they verify the dict shape Phase 4's _extract_widget_config produces
will round-trip through the validator successfully.
"""
from __future__ import annotations

from apps.maic.generation.widget_types import (
    CodeConfig,
    DiagramConfig,
    GameConfig,
    SimulationConfig,
    Visualization3DConfig,
    validate_widget_config,
)


# ── Sample fixtures (raw dicts, the wire shape) ───────────────────────


SIMULATION_MIN: dict = {
    "type": "simulation",
    "concept": "Newton's Second Law",
    "description": "F=ma slider demo",
    "variables": [
        {"name": "mass", "label": "Mass", "min": 1, "max": 10, "default": 5},
    ],
}


SIMULATION_FULL: dict = {
    "type": "simulation",
    "concept": "Newton's Second Law",
    "description": "F=ma slider demo",
    "variables": [
        {
            "name": "mass", "label": "Mass (kg)", "min": 1, "max": 10,
            "default": 5, "unit": "kg", "step": 0.1,
        },
    ],
    "presets": [{"name": "Heavy", "variables": {"mass": 10}}],
    "teacherActions": [
        {"id": "a1", "type": "highlight", "target": "#mass-slider"},
    ],
}


DIAGRAM_MIN: dict = {
    "type": "diagram",
    "diagramType": "flowchart",
    "description": "Photosynthesis steps",
    "nodes": [{"id": "n1", "label": "CO2"}],
    "edges": [{"id": "e1", "from": "n1", "to": "n1"}],
}


DIAGRAM_FULL: dict = {
    "type": "diagram",
    "diagramType": "flowchart",
    "description": "Photosynthesis steps",
    "nodes": [
        {"id": "n1", "label": "CO2", "position": {"x": 0, "y": 0},
         "details": "atmospheric input", "type": "start"},
        {"id": "n2", "label": "Glucose", "type": "end"},
    ],
    "edges": [{"id": "e1", "from": "n1", "to": "n2", "label": "synthesis"}],
    "revealOrder": ["n1", "n2"],
    "teacherActions": [
        {"id": "a1", "type": "reveal", "target": "#n2"},
    ],
}


CODE_MIN: dict = {
    "type": "code",
    "language": "python",
    "description": "FizzBuzz",
    "starterCode": "def fizzbuzz(n): pass",
    "testCases": [
        {"id": "t1", "input": "3", "expected": "Fizz"},
    ],
    "hints": ["Check divisibility by 3"],
    "solution": "def fizzbuzz(n): return 'Fizz' if n%3==0 else str(n)",
}


GAME_MIN: dict = {
    "type": "game",
    "gameType": "quiz",
    "description": "Vocabulary quiz",
    "scoring": {"correctPoints": 10},
}


VIS3D_MIN: dict = {
    "type": "visualization3d",
    "visualizationType": "molecular",
    "description": "Water molecule",
    "objects": [
        {"id": "o1", "type": "sphere"},
    ],
}


VIS3D_FULL_HIERARCHY: dict = {
    "type": "visualization3d",
    "visualizationType": "solar",
    "description": "Solar system",
    "objects": [
        {
            "id": "sun",
            "type": "sphere",
            "name": "Sun",
            "position": {"x": 0, "y": 0, "z": 0},
            "scale": 5,  # number form
            "material": {"type": "emissive", "color": "#ffaa00"},
            "children": [
                {
                    "id": "earth",
                    "type": "sphere",
                    "scale": {"x": 1, "y": 1, "z": 1},  # vec3 form
                    "animation": {"type": "orbit", "speed": 1.0, "axis": "y"},
                },
            ],
        },
    ],
    "interactions": [
        {"type": "slider", "target": "earth", "param": "speed",
         "min": 0, "max": 5, "default": 1, "step": 0.1},
    ],
    "camera": {
        "position": {"x": 0, "y": 10, "z": 20},
        "target": {"x": 0, "y": 0, "z": 0},
        "fov": 60,
    },
    "lighting": {
        "ambient": {"color": "#404040", "intensity": 0.4},
        "directional": [
            {"color": "#ffffff", "intensity": 1.0,
             "position": {"x": 1, "y": 1, "z": 1}},
        ],
    },
    "presets": [
        {"name": "Closeup", "state": {"camera": "near"}},
    ],
}


# ── Happy path: minimal valid configs validate ────────────────────────


def test_simulation_minimal_validates():
    ok, reason = validate_widget_config("simulation", SIMULATION_MIN)
    assert ok, reason


def test_diagram_minimal_validates():
    ok, reason = validate_widget_config("diagram", DIAGRAM_MIN)
    assert ok, reason


def test_code_minimal_validates():
    ok, reason = validate_widget_config("code", CODE_MIN)
    assert ok, reason


def test_game_minimal_validates():
    ok, reason = validate_widget_config("game", GAME_MIN)
    assert ok, reason


def test_visualization3d_minimal_validates():
    ok, reason = validate_widget_config("visualization3d", VIS3D_MIN)
    assert ok, reason


# ── Full-shape configs (every optional field set) ─────────────────────


def test_simulation_full_shape_validates():
    ok, reason = validate_widget_config("simulation", SIMULATION_FULL)
    assert ok, reason


def test_diagram_full_shape_validates():
    """Validates the `from` keyword alias on DiagramEdge — wire shape
    uses `from`, Python attribute is `from_`."""
    ok, reason = validate_widget_config("diagram", DIAGRAM_FULL)
    assert ok, reason


def test_visualization3d_recursive_children_and_scale_union():
    """Exercises (a) recursive `children` on Visualization3DObject,
    (b) `scale: float | _Vec3` union, (c) nested camera/lighting/
    interactions/presets — all the shape complexity in one fixture."""
    ok, reason = validate_widget_config("visualization3d", VIS3D_FULL_HIERARCHY)
    assert ok, reason


# ── Type-mismatch detection ───────────────────────────────────────────


def test_mismatched_type_field_fails():
    """If the config's `type` doesn't match the requested widget_type,
    Pydantic's Literal validator catches it — exactly what we want
    for catching generation drift between widget_type routing and
    config payload."""
    bad = dict(SIMULATION_MIN, type="diagram")
    ok, reason = validate_widget_config("simulation", bad)
    assert not ok
    assert reason is not None
    assert "type" in reason.lower()


def test_unknown_widget_type_fails():
    ok, reason = validate_widget_config("teleporter", SIMULATION_MIN)
    assert not ok
    assert reason is not None
    assert "unknown widget_type" in reason


def test_non_dict_config_fails():
    ok, reason = validate_widget_config("simulation", "not a dict")  # type: ignore[arg-type]
    assert not ok
    assert reason is not None
    assert "expected dict" in reason


def test_extra_fields_rejected():
    """extra='forbid' enforces strict matching against upstream's TS
    interfaces. A future drift where we add a field client-side without
    upstream parity will be caught here."""
    bad = dict(SIMULATION_MIN, surprise_field="hello")
    ok, reason = validate_widget_config("simulation", bad)
    assert not ok
    assert reason is not None


def test_required_field_missing_fails():
    """Drop a required field; validator surfaces which one."""
    bad = {k: v for k, v in SIMULATION_MIN.items() if k != "concept"}
    ok, reason = validate_widget_config("simulation", bad)
    assert not ok
    assert reason is not None


# ── Pydantic models can also be instantiated directly (Python-side use) ─


def test_simulation_config_python_instance_round_trip():
    cfg = SimulationConfig.model_validate(SIMULATION_FULL)
    dumped = cfg.model_dump(by_alias=True, exclude_none=True)
    # Round-trip preserves the wire shape (with `from` not `from_`).
    ok, _ = validate_widget_config("simulation", dumped)
    assert ok


def test_diagram_edge_alias_round_trip():
    cfg = DiagramConfig.model_validate(DIAGRAM_FULL)
    dumped = cfg.model_dump(by_alias=True, exclude_none=True)
    # Critical: dumped form must use `from`, not `from_`.
    assert dumped["edges"][0].get("from") == "n1"
    assert "from_" not in dumped["edges"][0]


def test_code_config_required_arrays():
    cfg = CodeConfig.model_validate(CODE_MIN)
    assert len(cfg.testCases) == 1
    assert cfg.testCases[0].id == "t1"


def test_game_config_scoring_required():
    cfg = GameConfig.model_validate(GAME_MIN)
    assert cfg.scoring.correctPoints == 10


def test_visualization3d_config_full_round_trip():
    cfg = Visualization3DConfig.model_validate(VIS3D_FULL_HIERARCHY)
    # Recursive children resolve to typed objects
    earth = cfg.objects[0].children[0]  # type: ignore[index]
    assert earth.id == "earth"
    assert earth.animation is not None
    assert earth.animation.type == "orbit"
