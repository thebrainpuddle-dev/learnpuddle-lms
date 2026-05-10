"""Tests for apps.maic.media.types — Pydantic round-trips + validation.

Pure data tests, no DB, no IO. Following the no-mocks rule: there
are no fakes here because there is nothing to fake. We exercise the
real Pydantic validators on real data.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.maic.media.types import (
    ImageGenerationRequest,
    ImageGenerationResult,
    MediaTaskState,
    VideoGenerationRequest,
    VideoGenerationResult,
)


# ── ImageGenerationRequest ────────────────────────────────────────────


def test_image_request_round_trip():
    """Valid input round-trips through Pydantic. Defaults populate
    width=height=1024, quality=standard, seed=None, scene_id=None."""
    req = ImageGenerationRequest(prompt="a fractions diagram", tenant_id="t-1")
    assert req.prompt == "a fractions diagram"
    assert req.width == 1024
    assert req.height == 1024
    assert req.quality == "standard"
    assert req.seed is None
    assert req.scene_id is None
    assert req.tenant_id == "t-1"


def test_image_request_rejects_empty_prompt():
    """min_length=1 means empty string fails validation."""
    with pytest.raises(ValidationError):
        ImageGenerationRequest(prompt="", tenant_id="t-1")


def test_image_request_rejects_oversize_prompt():
    """max_length=4000 caps prompt size — protects against a teacher
    pasting a whole document into the prompt field."""
    with pytest.raises(ValidationError):
        ImageGenerationRequest(prompt="x" * 4_001, tenant_id="t-1")


def test_image_request_rejects_invalid_dimensions():
    """Width/height bounds: 64 ≤ x ≤ 4096."""
    with pytest.raises(ValidationError):
        ImageGenerationRequest(prompt="p", tenant_id="t-1", width=0)
    with pytest.raises(ValidationError):
        ImageGenerationRequest(prompt="p", tenant_id="t-1", width=8192)
    with pytest.raises(ValidationError):
        ImageGenerationRequest(prompt="p", tenant_id="t-1", height=-100)


def test_image_request_rejects_negative_seed():
    """Seed must be non-negative when provided. None is allowed."""
    with pytest.raises(ValidationError):
        ImageGenerationRequest(prompt="p", tenant_id="t-1", seed=-1)


def test_image_request_rejects_unknown_quality():
    """quality is Literal['standard', 'high'] — anything else rejected."""
    with pytest.raises(ValidationError):
        ImageGenerationRequest(prompt="p", tenant_id="t-1", quality="ultra")


def test_image_request_rejects_extra_fields():
    """extra='forbid' prevents schema drift — unknown keys fail loud."""
    with pytest.raises(ValidationError):
        ImageGenerationRequest(
            prompt="p", tenant_id="t-1", style="picasso",  # unknown
        )


def test_image_request_rejects_missing_tenant_id():
    """tenant_id is required (no default). A request without it fails."""
    with pytest.raises(ValidationError):
        ImageGenerationRequest(prompt="p")


# ── ImageGenerationResult ─────────────────────────────────────────────


def test_image_result_round_trip():
    """Result with all fields populated."""
    res = ImageGenerationResult(
        media_id="m-1",
        url="https://example.com/m-1.png",
        provider="openai",
        model="dall-e-3",
        latency_ms=1234,
        cost_usd_estimate=0.04,
    )
    assert res.media_id == "m-1"
    assert res.cost_usd_estimate == 0.04


def test_image_result_optional_cost():
    """Cost is optional — provider may not return enough info."""
    res = ImageGenerationResult(
        media_id="m-1", url="x", provider="qwen", model="qwen-image-plus",
        latency_ms=500,
    )
    assert res.cost_usd_estimate is None


def test_image_result_rejects_invalid_provider():
    """Provider is a Literal — typo is rejected."""
    with pytest.raises(ValidationError):
        ImageGenerationResult(
            media_id="m", url="x", provider="dalle3",  # typo
            model="dall-e-3", latency_ms=100,
        )


def test_image_result_rejects_negative_latency():
    """latency_ms ≥ 0."""
    with pytest.raises(ValidationError):
        ImageGenerationResult(
            media_id="m", url="x", provider="openai",
            model="dall-e-3", latency_ms=-1,
        )


def test_image_result_rejects_extra_fields():
    with pytest.raises(ValidationError):
        ImageGenerationResult(
            media_id="m", url="x", provider="openai",
            model="dall-e-3", latency_ms=1, request_id="abc",  # unknown
        )


# ── VideoGenerationRequest ────────────────────────────────────────────


def test_video_request_round_trip():
    req = VideoGenerationRequest(prompt="a flowing river", tenant_id="t-1")
    assert req.duration_seconds == 5
    assert req.aspect_ratio == "16:9"


def test_video_request_duration_range():
    """duration_seconds in [1, 60]. Provider-specific clamping happens
    at the orchestrator (e.g. Veo caps at 8s)."""
    with pytest.raises(ValidationError):
        VideoGenerationRequest(prompt="p", tenant_id="t-1", duration_seconds=0)
    with pytest.raises(ValidationError):
        VideoGenerationRequest(prompt="p", tenant_id="t-1", duration_seconds=120)


def test_video_request_aspect_ratio_literal():
    """Only the 3 common ratios are allowed."""
    with pytest.raises(ValidationError):
        VideoGenerationRequest(prompt="p", tenant_id="t-1", aspect_ratio="4:3")


# ── VideoGenerationResult ─────────────────────────────────────────────


def test_video_result_round_trip():
    res = VideoGenerationResult(
        media_id="v-1",
        url="https://example.com/v-1.mp4",
        provider="veo",
        model="veo-3",
        duration_seconds=8,
        latency_ms=45_000,
    )
    assert res.duration_seconds == 8


def test_video_result_rejects_zero_duration():
    """duration_seconds ≥ 1 — a 0-second video makes no sense."""
    with pytest.raises(ValidationError):
        VideoGenerationResult(
            media_id="v", url="x", provider="veo", model="veo-3",
            duration_seconds=0, latency_ms=1000,
        )


# ── MediaTaskState ────────────────────────────────────────────────────


def test_media_task_state_has_exactly_four_values():
    """Lock the enum cardinality. Adding a state is a contract change."""
    states = {s.value for s in MediaTaskState}
    assert states == {"pending", "polling", "ready", "failed"}


def test_media_task_state_is_str_enum():
    """str-Enum so JSON serialization gives the string value, not 'MediaTaskState.READY'."""
    assert MediaTaskState.READY == "ready"
    assert MediaTaskState.READY.value == "ready"
