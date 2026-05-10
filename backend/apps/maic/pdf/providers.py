"""Provider adapter ABC + minimal registry for PDF ingest.

Source: apps/maic/media/providers.py (Phase 9 MAIC-902 pattern). We
        deliberately did NOT share the media base class — image/video
        results are Pydantic ``ImageGenerationResult`` /
        ``VideoGenerationResult``; PDF result is ``PDFParseResult``,
        a different shape. Forcing a shared ABC would require ``Any``
        returns and lose the per-adapter type guarantee. Two small
        ABCs cost ~80 LOC vs ~30 LOC of false reuse.

Used by:
  - apps/maic/pdf/adapters/*.py — concrete adapters register here
  - apps/maic/pdf/views.py — calls resolve_pdf_provider(tenant_config)

Discipline:
  - Module-level _REGISTRY (single global, like media providers)
  - register_adapter decorator with duplicate detection
  - resolve_pdf_provider raises MaicConfigError (not None) on missing
    config — same as Phase 9
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from apps.maic.exceptions import MaicConfigError
from apps.maic.pdf.types import PDFParseRequest, PDFParseResult


# ── Adapter ABC ───────────────────────────────────────────────────────


class PDFProviderAdapter(ABC):
    """Base class every concrete PDF parsing adapter must subclass.

    Subclasses declare:
      ``name``: provider identifier matching ``PDFProviderId``
      ``default_timeout_seconds``: outer cap on the entire parse call,
        INCLUDING polling. Tuned per provider; Mineru typically 60-180s
        for a 30-50 page document.

    Subclasses implement:
      ``async def parse(req) -> PDFParseResult`` — single attempt;
        raise MaicProviderError on transient failure (caller may retry
        at a higher level, but PDF parse is expensive — usually not
        worth retrying), MaicConfigError on permanent failure.
    """

    name: ClassVar[str]
    default_timeout_seconds: ClassVar[int] = 180

    def __init__(self, tenant_config) -> None:
        self.tenant_config = tenant_config

    @abstractmethod
    async def parse(self, req: PDFParseRequest) -> PDFParseResult:
        """Parse one PDF and return the structured document.

        Raises:
            MaicProviderError: transient provider failure (network,
                5xx, polling timeout, malformed response).
            MaicConfigError: bad auth, disabled provider, SSRF reject.
        """
        ...


# ── Registry ──────────────────────────────────────────────────────────


_REGISTRY: dict[str, type[PDFProviderAdapter]] = {}


def register_adapter(cls: type[PDFProviderAdapter]) -> type[PDFProviderAdapter]:
    """Class decorator that adds an adapter to the registry. Duplicate
    registration is a hard error (same posture as the media registry)."""
    if not hasattr(cls, "name"):
        raise MaicConfigError(
            f"PDF adapter {cls.__name__} must declare ClassVar name",
        )
    if cls.name in _REGISTRY:
        existing = _REGISTRY[cls.name]
        raise MaicConfigError(
            f"duplicate PDF adapter registration for name={cls.name!r}: "
            f"{existing.__name__} vs {cls.__name__}",
        )
    _REGISTRY[cls.name] = cls
    return cls


# ── Resolver factory ──────────────────────────────────────────────────


def resolve_pdf_provider(tenant_config) -> PDFProviderAdapter:
    """Pick the right PDF adapter for this tenant + instantiate it.

    Raises:
        MaicConfigError: provider is "disabled" or unregistered.
    """
    provider_id: str = getattr(tenant_config, "pdf_provider", "disabled")
    if provider_id == "disabled":
        raise MaicConfigError("PDF ingest disabled for this tenant")

    cls = _REGISTRY.get(provider_id)
    if cls is None:
        available = sorted(_REGISTRY.keys())
        raise MaicConfigError(
            f"unknown PDF provider {provider_id!r}; "
            f"registered providers: {available}",
        )
    return cls(tenant_config)
