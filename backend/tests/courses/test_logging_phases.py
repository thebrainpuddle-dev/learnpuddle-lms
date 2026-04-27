"""
TEST-P1-9: Structured logging phase taxonomy for MAIC code paths.

Verifies:
1. MAICPhase enum exposes the expected stable string values (so log queries
   like ``phase:json_retry`` work in production observability tooling).
2. _call_llm_with_json_retry emits a WARN whose ``extra`` carries
   ``phase="json_retry"`` when a parse failure forces a retry.
3. _enforce_length_budgets emits a WARN whose ``extra`` carries
   ``phase="enforce_budgets"`` when a field is over budget.
"""

import json
import logging
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ai_config(tenant):
    """Minimal TenantAIConfig — HTTP calls are mocked in all tests here."""
    from apps.courses.maic_models import TenantAIConfig
    return TenantAIConfig.objects.create(
        tenant=tenant,
        llm_provider="openrouter",
        llm_model="openrouter/auto",
        llm_base_url="",
        tts_provider="disabled",
    )


# ---------------------------------------------------------------------------
# TEST-P1-9-A: MAICPhase enum exposes stable string values
# ---------------------------------------------------------------------------

def test_maic_phase_enum_values():
    """MAICPhase enum values are stable strings used as ``phase`` field in logs.

    Production observability depends on these strings being stable so that
    saved queries like ``phase:json_retry`` or ``phase:enforce_budgets``
    don't break when the codebase is updated.
    """
    from apps.courses.maic_generation_service import MAICPhase

    assert MAICPhase.GENERATE_PROFILES.value == "generate_profiles"
    assert MAICPhase.GENERATE_SCENE_CONTENT.value == "generate_scene_content"
    assert MAICPhase.GENERATE_SCENE_ACTIONS.value == "generate_scene_actions"
    assert MAICPhase.FILL_IMAGES.value == "fill_images"
    assert MAICPhase.ENFORCE_BUDGETS.value == "enforce_budgets"
    assert MAICPhase.JSON_RETRY.value == "json_retry"

    # Enum members compare equal to their string value because MAICPhase
    # subclasses str.  This is what allows them to serialize directly into
    # the ``extra={}`` dict that the JSON formatter emits.
    assert MAICPhase.JSON_RETRY == "json_retry"
    assert MAICPhase.ENFORCE_BUDGETS == "enforce_budgets"

    # .value is always a plain str (used by _log_extra to stamp the field)
    assert isinstance(MAICPhase.JSON_RETRY.value, str)
    assert isinstance(MAICPhase.ENFORCE_BUDGETS.value, str)


# ---------------------------------------------------------------------------
# TEST-P1-9-B: _call_llm_with_json_retry WARN carries phase="json_retry"
# ---------------------------------------------------------------------------

_NON_JSON = "I'm sorry, I cannot generate that right now."
_GOOD_SCENE = json.dumps({
    "slides": [
        {"id": "slide-1", "title": "Intro", "elements": [],
         "background": "#fff", "speakerScript": "Welcome.", "duration": 40},
    ],
})


@pytest.mark.django_db
@patch("apps.courses.maic_generation_service._call_llm")
def test_json_retry_warn_carries_phase_field(mock_llm, ai_config, caplog):
    """When _call_llm_with_json_retry forces a retry due to non-JSON response,
    the emitted WARN record must carry ``phase="json_retry"`` so ops can
    filter retry rates by phase in production log tooling.
    """
    from apps.courses.maic_generation_service import _call_llm_with_json_retry

    # Attempt 1 fails (non-JSON), attempt 2 succeeds → one WARN emitted.
    mock_llm.side_effect = [_NON_JSON, _GOOD_SCENE]

    with caplog.at_level(logging.WARNING, logger="apps.courses.maic_generation_service"):
        parsed, _raw = _call_llm_with_json_retry(
            ai_config, "system", "user",
            validator=lambda p: isinstance(p, dict) and "slides" in p,
            caller="generate_scene_content:lecture",
            classroom_id="cr-phase-test",
        )

    assert parsed is not None, "Expected successful parse on attempt 2"

    warn_records = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and getattr(r, "metric", None) == "llm_json_retry"
    ]
    assert len(warn_records) == 1, (
        f"Expected 1 retry WARN; got {[r.message for r in warn_records]}"
    )
    rec = warn_records[0]
    # Core assertion: phase field must be the stable JSON_RETRY string.
    assert getattr(rec, "phase", None) == "json_retry", (
        f"phase={getattr(rec, 'phase', '<missing>')!r} — expected 'json_retry'"
    )
    # Correlated fields must also be present.
    assert getattr(rec, "classroom_id", None) == "cr-phase-test"
    assert getattr(rec, "path", None) == "generate_scene_content:lecture"


# ---------------------------------------------------------------------------
# TEST-P1-9-C: _enforce_length_budgets WARN carries phase="enforce_budgets"
# ---------------------------------------------------------------------------

def test_enforce_budgets_warn_carries_phase_field(caplog):
    """When _enforce_length_budgets truncates an over-budget field, the emitted
    WARN must carry ``phase="enforce_budgets"`` so budget-hit rates can be
    filtered independently from retry-rate metrics in production observability.
    """
    from apps.courses.maic_generation_service import (
        _enforce_length_budgets,
        SLIDE_TITLE_MAX_CHARS,
    )

    # A title clearly over the 120-char limit.
    long_title = "A" * 115 + " over budget here"  # 115+17=132 chars
    parsed = {"slides": [{"title": long_title, "elements": []}]}

    with caplog.at_level(logging.WARNING, logger="apps.courses.maic_generation_service"):
        result = _enforce_length_budgets(parsed, "lecture")

    # Truncation happened.
    assert len(result["slides"][0]["title"]) <= SLIDE_TITLE_MAX_CHARS

    warn_records = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and getattr(r, "metric", None) == "length_budget_truncate"
    ]
    assert len(warn_records) == 1, (
        f"Expected 1 budget WARN; got {[r.message for r in warn_records]}"
    )
    rec = warn_records[0]
    # Core assertion: phase field must be the stable ENFORCE_BUDGETS string.
    assert getattr(rec, "phase", None) == "enforce_budgets", (
        f"phase={getattr(rec, 'phase', '<missing>')!r} — expected 'enforce_budgets'"
    )
    # Existing budget-hit fields must still be present.
    assert getattr(rec, "field", None) == "slide.title"
    assert getattr(rec, "original_chars", None) == len(long_title)
    assert getattr(rec, "truncated_chars", None) <= SLIDE_TITLE_MAX_CHARS


# ---------------------------------------------------------------------------
# TEST-P1-9-D: log_extra helper produces expected schema
# ---------------------------------------------------------------------------

def test_log_extra_schema():
    """log_extra returns a dict with stable keys: phase, classroom_id, + rest."""
    from apps.courses.maic_generation_service import log_extra, MAICPhase

    extra = log_extra(
        MAICPhase.JSON_RETRY,
        "cr-abc-123",
        metric="llm_json_retry",
        attempt=1,
        path="generate_scene_content_lecture",
    )
    assert extra["phase"] == "json_retry"
    assert extra["classroom_id"] == "cr-abc-123"
    assert extra["metric"] == "llm_json_retry"
    assert extra["attempt"] == 1
    assert extra["path"] == "generate_scene_content_lecture"


def test_log_extra_classroom_id_defaults_to_empty_string():
    """When classroom_id is None, the field should be '' not None so log
    queries like ``classroom_id:""`` always land on a defined field."""
    from apps.courses.maic_generation_service import log_extra, MAICPhase

    extra_none = log_extra(MAICPhase.ENFORCE_BUDGETS, None)
    assert extra_none["classroom_id"] == ""

    extra_omitted = log_extra(MAICPhase.ENFORCE_BUDGETS)
    assert extra_omitted["classroom_id"] == ""


# ---------------------------------------------------------------------------
# TEST-P1-9-E: Shared helper module is the canonical home for MAICPhase /
#              log_extra; maic_generation_service re-exports for compat.
# ---------------------------------------------------------------------------

def test_log_helpers_module_is_canonical_source():
    """``apps.courses._log_helpers`` is the new shared home; the
    re-exports from ``maic_generation_service`` must remain identical so
    existing call sites (40+) keep working without churn.
    SPRINT-2-BATCH-8-F2: ``_log_extra`` alias deleted; only ``log_extra``."""
    from apps.courses import _log_helpers
    from apps.courses import maic_generation_service as gen

    # Same object identity — re-export, not a copy.
    assert _log_helpers.MAICPhase is gen.MAICPhase
    assert _log_helpers.log_extra is gen.log_extra
    # Alias is gone — no _log_extra attribute on either module.
    assert not hasattr(_log_helpers, "_log_extra")
    assert not hasattr(gen, "_log_extra")

    # New phases added by TEST-P1-9 are present.
    assert _log_helpers.MAICPhase.LLM_CALL.value == "llm_call"
    assert _log_helpers.MAICPhase.IMAGE_FETCH.value == "image_fetch"
    assert _log_helpers.MAICPhase.TTS.value == "tts"
    assert _log_helpers.MAICPhase.CHAT.value == "chat"
    assert _log_helpers.MAICPhase.SIDECAR_PROXY.value == "sidecar_proxy"
    assert _log_helpers.MAICPhase.DEFER_IMAGE_FILL.value == "defer_image_fill"


# ---------------------------------------------------------------------------
# TEST-P1-9-F: image_service per-provider fetch failures emit structured
#              records with phase=image_fetch + provider field.
# ---------------------------------------------------------------------------

def test_image_service_unsplash_429_emits_structured_log(caplog):
    """Unsplash returning 429 must emit a WARN with phase=image_fetch,
    provider=unsplash, status_code=429, outcome=rate_limited so ops can
    filter rate-limited fetches per provider."""
    from unittest.mock import patch, MagicMock

    from apps.courses import image_service
    from apps.courses.image_service import _fetch_unsplash, reset_circuit_breaker_state

    reset_circuit_breaker_state()
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.headers = {}
    with patch.object(image_service.requests, "get", return_value=mock_resp):
        with caplog.at_level(logging.WARNING, logger="apps.courses.image_service"):
            url = _fetch_unsplash("photosynthesis", "fake-key")

    assert url is None  # 429 → fall through, no URL returned

    matched = [
        r for r in caplog.records
        if getattr(r, "metric", None) == "image_fetch_error"
        and getattr(r, "provider", None) == "unsplash"
    ]
    assert len(matched) >= 1, (
        f"Expected at least 1 unsplash WARN; "
        f"records={[(r.message, getattr(r, 'metric', None)) for r in caplog.records]}"
    )
    rec = matched[0]
    assert getattr(rec, "phase", None) == "image_fetch"
    assert getattr(rec, "outcome", None) == "rate_limited"
    assert getattr(rec, "status_code", None) == 429
    # classroom_id is empty string (image_service has no classroom context).
    assert getattr(rec, "classroom_id", None) == ""


def test_image_service_pollinations_timeout_emits_structured_log(caplog):
    """Pollinations.ai timeout must emit a WARN with phase=image_fetch,
    provider=pollinations, outcome=timeout."""
    from unittest.mock import patch

    from apps.courses import image_service
    from apps.courses.image_service import _fetch_pollinations, reset_circuit_breaker_state

    reset_circuit_breaker_state()
    with patch.object(
        image_service.requests, "get",
        side_effect=image_service.requests.exceptions.Timeout(),
    ):
        with caplog.at_level(logging.WARNING, logger="apps.courses.image_service"):
            url = _fetch_pollinations("water cycle")

    assert url is None

    matched = [
        r for r in caplog.records
        if getattr(r, "metric", None) == "image_fetch_error"
        and getattr(r, "provider", None) == "pollinations"
        and getattr(r, "outcome", None) == "timeout"
    ]
    assert len(matched) == 1
    rec = matched[0]
    assert getattr(rec, "phase", None) == "image_fetch"


# ---------------------------------------------------------------------------
# TEST-P1-9-G: TTS fallback paths emit structured records (phase=tts).
# ---------------------------------------------------------------------------

def test_tts_no_api_key_emits_structured_log(tenant, caplog):
    """When a non-edge TTS provider is configured but no API key is
    available, the function logs with phase=tts, metric=tts_no_api_key,
    outcome=edge_fallback so we can grep tenants who haven't configured
    their TTS keys."""
    from unittest.mock import patch

    from apps.courses.maic_models import TenantAIConfig
    from apps.courses.maic_generation_service import generate_tts_audio

    cfg = TenantAIConfig.objects.create(
        tenant=tenant,
        llm_provider="openrouter",
        llm_model="openrouter/auto",
        llm_base_url="",
        tts_provider="elevenlabs",  # non-edge
        # no API key set — get_tts_api_key() returns ""
    )

    with patch(
        "apps.courses.maic_generation_service._tts_edge",
        return_value=None,
    ):
        with caplog.at_level(logging.INFO, logger="apps.courses.maic_generation_service"):
            generate_tts_audio("hello world", cfg)

    matched = [
        r for r in caplog.records
        if getattr(r, "metric", None) == "tts_no_api_key"
    ]
    assert len(matched) == 1
    rec = matched[0]
    assert getattr(rec, "phase", None) == "tts"
    assert getattr(rec, "outcome", None) == "edge_fallback"
    assert getattr(rec, "provider", None) == "elevenlabs"


# ---------------------------------------------------------------------------
# TEST-P1-9-H: LLM-call site emits structured WARN on empty response.
# ---------------------------------------------------------------------------

def test_llm_call_empty_response_emits_structured_log(tenant, caplog):
    """_call_llm logs a WARN with phase=llm_call, metric=llm_empty_response
    when the upstream provider returns no content."""
    from unittest.mock import patch, MagicMock

    from apps.courses.maic_models import TenantAIConfig
    from apps.courses import maic_generation_service as gen

    cfg = TenantAIConfig.objects.create(
        tenant=tenant,
        llm_provider="openrouter",
        llm_model="openrouter/auto",
        llm_base_url="",
        tts_provider="disabled",
    )

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": ""}}]}
    mock_resp.raise_for_status = MagicMock()

    with patch.object(gen.http_requests, "post", return_value=mock_resp):
        with caplog.at_level(logging.WARNING, logger="apps.courses.maic_generation_service"):
            result = gen._call_llm(cfg, "sys", "user")

    assert result is None  # empty content → returns None

    matched = [
        r for r in caplog.records
        if getattr(r, "metric", None) == "llm_empty_response"
    ]
    assert len(matched) == 1
    rec = matched[0]
    assert getattr(rec, "phase", None) == "llm_call"
    assert getattr(rec, "outcome", None) == "empty"
    assert getattr(rec, "provider", None) == "openrouter"
    assert getattr(rec, "model", None) == "openrouter/auto"


# ---------------------------------------------------------------------------
# SPRINT-2-BATCH-8-F1: log_extra sanitises caller-supplied kwargs
# ---------------------------------------------------------------------------

def test_log_extra_strips_unknown_kwarg(caplog):
    """Unknown kwargs (e.g. PII fields like ``email``) must be dropped from
    the returned ``extra`` dict and produce exactly one process-lifetime
    warning per unknown key (subsequent occurrences silenced).

    Defends against:
      * accidental PII leakage into Loki / Datadog,
      * unbounded label cardinality from free-form user-supplied strings.
    """
    from apps.courses import _log_helpers
    from apps.courses._log_helpers import MAICPhase, log_extra

    # Reset the one-shot warning set so this test sees the warning fire.
    _log_helpers._warned_unknown_fields.clear()

    with caplog.at_level(logging.WARNING, logger="apps.courses._log_helpers"):
        extra = log_extra(
            MAICPhase.LLM_CALL,
            "cr-1",
            metric="ok",
            email="x@y.com",          # disallowed — PII
            prompt_fragment="hello",  # disallowed — PII / cardinality risk
        )

    # The disallowed keys must NOT appear in the returned dict.
    assert "email" not in extra
    assert "prompt_fragment" not in extra
    # Allowed key passes through.
    assert extra["metric"] == "ok"
    assert extra["phase"] == "llm_call"
    assert extra["classroom_id"] == "cr-1"

    # Exactly one WARN per dropped field name (one-shot semantics): both
    # "email" and "prompt_fragment" should each have warned once.
    drop_warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "log_extra: dropping unknown field" in r.getMessage()
    ]
    assert len(drop_warnings) == 2, (
        f"expected one warning per disallowed kwarg; got "
        f"{[r.getMessage() for r in drop_warnings]}"
    )

    # A SECOND call with the same disallowed key emits no further warnings.
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="apps.courses._log_helpers"):
        extra2 = log_extra(MAICPhase.LLM_CALL, "cr-2", email="z@y.com")
    assert "email" not in extra2
    silent_drops = [
        r for r in caplog.records
        if "log_extra: dropping unknown field" in r.getMessage()
    ]
    assert silent_drops == [], (
        "unknown-field warning must be one-shot per process to avoid log "
        "amplification on misbehaving callers"
    )


def test_log_extra_truncates_long_string_value():
    """String values exceeding MAX_VALUE_STRING_LEN (200) chars on allowed
    fields are replaced with the literal token ``"<truncated>"`` so we
    don't blow up Loki / Elasticsearch indexing budgets with megabyte
    payloads.  Non-string values pass through untouched.
    """
    from apps.courses._log_helpers import (
        MAICPhase,
        MAX_VALUE_STRING_LEN,
        log_extra,
    )

    long_value = "x" * 500
    short_value = "y" * (MAX_VALUE_STRING_LEN - 1)

    extra = log_extra(
        MAICPhase.LLM_CALL,
        "cr-1",
        error_type=long_value,    # allowed but over-budget → truncated
        outcome=short_value,      # allowed and under budget → passthrough
        attempt=42,               # int → passthrough
    )

    assert extra["error_type"] == "<truncated>"
    assert extra["outcome"] == short_value  # untouched
    assert len(extra["outcome"]) <= MAX_VALUE_STRING_LEN
    assert extra["attempt"] == 42
