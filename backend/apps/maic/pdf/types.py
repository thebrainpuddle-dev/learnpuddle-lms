"""Pydantic types for the PDF ingest subsystem (Phase 10, MAIC-1001).

Source: THU-MAIC/OpenMAIC lib/pdf/types.ts (read for shape; re-
        implemented in Pydantic per ADR-001a). Backend pattern from
        apps/maic/media/types.py (Phase 9 MAIC-901).

Used by:
  - apps/maic/pdf/providers.py — provider ABC contract (MAIC-1002)
  - apps/maic/pdf/views.py — DRF serialization (MAIC-1003)
  - apps/maic/generation/* — outline generator accepts a parsed
    PDFDocument as an alternative to the bare topic seed (MAIC-1004)

Discipline:
  - ``extra="forbid"`` on every model — schema drift fails loud
  - Tenant id required on every request — telemetry + storage path
    keying both depend on it
  - PDFParseState mirrors Mineru's lifecycle (and the polling pattern
    we already use for video adapters)
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


PDFProviderId = Literal["mineru", "disabled"]


class PDFParseState(str, Enum):
    """Async-polling lifecycle for PDF parse tasks.

    Mineru cloud submits a task and returns a task_id; we poll until
    the state is terminal. Mirrors the MediaTaskState pattern from
    apps/maic/media/types.py — same orchestration shape, different
    domain.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


# ── Document structure (sections, figures, pages) ─────────────────────


class PDFFigure(BaseModel):
    """One figure (image) extracted from the PDF."""

    figure_id: str = Field(min_length=1)
    caption: str = Field(default="", max_length=2_000)
    image_url: str | None = None  # storage URL when re-hosted, else None
    page: int = Field(ge=1)
    bbox: tuple[float, float, float, float] | None = None  # x0,y0,x1,y1 in page coords

    model_config = ConfigDict(extra="forbid")


class PDFSection(BaseModel):
    """One semantic section (chapter / heading) extracted from the PDF.

    Page range is inclusive on both ends. Level mirrors HTML-heading
    semantics (1 = chapter, 2 = section, 3 = subsection).
    """

    section_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=500)
    level: int = Field(ge=1, le=6)
    text: str = ""  # body text, may be very long; no max_length cap
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)

    model_config = ConfigDict(extra="forbid")


class PDFPage(BaseModel):
    """One page of the PDF as plain text (Mineru flattens layout to
    markdown-ish text). Useful for fallback when section extraction
    misses a span."""

    page_number: int = Field(ge=1)
    text: str = ""

    model_config = ConfigDict(extra="forbid")


class PDFDocument(BaseModel):
    """Structured representation of a parsed PDF.

    Returned to clients verbatim; persisted as JSON on the
    PDFDocument model row (MAIC-1003). Section + figure ordering
    matches reading order; pages are 1-indexed.
    """

    document_id: str = Field(min_length=1)
    title: str = Field(default="", max_length=500)
    total_pages: int = Field(ge=1)
    sections: list[PDFSection] = Field(default_factory=list)
    figures: list[PDFFigure] = Field(default_factory=list)
    pages: list[PDFPage] = Field(default_factory=list)
    # Provider that produced this document (mineru or future provider)
    provider: PDFProviderId = "mineru"
    # Latency from submit to terminal status (ms)
    latency_ms: int = Field(ge=0)
    # Estimated cost in USD, or None when provider doesn't expose it
    cost_usd_estimate: float | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid")


# ── Request / Result envelopes ────────────────────────────────────────


class PDFParseRequest(BaseModel):
    """Inputs to parse one PDF.

    file_url is required — Mineru cloud accepts a URL the worker can
    fetch from. Direct multipart upload is supported by some providers
    but adds complexity (the orchestrator would have to stream bytes
    to the provider rather than passing a URL); deferred to MAIC-1003.
    Frontend uploads to our storage first → passes the resulting URL
    here.
    """

    file_url: str = Field(min_length=1, max_length=4_000)
    tenant_id: str = Field(min_length=1)
    scene_id: str | None = None
    # Hint to provider: extract only first N pages; useful for large
    # textbooks where the user only needs the chapter (default None =
    # entire document, bounded by Mineru's own cap)
    page_limit: int | None = Field(default=None, ge=1, le=500)
    # Whether to extract figures (default True). Set False to skip
    # image-extraction cost when the use case is text-only.
    extract_figures: bool = True

    model_config = ConfigDict(extra="forbid")


class PDFParseResult(BaseModel):
    """Output of one parse job.

    Wraps the actual PDFDocument. document_id is also exposed at the
    top level for client convenience (matches the shape downstream
    callers expect: media-style result envelope)."""

    document_id: str = Field(min_length=1)
    document: PDFDocument
    state: PDFParseState
    latency_ms: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")
