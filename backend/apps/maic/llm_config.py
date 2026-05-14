"""Tenant-scoped LLM resolution for MAIC v2.

Production MAIC v2 should not trust a browser-supplied model id or fall
back to the deterministic test stub. The tenant's `TenantAIConfig` is the
source of truth for which provider/model a school is allowed to use.
"""
from __future__ import annotations

from typing import Any

from django.conf import settings

from apps.maic.exceptions import MaicConfigError


_STUB_MODEL_IDS = {"stub", "stub-director"}


def resolve_request_language_model_id(
    *,
    tenant: Any | None = None,
    tenant_id: Any | None = None,
    requested: Any | None = None,
) -> str:
    """Resolve a request's MAIC v2 model id against tenant config.

    `requested` is accepted only when it matches the tenant's configured
    model, or when the deploy explicitly allows overrides for local/dev
    probes. This keeps production schools on their own configured provider.
    """
    requested_id = _clean_requested_model_id(requested)

    if requested_id in _STUB_MODEL_IDS:
        if _stub_allowed():
            return requested_id
        raise MaicConfigError(
            "languageModelId 'stub' is disabled; configure this school's "
            "TenantAIConfig instead"
        )

    config = get_tenant_ai_config(tenant=tenant, tenant_id=tenant_id)
    tenant_model_id = language_model_id_from_config(config)
    return _resolve_requested_against_config(config, tenant_model_id, requested_id)


def resolve_tenant_llm_runtime_config(
    *,
    tenant: Any | None = None,
    tenant_id: Any | None = None,
    requested: Any | None = None,
) -> dict[str, str | None]:
    """Return non-persistent runtime kwargs for the v2 AI adapter.

    The returned dict may contain a decrypted API key. It must stay in
    memory only and must never be stored in job/session JSON.
    """
    config = get_tenant_ai_config(tenant=tenant, tenant_id=tenant_id)
    tenant_model_id = language_model_id_from_config(config)
    requested_id = _clean_requested_model_id(requested)
    language_model_id = _resolve_requested_against_config(
        config,
        tenant_model_id,
        requested_id,
    )
    provider = str(config.llm_provider or "").strip().lower()
    api_key = _resolve_api_key(config, provider)
    base_url = _resolve_safe_base_url(config, provider)

    return {
        "language_model_id": language_model_id,
        "provider": provider,
        "model": str(config.llm_model or "").strip(),
        "api_key": api_key,
        "base_url": base_url,
    }


def _resolve_requested_against_config(
    config: Any,
    tenant_model_id: str,
    requested_id: str,
) -> str:
    if requested_id in _STUB_MODEL_IDS:
        if _stub_allowed():
            return requested_id
        raise MaicConfigError(
            "languageModelId 'stub' is disabled; configure this school's "
            "TenantAIConfig instead"
        )

    if not requested_id:
        return tenant_model_id

    if _request_override_allowed():
        return requested_id

    requested_for_provider = _language_model_id_for_provider(
        str(config.llm_provider or ""),
        requested_id,
    )
    if requested_id == tenant_model_id or requested_for_provider == tenant_model_id:
        return tenant_model_id

    raise MaicConfigError(
        "languageModelId override is not allowed; this school's "
        "TenantAIConfig controls MAIC v2 provider/model"
    )


def get_tenant_ai_config(*, tenant: Any | None = None, tenant_id: Any | None = None):
    """Load the enabled TenantAIConfig row for a tenant.

    Uses `all_tenants()` when available because websocket/Celery paths do
    not always run with tenant middleware thread-local state set.
    """
    from apps.courses.maic_models import TenantAIConfig

    resolved_tenant_id = (
        tenant_id if tenant_id is not None else getattr(tenant, "id", None)
    )
    if resolved_tenant_id is None:
        raise MaicConfigError("tenant is required to resolve MAIC v2 LLM config")

    manager = TenantAIConfig.objects
    qs = manager.all_tenants() if hasattr(manager, "all_tenants") else manager
    config = qs.filter(tenant_id=resolved_tenant_id).first()
    if config is None:
        raise MaicConfigError(
            "this school has no TenantAIConfig; configure MAIC AI settings first"
        )
    if not config.maic_enabled:
        raise MaicConfigError("MAIC is disabled in this school's TenantAIConfig")
    return config


def language_model_id_from_config(config: Any) -> str:
    provider = str(getattr(config, "llm_provider", "") or "")
    model = str(getattr(config, "llm_model", "") or "").strip()
    if not model:
        raise MaicConfigError("TenantAIConfig.llm_model is required for MAIC v2")
    if model in _STUB_MODEL_IDS:
        if _stub_allowed():
            return model
        raise MaicConfigError(
            "TenantAIConfig.llm_model cannot be 'stub' when MAIC_V2_ALLOW_STUB is false"
        )
    return _language_model_id_for_provider(provider, model)


def _language_model_id_for_provider(provider: str, model: str) -> str:
    provider_id = provider.strip().lower()
    model_id = model.strip()
    model_lower = model_id.lower()
    if not provider_id:
        raise MaicConfigError("TenantAIConfig.llm_provider is required for MAIC v2")
    if not model_id:
        raise MaicConfigError("TenantAIConfig.llm_model is required for MAIC v2")

    if provider_id == "openrouter":
        return (
            model_id
            if model_lower.startswith("openrouter/")
            else f"openrouter/{model_id}"
        )

    if provider_id == "openai":
        if (
            model_lower.startswith("openai/")
            or model_lower.startswith("gpt-")
            or model_lower in {"o1", "o3", "o4"}
            or model_lower.startswith("o1-")
            or model_lower.startswith("o3-")
            or model_lower.startswith("o4-")
        ):
            return model_id
        return f"openai/{model_id}"

    if provider_id == "anthropic":
        return (
            model_id
            if model_lower.startswith("anthropic/") or model_lower.startswith("claude-")
            else f"anthropic/{model_id}"
        )

    if provider_id == "ollama":
        if model_lower.startswith("ollama/") or model_lower.startswith("ollama:"):
            return model_id
        return f"ollama/{model_id}"

    raise MaicConfigError(
        f"TenantAIConfig.llm_provider {provider!r} is not supported by MAIC v2 yet; "
        "use openai, anthropic, openrouter, or ollama"
    )


def _clean_requested_model_id(requested: Any | None) -> str:
    if requested is None or requested == "":
        return ""
    if not isinstance(requested, str):
        raise MaicConfigError("languageModelId must be a string")
    cleaned = requested.strip()
    if not cleaned:
        raise MaicConfigError("languageModelId must be a non-empty string")
    return cleaned


def _resolve_api_key(config: Any, provider: str) -> str:
    if provider == "ollama":
        return ""

    api_key = (
        config.get_llm_api_key()
        if getattr(config, "llm_api_key_encrypted", "")
        else ""
    )
    if not api_key:
        raise MaicConfigError(
            "TenantAIConfig.llm_api_key is required for MAIC v2 provider "
            f"{provider!r}"
        )
    return api_key


def _resolve_safe_base_url(config: Any, provider: str) -> str | None:
    raw_base_url = str(getattr(config, "llm_base_url", "") or "").strip().rstrip("/")
    if not raw_base_url:
        return None
    if provider == "ollama":
        # Local/private Ollama endpoints are deployment infrastructure, not
        # school-admin-controlled outbound URLs. The adapter uses
        # OLLAMA_BASE_URL for that path.
        return None

    from utils.url_safety import UnsafeURLError, validate_outbound_url

    try:
        validate_outbound_url(
            f"{raw_base_url}/chat/completions",
            allowed_schemes=("https",),
        )
    except UnsafeURLError as exc:
        raise MaicConfigError(f"TenantAIConfig.llm_base_url is unsafe: {exc}") from exc
    return raw_base_url


def _stub_allowed() -> bool:
    return bool(getattr(settings, "MAIC_V2_ALLOW_STUB", False))


def _request_override_allowed() -> bool:
    return bool(getattr(settings, "MAIC_V2_ALLOW_REQUEST_MODEL_OVERRIDE", False))
