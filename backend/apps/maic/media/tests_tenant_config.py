"""Tests for TenantAIConfig media fields (Phase 9, MAIC-901).

Validates the additive migration applied at courses/0047:
  - 9 new fields (4 image extensions + 5 video) exist with correct defaults
  - Encrypted helpers (set_video_api_key/get_video_api_key) round-trip
  - Existing tenant rows do not break (defaults are sane)

Real ORM, real Postgres (the test DB is a real Postgres clone). No
mocks. Per the no-mocks rule, encrypted-field tests use the actual
Fernet round-trip from utils.encryption — no patching.
"""
from __future__ import annotations

import pytest


def _make_tenant(slug: str = "t-mediacfg"):
    """Helper: tenant + ai_config in one shot. Mirrors the pattern in
    apps/maic_pbl/tests_views.py to keep fixtures consistent."""
    from apps.tenants.models import Tenant
    from apps.courses.maic_models import TenantAIConfig

    tenant = Tenant.objects.create(
        name=slug.upper(), slug=slug, subdomain=slug, is_active=True,
    )
    cfg = TenantAIConfig.objects.create(tenant=tenant)
    return tenant, cfg


# ── Defaults on a fresh row ───────────────────────────────────────────


@pytest.mark.django_db
def test_image_defaults_on_fresh_tenant():
    """A tenant created via TenantAIConfig.objects.create() gets the
    Phase 9 defaults — empty model + base_url, 1024x1024 size,
    'standard' quality, image_provider stays 'pollinations' (the v1
    default; flips per tenant when admin opts in)."""
    _, cfg = _make_tenant("t-img-defaults")
    assert cfg.image_provider == "pollinations"  # legacy default unchanged
    assert cfg.image_model == ""
    assert cfg.image_base_url == ""
    assert cfg.image_default_size == "1024x1024"
    assert cfg.image_default_quality == "standard"


@pytest.mark.django_db
def test_video_defaults_on_fresh_tenant():
    """Video defaults to disabled — opt-in only because clip costs are
    an order of magnitude higher than image generation."""
    _, cfg = _make_tenant("t-vid-defaults")
    assert cfg.video_provider == "disabled"
    assert cfg.video_api_key_encrypted == ""
    assert cfg.video_model == ""
    assert cfg.video_base_url == ""
    assert cfg.video_default_duration == 5


# ── Encrypted helpers: round-trip ─────────────────────────────────────


@pytest.mark.django_db
def test_video_api_key_round_trip_encrypts_at_rest():
    """set_video_api_key('plain') writes a Fernet token; get_video_api_key
    decrypts it. The stored bytes are NOT the plaintext."""
    _, cfg = _make_tenant("t-vid-key")

    cfg.set_video_api_key("sk-veo-secret-12345")
    cfg.save()

    # Stored value is encrypted (not equal to plaintext)
    assert cfg.video_api_key_encrypted != "sk-veo-secret-12345"
    assert "sk-veo-secret-12345" not in cfg.video_api_key_encrypted

    # Round-trip via the helper
    assert cfg.get_video_api_key() == "sk-veo-secret-12345"


@pytest.mark.django_db
def test_video_api_key_empty_returns_empty_string():
    """A fresh row has no key → get_video_api_key() returns "" rather
    than raising. Adapters check the empty string to detect no-config."""
    _, cfg = _make_tenant("t-vid-nokey")
    assert cfg.get_video_api_key() == ""


@pytest.mark.django_db
def test_video_api_key_persists_across_reloads():
    """Encrypted value survives a refresh_from_db — proves the field
    landed on disk via the migration, not just in memory."""
    tenant, cfg = _make_tenant("t-vid-persist")
    cfg.set_video_api_key("the-secret")
    cfg.save()

    # Reload from DB
    from apps.courses.maic_models import TenantAIConfig
    fresh = TenantAIConfig.objects.get(tenant=tenant)
    assert fresh.get_video_api_key() == "the-secret"


# ── Provider choice extensions ────────────────────────────────────────


@pytest.mark.django_db
def test_image_provider_accepts_new_phase9_choices():
    """The 5 new image providers added in MAIC-901 (qwen, grok, minimax,
    nano_banana, seedream) are valid choices on the model. We exercise
    by setting each one + saving — Django validates on full_clean()."""
    _, cfg = _make_tenant("t-img-choices")
    for provider in ("qwen", "grok", "minimax", "nano_banana", "seedream"):
        cfg.image_provider = provider
        cfg.full_clean()  # raises if not in choices


@pytest.mark.django_db
def test_video_provider_choices_match_adapter_roster():
    """The 5 video providers in VIDEO_PROVIDER_CHOICES must match the
    roster Phase 9 will ship adapters for. Drift here = orphaned config
    options. Codified so a future provider addition forces this test
    to update."""
    from apps.courses.maic_models import TenantAIConfig
    expected = {"veo", "kling", "minimax_video", "seedance", "grok_video", "disabled"}
    actual = {choice[0] for choice in TenantAIConfig.VIDEO_PROVIDER_CHOICES}
    assert actual == expected
