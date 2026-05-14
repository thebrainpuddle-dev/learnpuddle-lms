"""Pydantic types for the media generation subsystem.

Source: THU-MAIC/OpenMAIC lib/media/types.ts (read for shape; re-
        implemented in Pydantic per ADR-001a — no AGPL code import).
        Backend mirror at backend/apps/maic_pbl/types.py uses the
        same pattern (explicit ``extra="forbid"`` on every model so
        unknown fields fail loud).

Used by:
  - apps/maic/media/providers.py — adapter ABC method signatures
  - apps/maic/media/orchestrator.py — job dispatch + retry
  - apps/maic/media/adapters/*.py — every provider conforms to these
  - apps/maic/media/views.py — DRF view serialization
  - frontend/src/lib/media/types.ts — TS mirror (lift in MAIC-916)

Discipline:
  - ``extra="forbid"`` on every model (catches schema drift early)
  - Typed Literals for provider IDs (compile-time safety + Pydantic
    enum-like validation)
  - No defaults that mask missing required fields
  - Tenant ID is required on every request — telemetry + storage path
    keying both depend on it
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ── Provider identifiers ──────────────────────────────────────────────


ImageProviderId = Literal[
    "openai",
    "qwen",
    "grok",
    "minimax",
    "nano_banana",
    "seedream",
    "stability",
    "pollinations",
    "disabled",
]

VideoProviderId = Literal[
    "veo",
    "kling",
    "minimax_video",
    "seedance",
    "grok_video",
    "disabled",
]


class MediaTaskState(str, Enum):
    """Async-polling lifecycle for video providers.

    Image providers complete synchronously (single HTTP call returns
    bytes or a URL) and never enter polling state. Video providers
    typically return a task id; the orchestrator polls with bounded
    backoff until the state is READY or FAILED, with a hard timeout
    at the orchestrator level (default 600s for video).
    """

    PENDING = "pending"
    POLLING = "polling"
    READY = "ready"
    FAILED = "failed"


# ── Image generation ──────────────────────────────────────────────────


class ImageGenerationRequest(BaseModel):
    """Inputs to generate one image.

    The orchestrator + adapter together translate this into a provider-
    specific HTTP call. Tenant id is required for two reasons: it keys
    the storage path so generated images don't leak across tenants,
    and it gates per-tenant rate limits + telemetry. Scene id is
    optional — the placeholder generation pipeline (Phase 4) supplies
    it; ad-hoc admin requests do not.
    """

    prompt: str = Field(min_length=1, max_length=4_000)
    width: int = Field(default=1024, ge=64, le=4096)
    height: int = Field(default=1024, ge=64, le=4096)
    quality: Literal["standard", "high"] = "standard"
    seed: int | None = Field(default=None, ge=0)
    tenant_id: str = Field(min_length=1)
    scene_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class ImageGenerationResult(BaseModel):
    """Output of one image generation.

    ``url`` is the public/signed URL the frontend renders; the adapter
    is responsible for uploading bytes to storage and returning the
    final URL. ``cost_usd_estimate`` is provider-derived (list price
    × dimensions / quality multiplier); MAY be None when the provider
    does not return enough info to compute it (we do not fail the
    request on missing cost — telemetry is non-blocking).
    """

    media_id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    provider: ImageProviderId
    model: str = Field(min_length=1)
    latency_ms: int = Field(ge=0)
    cost_usd_estimate: float | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid")


# ── Video generation ──────────────────────────────────────────────────


class VideoGenerationRequest(BaseModel):
    """Inputs to generate one video clip.

    Duration is in seconds; provider caps vary (Veo: 8s; Kling: 5-10s;
    Minimax-video: 6-10s). The orchestrator clamps to the provider's
    range when dispatching. Aspect ratio is the union of the three
    common ones across all video providers.
    """

    prompt: str = Field(min_length=1, max_length=4_000)
    duration_seconds: int = Field(default=5, ge=1, le=60)
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    seed: int | None = Field(default=None, ge=0)
    tenant_id: str = Field(min_length=1)
    scene_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class VideoGenerationResult(BaseModel):
    """Output of one video generation."""

    media_id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    provider: VideoProviderId
    model: str = Field(min_length=1)
    duration_seconds: int = Field(ge=1)
    latency_ms: int = Field(ge=0)
    cost_usd_estimate: float | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid")
