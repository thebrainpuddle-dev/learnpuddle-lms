"""Provider adapter ABC + registry + resolver factories.

Source: THU-MAIC/OpenMAIC lib/media/image-providers.ts + lib/media/video-providers.ts
        (read for the registry + factory pattern; re-implemented in Python
        per ADR-001a). Backend mirror at apps/maic/tts/service.py for the
        per-tenant resolver shape.

Used by:
  - apps/maic/media/orchestrator.py — calls resolve_image_provider /
    resolve_video_provider to instantiate the right adapter per request
  - apps/maic/media/adapters/*.py — every concrete adapter registers
    itself via the @register_adapter decorator at module import

Discipline:
  - ABC + ClassVar makes provider identity static (the name lives on
    the class, not the instance), so the registry key is well-defined
    before any instance exists.
  - Registry is module-level (Python imports run once). Tests get
    isolation via the registry_isolated fixture in tests_providers.py.
  - resolve_*_provider raises MaicConfigError (not silent None) on
    unknown provider, disabled provider, or missing config — every
    failure mode is loud at the entry point.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Literal, TypeVar

from apps.maic.exceptions import MaicConfigError
from apps.maic.media.types import (
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageProviderId,
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoProviderId,
)


MediaKind = Literal["image", "video"]
_RequestT = TypeVar("_RequestT", ImageGenerationRequest, VideoGenerationRequest)
_ResultT = TypeVar("_ResultT", ImageGenerationResult, VideoGenerationResult)


# ── Adapter ABC ───────────────────────────────────────────────────────


class MediaProviderAdapter(ABC):
    """Base class every concrete media-generation adapter must subclass.

    Subclasses declare:
      ``name``: the provider identifier (matches ``ImageProviderId`` or
        ``VideoProviderId``); used as the registry key together with
        ``kind``.
      ``kind``: "image" or "video".
      ``default_timeout_seconds``: orchestrator per-attempt cap; overridden
        per provider when the API is unusually slow (e.g. video sync).

    Subclasses implement:
      ``async def generate(req) -> result`` — single attempt; raise
        ``MaicProviderError`` on transient failure (orchestrator decides
        retry), or ``MaicConfigError`` on permanent failure (no retry).
    """

    name: ClassVar[str]
    kind: ClassVar[MediaKind]
    default_timeout_seconds: ClassVar[int] = 30

    def __init__(self, tenant_config) -> None:
        self.tenant_config = tenant_config

    @abstractmethod
    async def generate(self, req):
        """Generate one media artifact. Returns ImageGenerationResult or
        VideoGenerationResult per ``kind``.

        Raises:
            MaicProviderError: provider call failed (network, 5xx, 429).
                Orchestrator MAY retry.
            MaicConfigError: invalid request shape or missing credentials
                that won't be fixed by retry. Orchestrator does NOT retry.
        """
        ...


# ── Registry ──────────────────────────────────────────────────────────


_REGISTRY: dict[tuple[MediaKind, str], type[MediaProviderAdapter]] = {}


def register_adapter(cls: type[MediaProviderAdapter]) -> type[MediaProviderAdapter]:
    """Class decorator that adds an adapter to the registry.

    Usage at the bottom of an adapter module:
        @register_adapter
        class OpenAIImageAdapter(MediaProviderAdapter):
            name = "openai"
            kind = "image"
            async def generate(self, req): ...

    Re-registration is a hard error — duplicate adapters in the
    registry would mask a real shadowing bug.
    """
    if not hasattr(cls, "name") or not hasattr(cls, "kind"):
        raise MaicConfigError(
            f"adapter {cls.__name__} must declare ClassVar name + kind",
        )
    key = (cls.kind, cls.name)
    if key in _REGISTRY:
        existing = _REGISTRY[key]
        raise MaicConfigError(
            f"duplicate adapter registration for kind={cls.kind!r} "
            f"name={cls.name!r}: {existing.__name__} vs {cls.__name__}",
        )
    _REGISTRY[key] = cls
    return cls


def _registered_adapters(kind: MediaKind) -> dict[str, type[MediaProviderAdapter]]:
    """Diagnostic helper — return all adapters of a given kind. Used by
    tests + the admin /v2/verify endpoint (Phase 12)."""
    return {name: cls for (k, name), cls in _REGISTRY.items() if k == kind}


# ── Resolver factories ────────────────────────────────────────────────


def resolve_image_provider(tenant_config) -> MediaProviderAdapter:
    """Pick the right image adapter for this tenant + instantiate it.

    Raises:
        MaicConfigError: provider is "disabled", unregistered, or the
            tenant's API key is empty (when the chosen provider requires
            one — that check is per-adapter in __init__).
    """
    provider_id: str = getattr(tenant_config, "image_provider", "disabled")
    if provider_id == "disabled":
        raise MaicConfigError("image generation disabled for this tenant")

    cls = _REGISTRY.get(("image", provider_id))
    if cls is None:
        available = sorted(_registered_adapters("image").keys())
        raise MaicConfigError(
            f"unknown image provider {provider_id!r}; "
            f"registered providers: {available}",
        )
    return cls(tenant_config)


def resolve_video_provider(tenant_config) -> MediaProviderAdapter:
    """Pick the right video adapter for this tenant + instantiate it."""
    provider_id: str = getattr(tenant_config, "video_provider", "disabled")
    if provider_id == "disabled":
        raise MaicConfigError("video generation disabled for this tenant")

    cls = _REGISTRY.get(("video", provider_id))
    if cls is None:
        available = sorted(_registered_adapters("video").keys())
        raise MaicConfigError(
            f"unknown video provider {provider_id!r}; "
            f"registered providers: {available}",
        )
    return cls(tenant_config)
