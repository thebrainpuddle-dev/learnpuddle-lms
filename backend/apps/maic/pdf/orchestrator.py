"""Async orchestrator for MAIC v2 PDF parsing.

The provider adapters own provider-specific HTTP and response shaping.
This module is the stable application-level path used by HTTP views and,
later, generation jobs: resolve the tenant's configured adapter, bound the
call by the adapter timeout, and surface typed MAIC exceptions.
"""
from __future__ import annotations

import asyncio

from apps.maic.exceptions import MaicProviderError
from apps.maic.pdf import adapters  # noqa: F401 - side-effect: register adapters
from apps.maic.pdf.providers import resolve_pdf_provider
from apps.maic.pdf.types import PDFParseRequest, PDFParseResult


async def parse_pdf(req: PDFParseRequest, tenant_config) -> PDFParseResult:
    """Parse one PDF for a tenant using its configured provider.

    Raises:
        MaicConfigError: provider disabled, missing API key, SSRF rejection.
        MaicProviderError: upstream/network/malformed response/timeout.
    """
    adapter = resolve_pdf_provider(tenant_config)

    try:
        async with asyncio.timeout(adapter.default_timeout_seconds):
            return await adapter.parse(req)
    except TimeoutError as exc:
        raise MaicProviderError(
            f"pdf parse timed out after {adapter.default_timeout_seconds}s: "
            f"provider={adapter.name}"
        ) from exc
