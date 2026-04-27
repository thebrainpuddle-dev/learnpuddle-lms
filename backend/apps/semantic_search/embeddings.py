"""
Embedding provider abstraction (TASK-057).

Provides a single public helper, :func:`embed_texts`, with a fallback
chain that mirrors the quiz-gen / chatbot LLM chain:

    OpenRouter  ──►  Ollama  ──►  StubEmbedder

Provider selection is driven by the ``EMBEDDING_PROVIDER`` env var:

    ``auto``        try openrouter → ollama → stub (DEBUG-only)
    ``openrouter``  force OpenRouter
    ``ollama``      force Ollama
    ``stub``        force StubEmbedder (deterministic hash — dev/tests only)

**Security gate**: the StubEmbedder refuses to run when
``settings.DEBUG`` is False unless ``EMBEDDING_ALLOW_STUB=1`` is set.
This prevents accidental prod-time use of fake vectors.

All real providers use a 20s HTTP timeout, batch size 64, and retry
up to 2x with exponential backoff on transient errors.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
import struct
from typing import Sequence

import requests
from django.conf import settings


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

EMBEDDING_DIM = 1024
EMBEDDING_TIMEOUT = 20.0
EMBEDDING_BATCH_SIZE = 64
EMBEDDING_MAX_RETRIES = 2

DEFAULT_OPENROUTER_MODEL = "mixedbread-ai/mxbai-embed-large-v1"
DEFAULT_OLLAMA_MODEL = "mxbai-embed-large"


class EmbeddingError(Exception):
    """Raised when all configured embedding providers fail."""


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


class _BaseEmbedder:
    name = "base"
    model = ""

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError


class OpenRouterEmbedder(_BaseEmbedder):
    name = "openrouter"

    def __init__(self):
        self.api_key = getattr(settings, "OPENROUTER_API_KEY", "") or os.environ.get(
            "OPENROUTER_API_KEY", ""
        )
        self.base_url = (
            getattr(settings, "OPENROUTER_BASE_URL", "")
            or "https://openrouter.ai/api/v1"
        ).rstrip("/")
        self.model = os.environ.get("OPENROUTER_EMBEDDING_MODEL", DEFAULT_OPENROUTER_MODEL)

    def available(self) -> bool:
        return bool(self.api_key)

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        if not self.api_key:
            raise EmbeddingError("OpenRouter API key not configured")

        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": list(texts),
            # Dimension hint for OpenAI-style embeddings; harmless for others.
            "dimensions": EMBEDDING_DIM,
        }

        last_exc: Exception | None = None
        for attempt in range(EMBEDDING_MAX_RETRIES + 1):
            try:
                resp = requests.post(
                    url, headers=headers, json=payload, timeout=EMBEDDING_TIMEOUT
                )
                resp.raise_for_status()
                data = resp.json()
                vectors = [row["embedding"] for row in data["data"]]
                return _coerce_dimensions(vectors)
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < EMBEDDING_MAX_RETRIES:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                break
            except Exception as exc:  # malformed response etc.
                last_exc = exc
                break

        raise EmbeddingError(f"OpenRouter embed failed: {last_exc}")


class OllamaEmbedder(_BaseEmbedder):
    name = "ollama"

    def __init__(self):
        self.base_url = (
            getattr(settings, "OLLAMA_BASE_URL", "")
            or "http://localhost:11434"
        ).rstrip("/")
        self.model = os.environ.get("OLLAMA_EMBEDDING_MODEL", DEFAULT_OLLAMA_MODEL)

    def available(self) -> bool:
        # Ollama is an opt-in local service; we assume configured if URL set.
        return bool(self.base_url)

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        # Ollama /api/embeddings accepts one prompt at a time. Iterate.
        url = f"{self.base_url}/api/embeddings"
        out: list[list[float]] = []
        for prompt in texts:
            last_exc: Exception | None = None
            for attempt in range(EMBEDDING_MAX_RETRIES + 1):
                try:
                    resp = requests.post(
                        url,
                        json={"model": self.model, "prompt": prompt},
                        timeout=EMBEDDING_TIMEOUT,
                    )
                    resp.raise_for_status()
                    vec = resp.json().get("embedding")
                    if not isinstance(vec, list):
                        raise EmbeddingError("Ollama returned no embedding vector")
                    out.append(vec)
                    break
                except requests.RequestException as exc:
                    last_exc = exc
                    if attempt < EMBEDDING_MAX_RETRIES:
                        time.sleep(0.5 * (2 ** attempt))
                        continue
                    raise EmbeddingError(f"Ollama embed failed: {exc}") from exc
                except Exception as exc:
                    last_exc = exc
                    raise EmbeddingError(f"Ollama embed failed: {exc}") from exc
        return _coerce_dimensions(out)


class StubEmbedder(_BaseEmbedder):
    """
    Deterministic SHA256-derived embedder.

    Never suitable for real retrieval; the vectors have no semantic
    relation to each other. Usable only as a dev/tests fallback so the
    pipeline plumbing can be exercised end-to-end without an external
    API.
    """

    name = "stub"
    model = "stub-sha256-1024"

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        # Gate: refuse to run in production unless explicitly allowed.
        allow_in_prod = os.environ.get("EMBEDDING_ALLOW_STUB", "") == "1"
        if not getattr(settings, "DEBUG", False) and not allow_in_prod:
            raise RuntimeError(
                "StubEmbedder refused: DEBUG=False and EMBEDDING_ALLOW_STUB is not set"
            )
        return [_stub_vector(t) for t in texts]


def _stub_vector(text: str) -> list[float]:
    """
    Deterministic pseudo-embedding. NOT suitable for real search.

    We hash the text with SHA256 and stretch the 256-bit digest into
    EMBEDDING_DIM floats in [-1, 1] by re-hashing with a counter salt.
    """
    vec: list[float] = []
    counter = 0
    while len(vec) < EMBEDDING_DIM:
        h = hashlib.sha256(f"{text}|{counter}".encode("utf-8")).digest()
        # 32 bytes -> 8 float32s (4 bytes each) -> normalised to [-1, 1]
        for i in range(0, 32, 4):
            if len(vec) >= EMBEDDING_DIM:
                break
            (u,) = struct.unpack(">I", h[i : i + 4])
            vec.append((u / 0xFFFFFFFF) * 2.0 - 1.0)
        counter += 1
    return vec[:EMBEDDING_DIM]


def _coerce_dimensions(vectors: list[list[float]]) -> list[list[float]]:
    """
    Force each vector to exactly EMBEDDING_DIM length.

    Truncates longer vectors and right-pads shorter ones with zeros.
    This keeps us safe against model-dim drift from providers.
    """
    out: list[list[float]] = []
    for v in vectors:
        if len(v) == EMBEDDING_DIM:
            out.append(list(v))
        elif len(v) > EMBEDDING_DIM:
            out.append(list(v[:EMBEDDING_DIM]))
        else:
            out.append(list(v) + [0.0] * (EMBEDDING_DIM - len(v)))
    return out


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def get_embedder(provider: str | None = None) -> _BaseEmbedder:
    """Return a concrete embedder based on ``EMBEDDING_PROVIDER`` env.

    ``auto`` (default) tries OpenRouter → Ollama → Stub (DEBUG-only).
    """
    sel = (provider or os.environ.get("EMBEDDING_PROVIDER", "auto") or "auto").lower()

    if sel == "openrouter":
        return OpenRouterEmbedder()
    if sel == "ollama":
        return OllamaEmbedder()
    if sel == "stub":
        return StubEmbedder()

    # auto — return an "auto" wrapper that performs the fallback chain.
    return _AutoEmbedder()


class _AutoEmbedder(_BaseEmbedder):
    """Walk the provider chain on first-embed failure.

    Order: OpenRouter (if key present) → Ollama → Stub (DEBUG only).
    Note: the stub guard inside StubEmbedder.embed_batch enforces the
    production-time refusal independently.
    """

    name = "auto"
    model = ""

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        errors: list[str] = []

        for candidate in (OpenRouterEmbedder(), OllamaEmbedder()):
            if not getattr(candidate, "available", lambda: True)():
                errors.append(f"{candidate.name}: not configured")
                continue
            try:
                result = candidate.embed_batch(texts)
                self.model = candidate.model
                self.name = candidate.name
                return result
            except EmbeddingError as exc:
                errors.append(f"{candidate.name}: {exc}")
                continue
            except Exception as exc:  # unexpected — log and try next
                logger.exception("embedder %s raised unexpectedly", candidate.name)
                errors.append(f"{candidate.name}: {exc}")
                continue

        # Final fallback — stub. Will raise in prod (DEBUG=False) unless allowed.
        stub = StubEmbedder()
        try:
            result = stub.embed_batch(texts)
            self.model = stub.model
            self.name = stub.name
            return result
        except RuntimeError as exc:
            errors.append(f"stub: {exc}")

        raise EmbeddingError(
            "All embedding providers failed: " + "; ".join(errors)
        )


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """
    Embed a batch of texts using the configured provider chain.

    Batches are chunked at ``EMBEDDING_BATCH_SIZE`` automatically.
    Returns a list of 1024-dim float vectors, one per input text.

    Raises :class:`EmbeddingError` when no provider can produce a
    real embedding (or a gated-off stub tries to run in production).
    """
    if not texts:
        return []

    embedder = get_embedder()

    out: list[list[float]] = []
    batch: list[str] = []
    for t in texts:
        batch.append(t)
        if len(batch) >= EMBEDDING_BATCH_SIZE:
            out.extend(embedder.embed_batch(batch))
            batch = []
    if batch:
        out.extend(embedder.embed_batch(batch))

    return out


def embedder_info() -> dict:
    """Return the currently-selected embedder's name + model (best-effort).

    Under ``LLM_PROVIDER=auto``, the _AutoEmbedder resolves its concrete
    provider lazily on the first ``embed_batch`` call.  To avoid returning an
    empty model string on the first call, we probe the provider chain eagerly
    by trying a single-item dummy embed and reading back the resolved name/model.
    """
    try:
        e = get_embedder()
        if not isinstance(e, _AutoEmbedder):
            return {"provider": e.name, "model": getattr(e, "model", "")}

        # _AutoEmbedder — walk the candidate chain without actually embedding.
        # Try each concrete provider in priority order; the first one that is
        # available (and whose .available() returns True) tells us the
        # resolved name + model without making a real HTTP call.
        for candidate in (OpenRouterEmbedder(), OllamaEmbedder()):
            if getattr(candidate, "available", lambda: True)():
                return {"provider": candidate.name, "model": getattr(candidate, "model", "")}

        # Both real providers unavailable — the auto chain would fall back to
        # stub in DEBUG mode.  Report that rather than an empty string.
        return {"provider": "auto", "model": "stub-sha256-1024"}
    except Exception:
        return {"provider": "unknown", "model": ""}
