from __future__ import annotations

import pytest


pytestmark = pytest.mark.django_db


def test_tenant_ai_config_rejects_unsafe_llm_base_url(admin_client, tenant):
    from apps.courses.maic_models import TenantAIConfig

    resp = admin_client.patch(
        "/api/v1/tenants/settings/ai/",
        {"llm_base_url": "http://127.0.0.1:11434"},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert "Unsafe llm_base_url" in resp.json()["error"]
    config = TenantAIConfig.objects.get(tenant=tenant)
    assert config.llm_base_url == ""


def test_sidecar_proxy_headers_do_not_forward_unsafe_llm_base_url(tenant):
    from apps.courses.maic_models import TenantAIConfig
    from apps.courses.maic_views import _build_proxy_headers

    config = TenantAIConfig.objects.create(
        tenant=tenant,
        maic_enabled=True,
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        llm_base_url="http://127.0.0.1:11434",
    )

    headers = _build_proxy_headers(config)

    assert "x-base-url" not in headers
