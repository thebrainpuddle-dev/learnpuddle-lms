"""Tests for apps.maic.pdf.types (Phase 10, MAIC-1001).

Pure data validation. No mocks, no DB, no IO. Mirrors the shape of
apps/maic/media/tests_types.py.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.maic.pdf.types import (
    PDFDocument,
    PDFFigure,
    PDFPage,
    PDFParseRequest,
    PDFParseResult,
    PDFParseState,
    PDFSection,
)


# ── PDFParseRequest ───────────────────────────────────────────────────


def test_parse_request_round_trip():
    req = PDFParseRequest(
        file_url="https://storage.example/textbook.pdf",
        tenant_id="t-1",
    )
    assert req.file_url == "https://storage.example/textbook.pdf"
    assert req.tenant_id == "t-1"
    assert req.scene_id is None
    assert req.page_limit is None
    assert req.extract_figures is True  # default


def test_parse_request_rejects_empty_file_url():
    with pytest.raises(ValidationError):
        PDFParseRequest(file_url="", tenant_id="t-1")


def test_parse_request_rejects_oversize_file_url():
    """4000-char URL cap — guards against accidentally passing the
    entire PDF as a data: URL, which would 500 Mineru."""
    with pytest.raises(ValidationError):
        PDFParseRequest(file_url="https://x/" + "a" * 5000, tenant_id="t-1")


def test_parse_request_page_limit_bounds():
    with pytest.raises(ValidationError):
        PDFParseRequest(file_url="https://x/a.pdf", tenant_id="t-1", page_limit=0)
    with pytest.raises(ValidationError):
        PDFParseRequest(file_url="https://x/a.pdf", tenant_id="t-1", page_limit=501)
    # Boundaries OK
    PDFParseRequest(file_url="https://x/a.pdf", tenant_id="t-1", page_limit=1)
    PDFParseRequest(file_url="https://x/a.pdf", tenant_id="t-1", page_limit=500)


def test_parse_request_rejects_extra_fields():
    with pytest.raises(ValidationError):
        PDFParseRequest(
            file_url="https://x/a.pdf", tenant_id="t-1",
            secret_field="oops",
        )


def test_parse_request_requires_tenant_id():
    with pytest.raises(ValidationError):
        PDFParseRequest(file_url="https://x/a.pdf")


# ── PDFSection / PDFFigure / PDFPage ──────────────────────────────────


def test_section_round_trip():
    s = PDFSection(
        section_id="s-1",
        title="Chapter 1 — Fractions",
        level=1,
        text="Fractions are parts of a whole...",
        page_start=1,
        page_end=12,
    )
    assert s.level == 1


def test_section_level_bounds():
    """Heading levels mirror HTML h1-h6."""
    with pytest.raises(ValidationError):
        PDFSection(section_id="s", title="t", level=0, page_start=1, page_end=1)
    with pytest.raises(ValidationError):
        PDFSection(section_id="s", title="t", level=7, page_start=1, page_end=1)


def test_section_rejects_empty_title():
    with pytest.raises(ValidationError):
        PDFSection(section_id="s", title="", level=1, page_start=1, page_end=1)


def test_figure_round_trip():
    fig = PDFFigure(
        figure_id="f-1",
        caption="Pie chart showing 1/3 vs 2/3",
        image_url="https://storage.example/figures/f-1.png",
        page=3,
        bbox=(0.1, 0.2, 0.5, 0.6),
    )
    assert fig.bbox == (0.1, 0.2, 0.5, 0.6)


def test_figure_image_url_optional():
    """Not all providers re-host figure images — image_url may be None
    on first extraction; later passes can re-host."""
    fig = PDFFigure(figure_id="f", caption="", page=1)
    assert fig.image_url is None
    assert fig.bbox is None


def test_page_round_trip():
    p = PDFPage(page_number=1, text="Page 1 plain text here.")
    assert p.page_number == 1


def test_page_text_can_be_empty():
    """Blank pages (cover, dividers) are legitimate — empty text OK."""
    p = PDFPage(page_number=42, text="")
    assert p.text == ""


# ── PDFDocument ────────────────────────────────────────────────────────


def test_document_round_trip():
    doc = PDFDocument(
        document_id="d-1",
        title="Math Foundations",
        total_pages=120,
        sections=[
            PDFSection(
                section_id="s-1", title="Ch 1", level=1,
                page_start=1, page_end=20,
            ),
        ],
        figures=[
            PDFFigure(figure_id="f-1", page=5),
        ],
        pages=[
            PDFPage(page_number=1, text="cover"),
        ],
        provider="mineru",
        latency_ms=45_000,
        cost_usd_estimate=0.05,
    )
    assert doc.total_pages == 120
    assert len(doc.sections) == 1
    assert doc.cost_usd_estimate == 0.05


def test_document_empty_sections_and_figures_ok():
    """A scan-only PDF (image-heavy, text-light) might extract no
    sections or figures — that's still a valid document."""
    doc = PDFDocument(
        document_id="d-2",
        total_pages=1,
        latency_ms=1000,
    )
    assert doc.sections == []
    assert doc.figures == []
    assert doc.pages == []


def test_document_rejects_zero_pages():
    """A 0-page PDF is nonsensical — fail validation early."""
    with pytest.raises(ValidationError):
        PDFDocument(document_id="d", total_pages=0, latency_ms=100)


def test_document_provider_literal_validation():
    with pytest.raises(ValidationError):
        PDFDocument(
            document_id="d", total_pages=1, latency_ms=100,
            provider="invalid_provider",
        )


# ── PDFParseResult ─────────────────────────────────────────────────────


def test_parse_result_round_trip():
    res = PDFParseResult(
        document_id="d-1",
        document=PDFDocument(
            document_id="d-1", total_pages=10, latency_ms=5000,
        ),
        state=PDFParseState.DONE,
        latency_ms=5000,
    )
    assert res.state == PDFParseState.DONE


# ── PDFParseState ──────────────────────────────────────────────────────


def test_parse_state_has_exactly_four_values():
    """Lock the cardinality so adding a state is an explicit contract change."""
    assert {s.value for s in PDFParseState} == {
        "pending", "processing", "done", "failed",
    }


def test_parse_state_is_str_enum():
    """str-Enum semantics so JSON serialization gives the string value."""
    assert PDFParseState.DONE == "done"
    assert PDFParseState.DONE.value == "done"
