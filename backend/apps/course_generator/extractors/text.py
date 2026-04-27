"""Plain-text extractor for TASK-060 — AI Course Generator.

Reads raw bytes, auto-detects encoding via chardet (or falls back to UTF-8),
and caps at 100k chars.
"""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

CHAR_CAP = 100_000
# Bytes read for charset detection
CHARDET_SAMPLE = 65_536


class TextExtractor:
    """Extract text from a plain-text file-like object."""

    def extract(self, file_obj: io.IOBase) -> str:
        """Return up to CHAR_CAP chars of decoded text.

        Args:
            file_obj: A readable binary file-like object.

        Returns:
            Decoded text, potentially truncated.
        """
        raw = file_obj.read()
        if not isinstance(raw, bytes):
            # Already decoded (StringIO)
            return raw[:CHAR_CAP]

        encoding = self._detect_encoding(raw)
        text = raw.decode(encoding, errors="replace")
        return text[:CHAR_CAP]

    @staticmethod
    def _detect_encoding(raw: bytes) -> str:
        sample = raw[:CHARDET_SAMPLE]
        try:
            import chardet

            result = chardet.detect(sample)
            enc = (result or {}).get("encoding") or "utf-8"
            return enc
        except ImportError:
            logger.debug(
                "chardet not installed; falling back to utf-8 for text extraction"
            )
            return "utf-8"
