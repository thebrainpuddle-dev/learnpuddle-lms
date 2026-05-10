"""Tests for TenantAIConfig PDF fields (Phase 10, MAIC-1001).

Mirrors apps/maic/media/tests_tenant_config.py shape. Real ORM, real
Fernet round-trip, no mocks.
"""
from __future__ import annotations

import pytest


def _make_tenant(slug: str = "t-pdfcfg"):
    from apps.tenants.models import Tenant
    from apps.courses.maic_models import TenantAIConfig
    tenant = Tenant.objects.create(
        name=slug.upper(), slug=slug, subdomain=slug, is_active=True,
    )
    cfg = TenantAIConfig.objects.create(tenant=tenant)
    return tenant, cfg


# ── Defaults ──────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_pdf_defaults_on_fresh_tenant():
    """PDF defaults to disabled — opt-in only. Cloud parsing has
    non-trivial per-page cost; don't enable by accident."""
    _, cfg = _make_tenant("t-pdf-defaults")
    assert cfg.pdf_provider == "disabled"
    assert cfg.mineru_api_key_encrypted == ""
    assert cfg.mineru_base_url == ""


# ── Fernet round-trip ────────────────────────────────────────────────


@pytest.mark.django_db
def test_mineru_api_key_round_trip_encrypts_at_rest():
    """set_mineru_api_key writes a Fernet token; get_mineru_api_key
    decrypts. Stored bytes are NOT plaintext."""
    _, cfg = _make_tenant("t-mineru-key")
    cfg.set_mineru_api_key("mr-test-key-abc123")
    cfg.save()

    assert cfg.mineru_api_key_encrypted != "mr-test-key-abc123"
    assert "mr-test-key-abc123" not in cfg.mineru_api_key_encrypted
    assert cfg.get_mineru_api_key() == "mr-test-key-abc123"


@pytest.mark.django_db
def test_mineru_api_key_empty_returns_empty_string():
    _, cfg = _make_tenant("t-mineru-nokey")
    assert cfg.get_mineru_api_key() == ""


@pytest.mark.django_db
def test_mineru_api_key_persists_across_reloads():
    tenant, cfg = _make_tenant("t-mineru-persist")
    cfg.set_mineru_api_key("persistent-key")
    cfg.save()

    from apps.courses.maic_models import TenantAIConfig
    fresh = TenantAIConfig.objects.get(tenant=tenant)
    assert fresh.get_mineru_api_key() == "persistent-key"


# ── Provider choices ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_pdf_provider_accepts_phase10_choices():
    _, cfg = _make_tenant("t-pdf-choices")
    for provider in ("mineru", "disabled"):
        cfg.pdf_provider = provider
        cfg.full_clean()  # raises if not in choices


@pytest.mark.django_db
def test_pdf_provider_choices_match_planned_roster():
    """Lock cardinality — adding a provider here forces this test to
    update, which forces brain docs + adapter ticket to ship together."""
    from apps.courses.maic_models import TenantAIConfig
    expected = {"mineru", "disabled"}
    actual = {c[0] for c in TenantAIConfig.PDF_PROVIDER_CHOICES}
    assert actual == expected
