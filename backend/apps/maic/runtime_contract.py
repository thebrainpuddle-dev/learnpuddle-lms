"""Canonical runtime contract for persisted AI Classroom scenes.

OpenMAIC works because generated content is forced through one stage/scene/
action model before playback. LearnPuddle has extra SaaS boundaries
(tenant-scoped rows, Celery image fill, authenticated media, teacher/student
routes), so this module is the backend gate that says a materialized classroom
is actually playable by the React runtime.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

from apps.courses.maic_media_safety import should_strip_generated_image_src
from apps.maic.protocol import ALL_ACTION_TYPES, SLIDE_ONLY_ACTIONS


CANONICAL_CANVAS_WIDTH = 1000.0
CANONICAL_CANVAS_RATIO = 0.5625
CANONICAL_CANVAS_HEIGHT = CANONICAL_CANVAS_WIDTH * CANONICAL_CANVAS_RATIO

ALLOWED_SCENE_TYPES = frozenset({"slide", "quiz", "interactive", "pbl"})
ALLOWED_ELEMENT_TYPES = frozenset({
    "text",
    "image",
    "shape",
    "chart",
    "latex",
    "code",
    "table",
    "video",
})

# Frontend playback supports a small platform layer on top of the 21 upstream
# OpenMAIC actions. Keeping the union here prevents backend validation from
# drifting behind the actual SaaS runtime.
PLATFORM_ACTION_TYPES = frozenset({"highlight", "pause", "transition"})
RUNTIME_ACTION_TYPES = ALL_ACTION_TYPES | PLATFORM_ACTION_TYPES
SLIDE_TARGET_ACTIONS = frozenset({"spotlight", "laser", "highlight", "play_video"})
DISCUSSION_SESSION_TYPES = frozenset({"classroom", "qa", "roundtable"})
DISCUSSION_TRIGGER_MODES = frozenset({"auto", "manual"})

PROMPT_LEAK_MARKERS = (
    "aspect ratio 16:9",
    "canvas size",
    "do not wrap your json",
    "output pure json",
    "provided generated image ids",
)


@dataclass(frozen=True)
class RuntimeContractIssue:
    severity: str
    code: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }


@dataclass
class RuntimeContractReport:
    errors: list[RuntimeContractIssue] = field(default_factory=list)
    warnings: list[RuntimeContractIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def add_error(self, code: str, path: str, message: str) -> None:
        self.errors.append(RuntimeContractIssue("error", code, path, message))

    def add_warning(self, code: str, path: str, message: str) -> None:
        self.warnings.append(RuntimeContractIssue("warning", code, path, message))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "maic_runtime_contract_v1",
            "valid": self.is_valid,
            "errorCount": len(self.errors),
            "warningCount": len(self.warnings),
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
        }

    def summary(self, limit: int = 4) -> str:
        issues = self.errors[:limit]
        rendered = "; ".join(
            f"{issue.path}: {issue.code} ({issue.message})"
            for issue in issues
        )
        if len(self.errors) > limit:
            rendered += f"; +{len(self.errors) - limit} more"
        return rendered or "runtime contract valid"


def validate_classroom_runtime_contract(
    scenes: Any,
    agents: Any,
    *,
    allow_unresolved_images: bool = True,
) -> RuntimeContractReport:
    """Validate the exact payload persisted for playback.

    This intentionally validates cross-field invariants that plain JSON schema
    cannot catch: spotlight targets must exist, discussion agents must be in the
    roster, slide elements must fit their canvas, and placeholder image URLs
    cannot cross the persistence boundary.
    """
    report = RuntimeContractReport()
    if not isinstance(scenes, list) or not scenes:
        report.add_error("scenes.empty", "scenes", "Classroom must contain at least one scene.")
        return report

    valid_agent_ids = _agent_ids(agents)
    if not valid_agent_ids:
        report.add_warning("agents.empty", "agents", "No runtime agents were supplied.")

    seen_scene_ids: set[str] = set()
    for scene_index, scene in enumerate(scenes):
        scene_path = f"scenes[{scene_index}]"
        if not isinstance(scene, dict):
            report.add_error("scene.type", scene_path, "Scene must be an object.")
            continue

        scene_id = _clean_id(scene.get("id"))
        if not scene_id:
            report.add_error("scene.id", f"{scene_path}.id", "Scene id is required.")
        elif scene_id in seen_scene_ids:
            report.add_error("scene.id.duplicate", f"{scene_path}.id", f"Duplicate scene id {scene_id}.")
        else:
            seen_scene_ids.add(scene_id)

        scene_type = str(scene.get("type") or "").strip().lower()
        if scene_type not in ALLOWED_SCENE_TYPES:
            report.add_error(
                "scene.type.unsupported",
                f"{scene_path}.type",
                f"Unsupported scene type {scene_type or '<empty>'}.",
            )

        slides = _slides_for_scene(scene)
        element_ids, element_types = _validate_slides(
            report,
            scene_path,
            scene_type,
            slides,
            allow_unresolved_images=allow_unresolved_images,
        )
        _validate_actions(
            report,
            scene_path,
            scene_type,
            scene.get("actions"),
            valid_agent_ids,
            element_ids,
            element_types,
            len(slides),
        )

    return report


def require_valid_classroom_runtime_contract(
    scenes: Any,
    agents: Any,
    *,
    allow_unresolved_images: bool = True,
) -> RuntimeContractReport:
    report = validate_classroom_runtime_contract(
        scenes,
        agents,
        allow_unresolved_images=allow_unresolved_images,
    )
    if not report.is_valid:
        raise ValueError(f"MAIC runtime contract failed: {report.summary()}")
    return report


def _validate_slides(
    report: RuntimeContractReport,
    scene_path: str,
    scene_type: str,
    slides: list[dict[str, Any]],
    *,
    allow_unresolved_images: bool,
) -> tuple[set[str], dict[str, str]]:
    element_ids: set[str] = set()
    element_types: dict[str, str] = {}
    if scene_type == "slide" and not slides:
        report.add_error("slide.missing", f"{scene_path}.content", "Slide scene has no slide canvas.")
        return element_ids, element_types

    seen_slide_ids: set[str] = set()
    for slide_index, slide in enumerate(slides):
        slide_path = f"{scene_path}.slides[{slide_index}]"
        slide_id = _clean_id(slide.get("id"))
        if not slide_id:
            report.add_error("slide.id", f"{slide_path}.id", "Slide id is required.")
        elif slide_id in seen_slide_ids:
            report.add_error("slide.id.duplicate", f"{slide_path}.id", f"Duplicate slide id {slide_id}.")
        else:
            seen_slide_ids.add(slide_id)

        width = _number(slide.get("canvasWidth") or slide.get("viewportSize"))
        height = _number(slide.get("canvasHeight"))
        ratio = _number(slide.get("viewportRatio"))
        if height is None and width is not None and ratio is not None:
            height = width * ratio
        if width is None or height is None or width <= 0 or height <= 0:
            report.add_error(
                "slide.canvas",
                slide_path,
                "Slide must declare a positive canvasWidth/canvasHeight or viewportSize/viewportRatio.",
            )
            width = CANONICAL_CANVAS_WIDTH
            height = CANONICAL_CANVAS_HEIGHT

        elements = slide.get("elements")
        if not isinstance(elements, list):
            report.add_error("slide.elements", f"{slide_path}.elements", "Slide elements must be an array.")
            continue
        if scene_type == "slide" and not elements:
            report.add_error("slide.elements.empty", f"{slide_path}.elements", "Slide scene must contain renderable elements.")
            continue

        seen_element_ids: set[str] = set()
        for element_index, element in enumerate(elements):
            element_path = f"{slide_path}.elements[{element_index}]"
            if not isinstance(element, dict):
                report.add_error("element.type", element_path, "Element must be an object.")
                continue
            element_id = _clean_id(element.get("id"))
            if not element_id:
                report.add_error("element.id", f"{element_path}.id", "Element id is required.")
                continue
            if element_id in seen_element_ids:
                report.add_error(
                    "element.id.duplicate",
                    f"{element_path}.id",
                    f"Duplicate element id {element_id} in slide.",
                )
            seen_element_ids.add(element_id)
            element_ids.add(element_id)

            element_type = str(element.get("type") or "").strip().lower()
            element_types[element_id] = element_type
            if element_type not in ALLOWED_ELEMENT_TYPES:
                report.add_error(
                    "element.type.unsupported",
                    f"{element_path}.type",
                    f"Unsupported element type {element_type or '<empty>'}.",
                )

            _validate_element_bounds(report, element_path, element, width, height)
            if element_type == "text" and _contains_prompt_leak(element.get("content")):
                report.add_error(
                    "element.prompt_leak",
                    f"{element_path}.content",
                    "Prompt instructions leaked into a text element.",
                )
            if element_type == "image":
                _validate_image_element(
                    report,
                    element_path,
                    element,
                    allow_unresolved_images=allow_unresolved_images,
                )

    return element_ids, element_types


def _validate_element_bounds(
    report: RuntimeContractReport,
    element_path: str,
    element: dict[str, Any],
    canvas_width: float,
    canvas_height: float,
) -> None:
    x = _number(element.get("x", element.get("left")))
    y = _number(element.get("y", element.get("top")))
    width = _number(element.get("width"))
    height = _number(element.get("height"))
    if None in {x, y, width, height}:
        report.add_error("element.bounds.missing", element_path, "Element needs numeric x/y/width/height.")
        return
    assert x is not None and y is not None and width is not None and height is not None
    if width <= 0 or height <= 0:
        report.add_error("element.bounds.size", element_path, "Element width/height must be positive.")
        return
    tolerance = 0.5
    if x < -tolerance or y < -tolerance or x + width > canvas_width + tolerance or y + height > canvas_height + tolerance:
        report.add_error(
            "element.bounds.canvas",
            element_path,
            "Element must fit inside the declared slide canvas.",
        )


def _validate_image_element(
    report: RuntimeContractReport,
    element_path: str,
    element: dict[str, Any],
    *,
    allow_unresolved_images: bool,
) -> None:
    src = str(element.get("src") or "").strip()
    content = str(element.get("content") or "").strip()
    meta = element.get("meta")
    provider_disabled = isinstance(meta, dict) and meta.get("imageProviderDisabled") is True
    if src and should_strip_generated_image_src(src, allow_bare_ids=True):
        report.add_error("image.src.placeholder", f"{element_path}.src", "Image src is not a real tenant-safe media URL.")
    if content and should_strip_generated_image_src(content, allow_bare_ids=True):
        report.add_error(
            "image.content.placeholder",
            f"{element_path}.content",
            "Image content contains a placeholder URL.",
        )
    if not src and not content and not provider_disabled:
        add = report.add_warning if allow_unresolved_images else report.add_error
        add(
            "image.unresolved",
            element_path,
            "Image element has no src/content and no provider-disabled marker.",
        )


def _validate_actions(
    report: RuntimeContractReport,
    scene_path: str,
    scene_type: str,
    actions: Any,
    valid_agent_ids: set[str],
    element_ids: set[str],
    element_types: dict[str, str],
    slide_count: int,
) -> None:
    if actions is None:
        report.add_warning("actions.missing", f"{scene_path}.actions", "Scene has no actions array.")
        return
    if not isinstance(actions, list):
        report.add_error("actions.type", f"{scene_path}.actions", "Actions must be an array.")
        return

    seen_action_ids: set[str] = set()
    speech_count = 0
    for action_index, action in enumerate(actions):
        action_path = f"{scene_path}.actions[{action_index}]"
        if not isinstance(action, dict):
            report.add_error("action.type", action_path, "Action must be an object.")
            continue
        action_type = str(action.get("type") or "").strip()
        if action_type not in RUNTIME_ACTION_TYPES:
            report.add_error("action.type.unsupported", f"{action_path}.type", f"Unsupported action type {action_type or '<empty>'}.")
            continue

        action_id = _clean_id(action.get("id"))
        if not action_id:
            report.add_error("action.id", f"{action_path}.id", "Action id is required.")
        elif action_id in seen_action_ids:
            report.add_error("action.id.duplicate", f"{action_path}.id", f"Duplicate action id {action_id}.")
        else:
            seen_action_ids.add(action_id)

        if action_type in SLIDE_ONLY_ACTIONS and scene_type != "slide":
            report.add_error("action.slide_only", action_path, f"{action_type} can only run in slide scenes.")
        if action_type in SLIDE_TARGET_ACTIONS:
            target_id = _clean_id(action.get("elementId"))
            if not target_id or target_id not in element_ids:
                report.add_error("action.target", f"{action_path}.elementId", f"{action_type} target must exist in the scene slide.")
            if action_type == "play_video" and target_id and element_types.get(target_id) != "video":
                report.add_warning("action.video_target", f"{action_path}.elementId", "play_video target is not a video element.")

        if action_type == "speech":
            speech_count += 1
            if not str(action.get("text") or "").strip():
                report.add_error("speech.text", f"{action_path}.text", "Speech action needs non-empty text.")
            _validate_action_agent(report, action_path, action.get("agentId"), valid_agent_ids, required=True)
            duration_ms = action.get("durationMs")
            if duration_ms is not None and (_number(duration_ms) is None or _number(duration_ms) <= 0):
                report.add_error("speech.duration", f"{action_path}.durationMs", "durationMs must be positive when supplied.")

        if action_type == "discussion":
            if action_index != len(actions) - 1:
                report.add_error("discussion.order", action_path, "Discussion actions must be the final action in a scene.")
            if not str(action.get("topic") or "").strip():
                report.add_error("discussion.topic", f"{action_path}.topic", "Discussion topic is required.")
            _validate_discussion_agents(report, action_path, action, valid_agent_ids)
            if action.get("sessionType") not in DISCUSSION_SESSION_TYPES:
                report.add_error("discussion.session", f"{action_path}.sessionType", "Invalid discussion sessionType.")
            if action.get("triggerMode") not in DISCUSSION_TRIGGER_MODES:
                report.add_error("discussion.trigger", f"{action_path}.triggerMode", "Invalid discussion triggerMode.")

        if action_type == "transition":
            slide_index = action.get("slideIndex")
            if slide_index is not None:
                try:
                    resolved_index = int(slide_index)
                except (TypeError, ValueError):
                    report.add_error("transition.slide_index", f"{action_path}.slideIndex", "slideIndex must be an integer.")
                else:
                    if resolved_index < 0 or resolved_index >= max(slide_count, 1):
                        report.add_error("transition.slide_index", f"{action_path}.slideIndex", "slideIndex is outside this scene's slides.")

        if action_type == "pause":
            duration = _number(action.get("duration"))
            if duration is None or duration < 0:
                report.add_error("pause.duration", f"{action_path}.duration", "Pause duration must be a non-negative number.")

    if speech_count == 0:
        report.add_warning("speech.missing", f"{scene_path}.actions", "Scene has no speech actions.")
    if speech_count > 10:
        report.add_warning("speech.excessive", f"{scene_path}.actions", "Scene has more than 10 speech actions.")


def _validate_action_agent(
    report: RuntimeContractReport,
    action_path: str,
    agent_id: Any,
    valid_agent_ids: set[str],
    *,
    required: bool,
) -> None:
    clean = _clean_id(agent_id)
    if not clean:
        if required and valid_agent_ids:
            report.add_error("agent.missing", f"{action_path}.agentId", "Action needs an agentId.")
        return
    if valid_agent_ids and clean not in valid_agent_ids:
        report.add_error("agent.unknown", f"{action_path}.agentId", f"Unknown agentId {clean}.")


def _validate_discussion_agents(
    report: RuntimeContractReport,
    action_path: str,
    action: dict[str, Any],
    valid_agent_ids: set[str],
) -> None:
    _validate_action_agent(report, action_path, action.get("agentId"), valid_agent_ids, required=False)
    agent_ids = action.get("agentIds")
    if not isinstance(agent_ids, list) or not agent_ids:
        report.add_error("discussion.agents", f"{action_path}.agentIds", "Discussion needs at least one agentId in agentIds.")
        return
    for index, agent_id in enumerate(agent_ids):
        _validate_action_agent(
            report,
            f"{action_path}.agentIds[{index}]",
            agent_id,
            valid_agent_ids,
            required=True,
        )


def _slides_for_scene(scene: dict[str, Any]) -> list[dict[str, Any]]:
    content = scene.get("content")
    if not isinstance(content, dict) or content.get("type") != "slide":
        return []
    raw_slides = content.get("slides")
    if isinstance(raw_slides, list):
        return [slide for slide in raw_slides if isinstance(slide, dict)]
    canvas = content.get("canvas")
    if isinstance(canvas, dict):
        return [canvas]
    if isinstance(content.get("elements"), list):
        return [content]
    return []


def _agent_ids(agents: Any) -> set[str]:
    if not isinstance(agents, list):
        return set()
    return {
        str(agent.get("id")).strip()
        for agent in agents
        if isinstance(agent, dict) and str(agent.get("id") or "").strip()
    }


def _clean_id(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _contains_prompt_leak(value: Any) -> bool:
    text = str(value or "").lower()
    return any(marker in text for marker in PROMPT_LEAK_MARKERS)
