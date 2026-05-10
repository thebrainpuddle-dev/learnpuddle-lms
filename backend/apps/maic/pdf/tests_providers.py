"""Tests for apps.maic.pdf.providers — registry + factory + ABC.

Pattern: apps/maic/media/tests_providers.py. Real ABC, real registry,
isolated registry fixture so test-only fakes don't leak.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.maic.exceptions import MaicConfigError
from apps.maic.pdf import providers
from apps.maic.pdf.providers import (
    PDFProviderAdapter,
    register_adapter,
    resolve_pdf_provider,
)
from apps.maic.pdf.types import PDFParseRequest, PDFParseResult


@pytest.fixture
def registry_isolated():
    saved = providers._REGISTRY.copy()
    providers._REGISTRY.clear()
    try:
        yield providers._REGISTRY
    finally:
        providers._REGISTRY.clear()
        providers._REGISTRY.update(saved)


class _FakePDFAdapter(PDFProviderAdapter):
    name = "fake_pdf"

    async def parse(self, req):
        from apps.maic.pdf.types import PDFDocument, PDFParseState
        return PDFParseResult(
            document_id="d-fake",
            document=PDFDocument(
                document_id="d-fake", total_pages=1, latency_ms=10,
            ),
            state=PDFParseState.DONE,
            latency_ms=10,
        )


# ── register_adapter ──────────────────────────────────────────────────


def test_register_adds_to_registry(registry_isolated):
    register_adapter(_FakePDFAdapter)
    assert "fake_pdf" in registry_isolated
    assert registry_isolated["fake_pdf"] is _FakePDFAdapter


def test_register_rejects_duplicate(registry_isolated):
    register_adapter(_FakePDFAdapter)
    with pytest.raises(MaicConfigError):
        register_adapter(_FakePDFAdapter)


def test_register_returns_class(registry_isolated):
    """Decorator semantics — pass-through."""
    decorated = register_adapter(_FakePDFAdapter)
    assert decorated is _FakePDFAdapter


# ── resolve_pdf_provider ──────────────────────────────────────────────


def test_resolve_returns_instance(registry_isolated):
    register_adapter(_FakePDFAdapter)
    cfg = SimpleNamespace(pdf_provider="fake_pdf")
    adapter = resolve_pdf_provider(cfg)
    assert isinstance(adapter, _FakePDFAdapter)
    assert adapter.tenant_config is cfg


def test_resolve_raises_when_disabled(registry_isolated):
    cfg = SimpleNamespace(pdf_provider="disabled")
    with pytest.raises(MaicConfigError) as exc:
        resolve_pdf_provider(cfg)
    assert "disabled" in str(exc.value).lower()


def test_resolve_raises_when_unknown(registry_isolated):
    register_adapter(_FakePDFAdapter)
    cfg = SimpleNamespace(pdf_provider="nonexistent")
    with pytest.raises(MaicConfigError) as exc:
        resolve_pdf_provider(cfg)
    msg = str(exc.value)
    assert "nonexistent" in msg
    assert "fake_pdf" in msg  # error lists available providers


def test_resolve_missing_attr_treated_as_disabled(registry_isolated):
    """Tenant config with no pdf_provider attr at all (legacy) → fail
    closed."""
    cfg = SimpleNamespace()
    with pytest.raises(MaicConfigError) as exc:
        resolve_pdf_provider(cfg)
    assert "disabled" in str(exc.value).lower()
