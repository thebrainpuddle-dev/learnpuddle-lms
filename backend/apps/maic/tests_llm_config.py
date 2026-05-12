from __future__ import annotations

import pytest
from django.test import override_settings

from apps.courses.maic_models import TenantAIConfig
from apps.maic.exceptions import MaicConfigError
from apps.maic.llm_config import (
    resolve_request_language_model_id,
    resolve_tenant_llm_runtime_config,
)
from apps.tenants.models import Tenant


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(
        name="LLM School",
        slug="llm-school",
        feature_maic_v2=True,
    )


def _config(tenant, *, provider="openrouter", model="openai/gpt-4o-mini", enabled=True):
    return TenantAIConfig.objects.create(
        tenant=tenant,
        maic_enabled=enabled,
        llm_provider=provider,
        llm_model=model,
    )


@pytest.mark.django_db
@override_settings(MAIC_V2_ALLOW_STUB=False, MAIC_V2_ALLOW_REQUEST_MODEL_OVERRIDE=False)
def test_resolves_default_from_tenant_config(tenant):
    _config(tenant)

    assert (
        resolve_request_language_model_id(tenant_id=tenant.id)
        == "openrouter/openai/gpt-4o-mini"
    )


@pytest.mark.django_db
@override_settings(MAIC_V2_ALLOW_STUB=False, MAIC_V2_ALLOW_REQUEST_MODEL_OVERRIDE=False)
def test_rejects_client_override_when_disabled(tenant):
    _config(tenant)

    with pytest.raises(MaicConfigError, match="override"):
        resolve_request_language_model_id(
            tenant_id=tenant.id,
            requested="openrouter/anthropic/claude-3.5-sonnet",
        )


@pytest.mark.django_db
@override_settings(MAIC_V2_ALLOW_STUB=False, MAIC_V2_ALLOW_REQUEST_MODEL_OVERRIDE=False)
def test_accepts_requested_model_when_it_matches_tenant_config(tenant):
    _config(tenant, provider="openai", model="gpt-4.1")

    assert (
        resolve_request_language_model_id(tenant=tenant, requested="gpt-4.1")
        == "gpt-4.1"
    )


@pytest.mark.django_db
@override_settings(MAIC_V2_ALLOW_STUB=False)
def test_rejects_stub_when_disabled(tenant):
    _config(tenant)

    with pytest.raises(MaicConfigError, match="stub"):
        resolve_request_language_model_id(tenant=tenant, requested="stub")


@override_settings(MAIC_V2_ALLOW_STUB=True)
def test_allows_stub_only_when_explicitly_enabled():
    assert resolve_request_language_model_id(requested="stub") == "stub"


@pytest.mark.django_db
@override_settings(MAIC_V2_ALLOW_STUB=False)
def test_maps_ollama_tenant_config(tenant):
    _config(tenant, provider="ollama", model="llama3.2:3b")

    assert resolve_request_language_model_id(tenant_id=tenant.id) == "ollama/llama3.2:3b"


@pytest.mark.django_db
@override_settings(MAIC_V2_ALLOW_STUB=False)
def test_runtime_config_decrypts_tenant_key_without_env(monkeypatch, tenant):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    cfg = _config(tenant)
    cfg.set_llm_api_key("tenant-key-a")
    cfg.save(update_fields=["llm_api_key_encrypted"])

    runtime = resolve_tenant_llm_runtime_config(tenant_id=tenant.id)

    assert runtime["language_model_id"] == "openrouter/openai/gpt-4o-mini"
    assert runtime["api_key"] == "tenant-key-a"


@pytest.mark.django_db
@override_settings(MAIC_V2_ALLOW_STUB=False)
def test_runtime_config_requires_external_provider_key(tenant):
    _config(tenant)

    with pytest.raises(MaicConfigError, match="llm_api_key"):
        resolve_tenant_llm_runtime_config(tenant_id=tenant.id)


@pytest.mark.django_db
@override_settings(MAIC_V2_ALLOW_STUB=False)
def test_runtime_config_ollama_does_not_require_key(tenant):
    _config(tenant, provider="ollama", model="llama3.2:3b")

    runtime = resolve_tenant_llm_runtime_config(tenant_id=tenant.id)

    assert runtime["language_model_id"] == "ollama/llama3.2:3b"
    assert runtime["api_key"] == ""


@pytest.mark.django_db
@override_settings(MAIC_V2_ALLOW_STUB=False)
def test_runtime_config_rejects_unsafe_base_url(tenant):
    cfg = _config(tenant)
    cfg.set_llm_api_key("tenant-key-a")
    cfg.llm_base_url = "http://127.0.0.1:11434"
    cfg.save(update_fields=["llm_api_key_encrypted", "llm_base_url"])

    with pytest.raises(MaicConfigError, match="unsafe"):
        resolve_tenant_llm_runtime_config(tenant_id=tenant.id)
