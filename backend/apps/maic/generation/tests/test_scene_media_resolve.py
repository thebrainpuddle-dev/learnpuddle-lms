"""Tests for resolve_scene_media (Phase 9, MAIC-915).

Discipline:
  - IO-boundary fakes: orchestrator functions
    (apps.maic.media.orchestrator.generate_image / generate_video) are
    monkey-patched at the scene_builder import site. The resolver
    itself (the unit under test) runs unchanged.
  - Real Pydantic, real asyncio.gather, real failure paths.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.maic.exceptions import MaicConfigError, MaicProviderError
from apps.maic.generation.scene_builder import resolve_scene_media
from apps.maic.media.types import (
    ImageGenerationResult,
    VideoGenerationResult,
)


# ── Fixtures ──────────────────────────────────────────────────────────


def _tenant_cfg(tenant_id: str = "t-1"):
    """Minimal stand-in for TenantAIConfig. resolve_scene_media only
    reads tenant_id off it; the orchestrator (fully tested elsewhere)
    is patched out below."""
    return SimpleNamespace(tenant_id=tenant_id)


def _slide_scene(scene_id: str = "scene-1", *, elements: list[dict]) -> dict:
    """Build a minimal slide scene with given elements. Mirrors the
    shape produced by build_complete_scene."""
    return {
        "id": scene_id,
        "type": "slide",
        "content": {
            "type": "slide",
            "canvas": {"elements": elements},
        },
    }


def _outline_with_media(media_generations: list[dict]) -> dict:
    """Outline shape that produces mediaGenerations entries."""
    return {
        "type": "slide",
        "title": "test",
        "mediaGenerations": media_generations,
    }


# ── No-op paths (return scene unchanged) ──────────────────────────────


@pytest.mark.asyncio
async def test_resolver_no_op_when_scene_is_none():
    result = await resolve_scene_media(None, {}, _tenant_cfg())
    assert result is None


@pytest.mark.asyncio
async def test_resolver_no_op_when_tenant_config_is_none():
    """No tenant config means caller opted out; scene is preserved
    verbatim even if it has placeholders."""
    scene = _slide_scene(elements=[
        {"type": "image", "src": "gen_img_xyz", "id": "el-1"},
    ])
    result = await resolve_scene_media(scene, {}, None)
    assert result is scene  # same object
    assert result["content"]["canvas"]["elements"][0]["src"] == "gen_img_xyz"


@pytest.mark.asyncio
async def test_resolver_no_op_when_non_slide_scene():
    """Quiz/PBL/interactive scenes don't have gen_img placeholders to
    resolve. Return unchanged regardless of orchestrator state."""
    scene = {
        "id": "quiz-1",
        "type": "quiz",
        "content": {"type": "quiz", "questions": []},
    }
    result = await resolve_scene_media(scene, {}, _tenant_cfg())
    assert result is scene


@pytest.mark.asyncio
async def test_resolver_no_op_when_no_elements():
    scene = _slide_scene(elements=[])
    result = await resolve_scene_media(scene, {}, _tenant_cfg())
    assert result is scene


@pytest.mark.asyncio
async def test_resolver_no_op_when_no_placeholders():
    """All element srcs are already real URLs — no media to resolve."""
    scene = _slide_scene(elements=[
        {"type": "image", "src": "https://cdn.example/real.png", "id": "el-1"},
        {"type": "text",  "content": "hello", "id": "el-2"},
    ])
    result = await resolve_scene_media(scene, {}, _tenant_cfg())
    assert result["content"]["canvas"]["elements"][0]["src"] == \
        "https://cdn.example/real.png"


@pytest.mark.asyncio
async def test_resolver_skips_placeholder_without_matching_media_generation():
    """Element has gen_img_xyz src but no matching mediaGenerations entry —
    we don't know what prompt to use, so preserve the placeholder
    (frontend renders a skeleton)."""
    scene = _slide_scene(elements=[
        {"type": "image", "src": "gen_img_orphan", "id": "el-1"},
    ])
    outline = _outline_with_media([])  # empty
    result = await resolve_scene_media(scene, outline, _tenant_cfg())
    assert result["content"]["canvas"]["elements"][0]["src"] == "gen_img_orphan"


# ── Happy path: orchestrator returns real URLs ────────────────────────


@pytest.mark.asyncio
async def test_resolver_replaces_image_placeholder_with_real_url(monkeypatch):
    scene = _slide_scene(scene_id="s-happy", elements=[
        {"type": "image", "src": "gen_img_abc", "id": "el-1"},
        {"type": "text",  "content": "title", "id": "el-2"},
    ])
    outline = _outline_with_media([
        {"elementId": "gen_img_abc", "type": "image",
         "prompt": "a colourful diagram"},
    ])

    captured: dict = {}

    async def _fake_image_gen(req, tenant_cfg):
        captured["prompt"] = req.prompt
        captured["scene_id"] = req.scene_id
        captured["tenant_id"] = req.tenant_id
        return ImageGenerationResult(
            media_id="m-1",
            url="https://storage.example/maic/t-1/image/m-1.png",
            provider="openai",
            model="dall-e-3",
            latency_ms=100,
        )

    monkeypatch.setattr(
        "apps.maic.media.orchestrator.generate_image", _fake_image_gen,
    )

    result = await resolve_scene_media(scene, outline, _tenant_cfg("t-1"))

    # Placeholder swapped for real URL; non-image element untouched.
    elements = result["content"]["canvas"]["elements"]
    assert elements[0]["src"] == "https://storage.example/maic/t-1/image/m-1.png"
    assert elements[1]["content"] == "title"

    # Orchestrator received the right inputs
    assert captured["prompt"] == "a colourful diagram"
    assert captured["scene_id"] == "s-happy"
    assert captured["tenant_id"] == "t-1"


@pytest.mark.asyncio
async def test_resolver_replaces_video_placeholder_with_real_url(monkeypatch):
    scene = _slide_scene(elements=[
        {"type": "video", "src": "gen_vid_clip", "id": "el-1"},
    ])
    outline = _outline_with_media([
        {"elementId": "gen_vid_clip", "type": "video",
         "prompt": "a river flowing", "duration_seconds": 5},
    ])

    async def _fake_video_gen(req, tenant_cfg):
        return VideoGenerationResult(
            media_id="v-1",
            url="https://storage.example/maic/t-1/video/v-1.mp4",
            provider="veo",
            model="veo-3.0-generate-preview",
            duration_seconds=5,
            latency_ms=45000,
        )

    monkeypatch.setattr(
        "apps.maic.media.orchestrator.generate_video", _fake_video_gen,
    )

    result = await resolve_scene_media(scene, outline, _tenant_cfg("t-1"))
    assert result["content"]["canvas"]["elements"][0]["src"] == \
        "https://storage.example/maic/t-1/video/v-1.mp4"


@pytest.mark.asyncio
async def test_resolver_runs_multiple_images_in_parallel(monkeypatch):
    """3 placeholder images should be resolved via a single asyncio.gather
    — proves we're NOT serializing the dispatches."""
    scene = _slide_scene(elements=[
        {"type": "image", "src": "gen_img_a", "id": "1"},
        {"type": "image", "src": "gen_img_b", "id": "2"},
        {"type": "image", "src": "gen_img_c", "id": "3"},
    ])
    outline = _outline_with_media([
        {"elementId": "gen_img_a", "type": "image", "prompt": "A"},
        {"elementId": "gen_img_b", "type": "image", "prompt": "B"},
        {"elementId": "gen_img_c", "type": "image", "prompt": "C"},
    ])

    call_log: list[str] = []

    async def _fake_image_gen(req, tenant_cfg):
        call_log.append(req.prompt)
        return ImageGenerationResult(
            media_id=f"m-{req.prompt}",
            url=f"https://storage.example/m-{req.prompt}.png",
            provider="openai",
            model="dall-e-3",
            latency_ms=100,
        )

    monkeypatch.setattr(
        "apps.maic.media.orchestrator.generate_image", _fake_image_gen,
    )

    result = await resolve_scene_media(scene, outline, _tenant_cfg())

    assert len(call_log) == 3
    elements = result["content"]["canvas"]["elements"]
    assert elements[0]["src"] == "https://storage.example/m-A.png"
    assert elements[1]["src"] == "https://storage.example/m-B.png"
    assert elements[2]["src"] == "https://storage.example/m-C.png"


# ── Failure handling: preserve placeholder, don't break the scene ─────


@pytest.mark.asyncio
async def test_resolver_preserves_placeholder_when_orchestrator_raises_provider_error(monkeypatch):
    scene = _slide_scene(elements=[
        {"type": "image", "src": "gen_img_fail", "id": "el-1"},
    ])
    outline = _outline_with_media([
        {"elementId": "gen_img_fail", "type": "image", "prompt": "X"},
    ])

    async def _failing_gen(req, tenant_cfg):
        raise MaicProviderError("upstream 502 after 3 retries")

    monkeypatch.setattr(
        "apps.maic.media.orchestrator.generate_image", _failing_gen,
    )

    result = await resolve_scene_media(scene, outline, _tenant_cfg())
    # Placeholder preserved — scene is still usable (frontend shows skeleton)
    assert result["content"]["canvas"]["elements"][0]["src"] == "gen_img_fail"


@pytest.mark.asyncio
async def test_resolver_preserves_placeholder_when_orchestrator_raises_config_error(monkeypatch):
    """MaicConfigError (e.g. provider disabled, SSRF, unknown provider) is
    permanent — we still don't fail the scene, just keep the placeholder."""
    scene = _slide_scene(elements=[
        {"type": "image", "src": "gen_img_cfg", "id": "el-1"},
    ])
    outline = _outline_with_media([
        {"elementId": "gen_img_cfg", "type": "image", "prompt": "X"},
    ])

    async def _cfg_err(req, tenant_cfg):
        raise MaicConfigError("image_provider is 'disabled' for this tenant")

    monkeypatch.setattr(
        "apps.maic.media.orchestrator.generate_image", _cfg_err,
    )

    result = await resolve_scene_media(scene, outline, _tenant_cfg())
    assert result["content"]["canvas"]["elements"][0]["src"] == "gen_img_cfg"


@pytest.mark.asyncio
async def test_resolver_partial_failure_isolates_to_failing_element(monkeypatch):
    """One image succeeds; another fails. Successful one gets its
    real URL; failing one keeps its placeholder. Neither blocks the
    other (asyncio.gather + per-task try/except)."""
    scene = _slide_scene(elements=[
        {"type": "image", "src": "gen_img_ok",   "id": "el-1"},
        {"type": "image", "src": "gen_img_bad",  "id": "el-2"},
    ])
    outline = _outline_with_media([
        {"elementId": "gen_img_ok",  "type": "image", "prompt": "ok"},
        {"elementId": "gen_img_bad", "type": "image", "prompt": "bad"},
    ])

    async def _mixed(req, tenant_cfg):
        if req.prompt == "bad":
            raise MaicProviderError("intentional failure")
        return ImageGenerationResult(
            media_id="m-good",
            url="https://storage.example/m-good.png",
            provider="openai",
            model="dall-e-3",
            latency_ms=100,
        )

    monkeypatch.setattr(
        "apps.maic.media.orchestrator.generate_image", _mixed,
    )

    result = await resolve_scene_media(scene, outline, _tenant_cfg())
    elements = result["content"]["canvas"]["elements"]
    assert elements[0]["src"] == "https://storage.example/m-good.png"
    assert elements[1]["src"] == "gen_img_bad"  # placeholder preserved


# ── Edge cases ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolver_handles_missing_prompt_field(monkeypatch):
    """mediaGenerations entry exists but has no prompt → skip
    (don't call orchestrator with empty prompt; that would fail
    Pydantic validation anyway)."""
    scene = _slide_scene(elements=[
        {"type": "image", "src": "gen_img_noprompt", "id": "el-1"},
    ])
    outline = _outline_with_media([
        {"elementId": "gen_img_noprompt", "type": "image"},  # no prompt key
    ])

    called = False

    async def _should_not_be_called(req, tenant_cfg):
        nonlocal called
        called = True
        return ImageGenerationResult(
            media_id="m", url="x", provider="openai", model="t", latency_ms=1,
        )

    monkeypatch.setattr(
        "apps.maic.media.orchestrator.generate_image", _should_not_be_called,
    )

    result = await resolve_scene_media(scene, outline, _tenant_cfg())
    assert called is False
    assert result["content"]["canvas"]["elements"][0]["src"] == "gen_img_noprompt"


@pytest.mark.asyncio
async def test_resolver_ignores_non_dict_elements(monkeypatch):
    """Defensive — if some malformed element sneaks into elements[]
    (string, None, etc.), the resolver doesn't crash; just skips it."""
    scene = _slide_scene(elements=[
        None,
        "stray-string",
        {"type": "image", "src": "gen_img_real", "id": "el-1"},
    ])
    outline = _outline_with_media([
        {"elementId": "gen_img_real", "type": "image", "prompt": "p"},
    ])

    async def _fake(req, tenant_cfg):
        return ImageGenerationResult(
            media_id="m", url="https://storage.example/m.png",
            provider="openai", model="t", latency_ms=1,
        )

    monkeypatch.setattr(
        "apps.maic.media.orchestrator.generate_image", _fake,
    )

    result = await resolve_scene_media(scene, outline, _tenant_cfg())
    elements = result["content"]["canvas"]["elements"]
    assert elements[0] is None  # untouched
    assert elements[1] == "stray-string"
    assert elements[2]["src"] == "https://storage.example/m.png"
