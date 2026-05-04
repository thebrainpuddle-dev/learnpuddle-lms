"""Type definitions for the generation pipeline.

Direct port of upstream `lib/generation/pipeline-types.ts` (72 lines).

Source:
    https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/generation/pipeline-types.ts
    /Volumes/CrucialX9/OpenMAIC/lib/generation/pipeline-types.ts

Phase 4 ports the data shapes that flow through the pipeline:
    - AgentInfo:                lightweight agent passed to generation
    - SceneGenerationContext:   cross-page context for speech coherence
    - GenerationResult:         {success, data, error} envelope
    - GenerationCallbacks:      onProgress / onStageComplete / onError
    - GeneratedSlideData:       AI-generated slide JSON shape
    - SceneOutline:             outline rows from Stage 1 → Stage 2

We use `TypedDict` rather than Pydantic for the cross-pipeline shapes:
    - The pipeline receives untrusted LLM JSON; Pydantic validation is
      done explicitly via `parseJsonResponse` (action_parser, etc.).
    - TypedDict gives us static-type checks without runtime overhead.

Pydantic IS used elsewhere (the WS protocol's Action models in
`apps.maic.protocol.actions`); this module's intermediate shapes feed
into those validators downstream.
"""
from __future__ import annotations

from typing import Any, Callable, Generic, Literal, NotRequired, TypedDict, TypeVar


# ── Agent info ─────────────────────────────────────────────────────


class AgentInfo(TypedDict):
    """Lightweight agent info passed to the generation pipeline.

    Mirrors `pipeline-types.ts:AgentInfo`. Distinct from the richer
    `apps.maic.orchestration.registry.AgentConfig` — generation only
    needs id/name/role/persona to format prompts; full registry data
    (allowedActions, voiceConfig, etc.) is not required here.
    """

    id: str
    name: str
    role: str
    persona: NotRequired[str]


# ── Cross-page context ─────────────────────────────────────────────


class SceneGenerationContext(TypedDict):
    """Cross-page context for maintaining speech coherence across scenes.

    Mirrors `pipeline-types.ts:SceneGenerationContext`. Populated by
    the pipeline runner as scenes are generated; passed to each
    scene's content prompt so the LLM avoids repeating intros and
    references prior topics naturally.
    """

    pageIndex: int  # 1-based
    totalPages: int
    allTitles: list[str]
    previousSpeeches: list[str]  # speech text from the prev page only


# ── Generated slide JSON shape ────────────────────────────────────


class GeneratedSlideData(TypedDict, total=False):
    """AI-generated slide JSON parsed from the slide-content LLM call.

    Mirrors `pipeline-types.ts:GeneratedSlideData`. The pipeline parses
    the LLM's response into this shape via `json_repair.parse_json_response`
    before assembling the final Scene.
    """

    elements: list[dict[str, Any]]  # see lib/types/slide.ts for element variants
    background: dict[str, Any]  # solid | gradient
    remark: str  # speaker notes


# ── GenerationResult envelope ─────────────────────────────────────


T = TypeVar("T")


class GenerationResult(TypedDict, Generic[T], total=False):
    """{success, data?, error?} return shape used by every pipeline
    stage. Success implies `data` is set; failure implies `error` is.
    """

    success: bool
    data: T
    error: str


# ── GenerationCallbacks ────────────────────────────────────────────


class GenerationProgress(TypedDict, total=False):
    """Progress event emitted during generation. Mirrors upstream
    `lib/types/generation.GenerationProgress` (the `@/lib/types/generation`
    import in pipeline-types.ts:5).

    Phase 4 emits these into Celery's task-state + the WS consumer
    relays them to the client via channel-layer group_send.
    """

    stage: Literal[1, 2, 3]
    completed: int
    total: int
    message: NotRequired[str]


class GenerationCallbacks(TypedDict, total=False):
    """Optional callbacks the caller installs on the pipeline runner.

    All optional. The pipeline runner never throws if a callback is
    unset (mirrors upstream's optional-chaining shape).
    """

    onProgress: Callable[[GenerationProgress], None]
    onStageComplete: Callable[[Literal[1, 2, 3], Any], None]
    onError: Callable[[str], None]


# ── AI call function signature ─────────────────────────────────────


# Upstream's `AICallFn = (system, user, images?) => Promise<string>`.
# Phase 4 ships text-only (no images) — the visionImages path is
# DEFERRED to Phase 5+ per the plan. The third positional is kept in
# the signature so future extensions don't break callers.
AICallFn = Callable[..., Any]  # async (system: str, user: str, images: list | None = None) -> str


# ── SceneOutline ───────────────────────────────────────────────────


class SceneOutline(TypedDict, total=False):
    """A single scene outline row from Stage 1.

    The full upstream interface lives at `lib/types/scene.ts`; this
    TypedDict captures the fields the generation pipeline reads.

    Stage 2's scene_generator dispatches on `type` ('slide' | 'quiz' |
    'pbl' | 'interactive') and, for 'interactive', on the inner
    `interactiveType` ('simulation' | 'diagram' | 'code' | 'game' |
    'visualization3d').
    """

    id: str
    title: str
    type: Literal["slide", "quiz", "pbl", "interactive"]
    interactiveType: Literal["simulation", "diagram", "code", "game", "visualization3d"]
    description: str
    duration: int  # estimated minutes
    teacherActions: NotRequired[list[dict[str, Any]]]
