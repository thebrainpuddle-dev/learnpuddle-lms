"""Pollinations image adapter for tenant-configured v2 media generation.

Pollinations is the repository's legacy no-key fallback. This adapter brings
it into the Phase 9 media orchestrator contract so v2 classrooms can resolve
``gen_img_*`` placeholders through the same tenant-scoped storage path as
paid providers.
"""
from __future__ import annotations

from typing import ClassVar
from urllib.parse import quote

from apps.maic.exceptions import MaicProviderError
from apps.maic.media.providers import MediaProviderAdapter, register_adapter
from apps.maic.media.storage import upload_media
from apps.maic.media.types import ImageGenerationRequest, ImageGenerationResult


@register_adapter
class PollinationsImageAdapter(MediaProviderAdapter):
    name: ClassVar[str] = "pollinations"
    kind: ClassVar = "image"
    default_timeout_seconds: ClassVar[int] = 45

    _BASE_URL: ClassVar[str] = "https://image.pollinations.ai/prompt"
    _DEFAULT_MODEL: ClassVar[str] = "flux"

    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        try:
            import aiohttp  # type: ignore[import-untyped]
        except ImportError as exc:
            raise MaicProviderError(
                "pollinations image: aiohttp is required"
            ) from exc

        model = self.tenant_config.image_model or self._DEFAULT_MODEL
        prompt = quote(f"Educational illustration: {req.prompt}", safe="")
        url = (
            f"{self._BASE_URL}/{prompt}"
            f"?width={req.width}"
            f"&height={req.height}"
            f"&nologo=true"
            f"&model={quote(model, safe='')}"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        body = (await resp.text())[:200]
                        raise MaicProviderError(
                            f"pollinations image: HTTP {resp.status}: {body}"
                        )
                    content_type = resp.headers.get("Content-Type", "image/jpeg")
                    if not content_type.lower().startswith("image/"):
                        raise MaicProviderError(
                            "pollinations image: response was not an image "
                            f"({content_type})"
                        )
                    data = await resp.read()
        except MaicProviderError:
            raise
        except aiohttp.ClientError as exc:
            raise MaicProviderError(
                f"pollinations image: network error: {exc}"
            ) from exc

        if len(data) < 1000:
            raise MaicProviderError(
                f"pollinations image: response too small ({len(data)} bytes)"
            )

        media_id, stored_url = await upload_media(
            data=data,
            content_type=content_type,
            tenant_id=req.tenant_id,
            kind="image",
            scene_id=req.scene_id,
        )
        return ImageGenerationResult(
            media_id=media_id,
            url=stored_url,
            provider="pollinations",
            model=model,
            latency_ms=0,
            cost_usd_estimate=0,
        )
