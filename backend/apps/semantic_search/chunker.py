"""
Text chunker for the semantic_search pipeline (TASK-057).

Uses a cheap whitespace-token heuristic (``len(text.split())``) so we
don't take on a tokenizer dependency. Window/stride defaults produce
~150-token overlap at stride=450 for a 600-token window.
"""

from __future__ import annotations

from typing import Iterable, List, Tuple


DEFAULT_WINDOW = 600
DEFAULT_STRIDE = 450


def chunk_text(
    text: str,
    window: int = DEFAULT_WINDOW,
    stride: int = DEFAULT_STRIDE,
) -> List[Tuple[int, str]]:
    """
    Split ``text`` into overlapping windowed chunks.

    - Returns ``[(chunk_index, chunk_text), ...]`` starting at index 0.
    - Short text (token count <= ``window``) returns a single chunk
      ``[(0, text)]`` unchanged (after whitespace trim).
    - Empty / whitespace-only chunks are skipped.
    """

    if not text or not text.strip():
        return []

    tokens = text.split()
    if window <= 0 or stride <= 0:
        raise ValueError("window and stride must be positive integers")

    if len(tokens) <= window:
        stripped = text.strip()
        return [(0, stripped)] if stripped else []

    chunks: List[Tuple[int, str]] = []
    idx = 0
    start = 0
    while start < len(tokens):
        end = start + window
        window_tokens = tokens[start:end]
        piece = " ".join(window_tokens).strip()
        if piece:
            chunks.append((idx, piece))
            idx += 1
        if end >= len(tokens):
            break
        start += stride

    return chunks


def iter_chunks(
    texts: Iterable[str],
    window: int = DEFAULT_WINDOW,
    stride: int = DEFAULT_STRIDE,
) -> List[Tuple[int, str]]:
    """Concatenate and chunk multiple text blobs. Used when pre-joining
    transcript segments into a single stream."""
    joined = "\n\n".join([t for t in texts if t and t.strip()])
    return chunk_text(joined, window=window, stride=stride)
