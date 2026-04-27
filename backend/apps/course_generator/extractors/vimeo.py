"""Vimeo extractor stub for TASK-060 — AI Course Generator.

MVP: YouTube-only is supported for transcript extraction.
Vimeo transcription (via Whisper) is deferred to a later ticket.

This module exists as a placeholder so the extractor registry
(``get_extractor()``) doesn't raise ImportError on the vimeo source type.
"""

from __future__ import annotations


class VimeoExtractor:
    """Placeholder extractor for Vimeo URLs (not yet implemented)."""

    def extract(self, url: str) -> str:  # noqa: ARG002
        raise NotImplementedError(
            "Vimeo transcript extraction is not implemented in this MVP. "
            "Use a YouTube URL or upload a document instead."
        )
