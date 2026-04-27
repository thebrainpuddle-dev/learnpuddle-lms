"""Structured-logging helpers for MAIC code paths (TEST-P1-9).

Centralizes the ``MAICPhase`` taxonomy and the ``log_extra`` builder so
view, service, task, and image-pipeline modules can attach the same
structured fields (``phase``, ``classroom_id``, ``metric``, ``outcome``,
…) without each module re-defining its own helper.

The previous home for these symbols was ``maic_generation_service`` —
which made tasks and views import a heavy generation module just to emit
a log record.  ``apps.courses.maic_generation_service`` keeps re-exports
of ``MAICPhase`` / ``log_extra`` for backwards compatibility.

Usage::

    from apps.courses._log_helpers import MAICPhase, log_extra

    logger.warning(
        "image fetch failed for %r", keyword,
        extra=log_extra(
            MAICPhase.IMAGE_FETCH,
            classroom_id=classroom_id,
            metric="image_fetch_error",
            outcome="provider_5xx",
            provider="unsplash",
        ),
    )

Production observability tooling (Loki / Datadog / GCP Logging) can
filter by ``phase``, ``metric``, or ``outcome`` without grepping
free-text messages.

Field allowlist (SPRINT-2-BATCH-8-F1)
-------------------------------------

The ``log_extra`` helper enforces an allowlist of caller-supplied
keyword arguments via ``ALLOWED_FIELDS``.  Unknown fields are stripped
(with a one-shot warning per process) before being merged into the
``extra={}`` dict so we cannot accidentally:

  * leak PII (emails, raw user prompts, …) into Loki/Datadog,
  * blow up label cardinality with free-form caller-supplied strings.

String values that ARE allowed are still capped at
``MAX_VALUE_STRING_LEN`` characters; longer values are replaced with
``"<truncated>"``.  ``keyword`` itself is intentionally NOT in the
allowlist — callers in ``image_service`` already truncate it to 80
chars and emit it as ``keyword_len`` instead.
"""

from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class MAICPhase(str, Enum):
    """Stable string values used as the ``phase`` field on every MAIC log record.

    Adding a new phase: pick a snake_case label that maps to an
    independently observable code path.  Once added, do NOT rename the
    string value — saved log queries break silently otherwise.
    """

    GENERATE_PROFILES = "generate_profiles"
    GENERATE_SCENE_CONTENT = "generate_scene_content"
    GENERATE_SCENE_ACTIONS = "generate_scene_actions"
    FILL_IMAGES = "fill_images"
    ENFORCE_BUDGETS = "enforce_budgets"
    JSON_RETRY = "json_retry"

    # New phases (TEST-P1-9 expansion).
    LLM_CALL = "llm_call"            # Raw LLM HTTP request lifecycle.
    IMAGE_FETCH = "image_fetch"      # image_service per-provider fetches.
    TTS = "tts"                      # Direct + Edge TTS generation.
    CHAT = "chat"                    # Teacher / student chat fallback path.
    SIDECAR_PROXY = "sidecar_proxy"  # OpenMAIC sidecar proxy lifecycle.
    DEFER_IMAGE_FILL = "defer_image_fill"  # Sync handoff to fill_classroom_images.


# SPRINT-2-BATCH-8-F1: allowlist of caller-supplied kwargs for ``log_extra``.
#
# Rules for adding a field here:
#   * Must be safely-bounded cardinality (enum, small int, hashed id) OR
#     truncatable to MAX_VALUE_STRING_LEN without losing meaning.
#   * MUST NOT be raw user input (prompts, emails, free-form keywords).
#   * Document why it is needed in observability dashboards.
ALLOWED_FIELDS: frozenset[str] = frozenset({
    # Universal taxonomy.
    "metric",          # short snake_case label, e.g. "image_fetch_error"
    "outcome",         # terminal status, e.g. "success", "fallback"
    "attempt",         # retry index (1-based int)
    "attempts",        # int — total attempts taken
    "provider",        # third-party service name (enum-ish)
    "model",           # LLM model id (provider-bounded)
    "error_type",      # type(exc).__name__
    "status_code",     # HTTP status code
    "path",            # caller path label (TEST-P1-10 stable values)
    "caller",          # legacy alias of `path` in some modules
    "task_id",         # Celery task id (UUID — high cardinality but bounded)
    "request_id",      # X-Request-ID for correlation
    "audience",        # enum-ish — who the log targets (e.g. "ops", "dev")

    # Per-phase contextual fields used in dashboards.
    "scene_idx",       # int — bounded by scene count
    "scene_id",        # UUID-ish
    "scene_type",      # enum: lecture/quiz/interactive/scene_actions
    "scene_count",     # int — total scenes in classroom
    "el_idx",          # int — element index inside a slide
    "element_id",      # UUID-ish
    "slide_idx",       # int — slide index inside a scene
    "slide_id",        # UUID-ish
    "agent_idx",       # int — agent index
    "field",           # length-budget field name, e.g. "slide.title"
    "original_chars",  # int
    "truncated_chars", # int
    "keyword_len",     # int — explicitly NOT raw `keyword`
    "duration_ms",     # int/float — measured timings
    "duration_s",      # float — measured timings
    "elapsed_ms",      # int/float
    "bytes",           # int — payload sizes (legacy alias of size_bytes)
    "size_bytes",      # int — payload sizes
    "count",           # int — generic count field
    "items",           # int — generic item count
    "n",               # int — generic count
    "retry_after",     # int/float — Retry-After header value
    "circuit_state",   # enum: open/closed/half_open
    "cooldown_s",      # int/float
    "cooldown_seconds",  # int/float — alias used in image_service
    "countdown_seconds", # int/float — Celery countdown
    "timeout_seconds",   # int/float — request timeout
    "failure_count",     # int — circuit-breaker failure count
    "language",        # ISO language code (enum-ish)
    "voice",           # bounded TTS voice id
    "voice_id",        # bounded TTS voice id alias
    "tts_provider",    # enum: edge/elevenlabs/disabled
    "image_provider",  # enum: imagen/unsplash/pexels/pollinations/placeholder
    "content_type",    # HTTP Content-Type (enum-ish)
    "fallback_reason", # enum-ish: reason code
    "skipped_reason",  # enum-ish: reason code
    "stage",           # generic enum-ish stage name
    "from_state",      # state-machine transition labels
    "to_state",        # state-machine transition labels
    "course_id",       # UUID — bounded by tenant
    "user_id",         # UUID — bounded by tenant
    "tenant_id",       # UUID — bounded
    "victim_tenant_id",  # UUID — SEC-P1-CROSS-TENANT-IMAGE-FILL: target tenant on cross-tenant miss
    "lesson_id",       # UUID
    "module_id",       # UUID
    "content_id",      # UUID
    "diff_key",        # enum-ish — bounded set of comparison keys
    "storage_key",     # bounded path-like — sanitised by caller
    "upstream_url",    # bounded — sanitised before logging
    "filled",          # int — number of items filled
    "skipped",         # int — number of items skipped
    "errors",          # int — number of errors encountered
})

#: Maximum length (chars) for any string value in the ``extra`` dict.
MAX_VALUE_STRING_LEN: int = 200

# We log at most one warning per unknown field name across the process
# lifetime to avoid log amplification when a misbehaving caller fires
# the same dropped field on every log line.
_warned_unknown_fields: set[str] = set()


def _coerce_value(name: str, value):
    """Truncate over-long strings to keep observability backends safe.

    Non-string values (ints, floats, bools, None) pass through untouched
    so cardinality / type stability is preserved per-field.
    """
    if isinstance(value, str) and len(value) > MAX_VALUE_STRING_LEN:
        return "<truncated>"
    return value


def log_extra(
    phase: MAICPhase,
    classroom_id: str | None = None,
    **rest,
) -> dict:
    """Return a stable ``extra={}`` dict for structured MAIC log records.

    Always emits:
        - ``phase`` — string value of the enum (never the Enum object).
        - ``classroom_id`` — empty string when not available, so log
          queries like ``classroom_id:""`` always land on a defined
          field (Loki / Elasticsearch treat missing fields differently
          from empty strings).

    Caller-supplied keyword arguments are filtered against
    :data:`ALLOWED_FIELDS` (SPRINT-2-BATCH-8-F1).  Unknown fields are
    dropped silently after a one-shot warning per process to prevent
    PII leakage and unbounded label cardinality.  String values are
    truncated to :data:`MAX_VALUE_STRING_LEN` characters.

    Conventional fields used across the codebase:
        ``metric``    — short snake_case label (e.g. ``"image_fill_complete"``).
        ``outcome``   — terminal status (e.g. ``"success"``, ``"fallback"``).
        ``attempt``   — retry index (1-based).
        ``provider``  — third-party service name (e.g. ``"unsplash"``).
        ``error_type``— ``type(exc).__name__`` for caught exceptions.

    Examples::

        log_extra(MAICPhase.IMAGE_FETCH, classroom_id, metric="image_fetch_error",
                  outcome="provider_429", provider="pexels", attempt=1)
        log_extra(MAICPhase.TTS, metric="tts_fallback", outcome="edge_tts",
                  provider="azure")
    """
    sanitized: dict = {}
    for key, value in rest.items():
        if key not in ALLOWED_FIELDS:
            if key not in _warned_unknown_fields:
                _warned_unknown_fields.add(key)
                logger.warning(
                    "log_extra: dropping unknown field %r (not in ALLOWED_FIELDS); "
                    "subsequent occurrences silenced. "
                    "If legitimate, add to ALLOWED_FIELDS in apps/courses/_log_helpers.py.",
                    key,
                )
            continue
        sanitized[key] = _coerce_value(key, value)

    return {
        "phase": phase.value,
        "classroom_id": classroom_id or "",
        **sanitized,
    }


__all__ = [
    "MAICPhase",
    "log_extra",
    "ALLOWED_FIELDS",
    "MAX_VALUE_STRING_LEN",
]
