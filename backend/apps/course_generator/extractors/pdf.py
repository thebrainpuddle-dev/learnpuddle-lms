"""PDF text extractor for TASK-060 — AI Course Generator.

Uses pypdf>=4.0 (the successor to PyPDF2, renamed at v4) or falls back
to pdfminer.six if available.  Caps extraction to 100k chars.
"""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

# Character cap per spec
CHAR_CAP = 100_000
# Maximum pages to scan (safety limit to avoid memory pressure on huge PDFs)
MAX_PAGES = 300


class PDFExtractor:
    """Extract plain text from a PDF file-like object."""

    def extract(self, file_obj: io.IOBase) -> str:
        """Return up to CHAR_CAP chars of plain text.

        Args:
            file_obj: A readable binary file-like object.

        Returns:
            Extracted text, potentially truncated.

        Raises:
            RuntimeError: If no PDF library is available.
        """
        try:
            return self._extract_pypdf2(file_obj)
        except ImportError:
            pass

        try:
            return self._extract_pdfminer(file_obj)
        except ImportError:
            pass

        raise RuntimeError(
            "No PDF extraction library available. "
            "Install pypdf>=4.0 or pdfminer.six."
        )

    @staticmethod
    def _extract_pypdf2(file_obj: io.IOBase) -> str:
        from pypdf import PdfReader  # pypdf>=4.0 (successor to PyPDF2)

        reader = PdfReader(file_obj)
        pages = reader.pages[:MAX_PAGES]
        parts: list[str] = []
        total = 0
        for page in pages:
            text = page.extract_text() or ""
            remaining = CHAR_CAP - total
            if len(text) >= remaining:
                parts.append(text[:remaining])
                total += remaining
                break
            parts.append(text)
            total += len(text)
        return "\n".join(parts)

    @staticmethod
    def _extract_pdfminer(file_obj: io.IOBase) -> str:
        from pdfminer.high_level import extract_text_to_fp
        from pdfminer.layout import LAParams

        buf = io.StringIO()
        extract_text_to_fp(file_obj, buf, laparams=LAParams(), output_type="text")
        text = buf.getvalue()
        return text[:CHAR_CAP]
