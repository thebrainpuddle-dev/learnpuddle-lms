"""DOCX text extractor for TASK-060 — AI Course Generator.

Uses python-docx (python-docx==1.1.2 in requirements.txt).
Caps extraction to 100k chars.
"""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

CHAR_CAP = 100_000


class DOCXExtractor:
    """Extract plain text from a DOCX file-like object."""

    def extract(self, file_obj: io.IOBase) -> str:
        """Return up to CHAR_CAP chars of plain text from a .docx file.

        Args:
            file_obj: A readable binary file-like object.

        Returns:
            Extracted text, potentially truncated.

        Raises:
            RuntimeError: If python-docx is not installed.
        """
        try:
            import docx as python_docx
        except ImportError:
            raise RuntimeError(
                "python-docx is not installed. Add python-docx>=1.1 to requirements.txt."
            )

        document = python_docx.Document(file_obj)
        parts: list[str] = []
        total = 0
        for para in document.paragraphs:
            text = para.text
            if not text:
                continue
            remaining = CHAR_CAP - total
            if len(text) >= remaining:
                parts.append(text[:remaining])
                break
            parts.append(text)
            total += len(text)
        return "\n".join(parts)
