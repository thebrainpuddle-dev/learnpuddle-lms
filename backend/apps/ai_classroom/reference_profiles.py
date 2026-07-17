from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .models import TenantAIProviderCredential, TenantAIRuntimeConfig


REFERENCE_PROFILE_ID = "openmaic-153195ca-default-v1"
REFERENCE_PROFILE_SHA256 = "cb99093bf90d58ac2b8ecb7bd1f4f38446e28e6dfa50ee7e8df3802e514b850e"
PROFILE_DIRECTORY = Path(__file__).with_name("reference_profiles")


def _canonical_bytes(profile: dict) -> bytes:
    return json.dumps(
        profile,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def load_reference_profile(profile_id: str = REFERENCE_PROFILE_ID) -> dict:
    path = PROFILE_DIRECTORY / f"{profile_id}.json"
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ImproperlyConfigured(
            f"Unable to load OpenMAIC reference profile {profile_id}"
        ) from exc
    if not isinstance(profile, dict) or profile.get("id") != profile_id:
        raise ImproperlyConfigured(f"Invalid OpenMAIC reference profile {profile_id}")
    if not isinstance(profile.get("providers"), list) or not isinstance(
        profile.get("settings"), dict
    ):
        raise ImproperlyConfigured(f"Incomplete OpenMAIC reference profile {profile_id}")
    if profile_id == REFERENCE_PROFILE_ID:
        digest = hashlib.sha256(_canonical_bytes(profile)).hexdigest()
        if digest != REFERENCE_PROFILE_SHA256:
            raise ImproperlyConfigured(
                f"OpenMAIC reference profile {profile_id} fingerprint mismatch"
            )
    return profile


def reference_profile_sha256(profile: dict) -> str:
    return hashlib.sha256(_canonical_bytes(profile)).hexdigest()


def reference_profile_payload(profile_id: str = REFERENCE_PROFILE_ID) -> dict:
    profile = load_reference_profile(profile_id)
    return {
        "id": profile["id"],
        "sha256": reference_profile_sha256(profile),
        "upstream_sha": profile["upstream_sha"],
        "integration_schema": profile["integration_schema"],
        "settings": profile["settings"],
    }


def profile_readiness_errors(tenant, profile_id: str = REFERENCE_PROFILE_ID) -> list[str]:
    profile = load_reference_profile(profile_id)
    digest = reference_profile_sha256(profile)
    config = TenantAIRuntimeConfig.all_objects.filter(tenant=tenant).first()
    errors = []
    if not config:
        errors.append("AI runtime configuration does not exist")
    elif config.reference_profile_id != profile_id or config.reference_profile_sha256 != digest:
        errors.append("tenant reference-profile fingerprint does not match the certified profile")

    expected = {(entry["modality"], entry["provider_id"]): entry for entry in profile["providers"]}
    credentials = {
        (credential.modality, credential.provider_id): credential
        for credential in TenantAIProviderCredential.all_objects.filter(tenant=tenant)
    }
    enabled = {key for key, credential in credentials.items() if credential.is_enabled}
    unexpected = sorted(enabled - set(expected))
    if unexpected:
        errors.append(
            "unexpected enabled providers: "
            + ", ".join(f"{modality}:{provider}" for modality, provider in unexpected)
        )

    for key, entry in expected.items():
        credential = credentials.get(key)
        label = f"{key[0]}:{key[1]}"
        if not credential:
            errors.append(f"missing provider {label}")
            continue
        if not credential.is_enabled or not credential.is_default:
            errors.append(f"provider {label} must be enabled and default")
        if not credential.api_key_encrypted:
            errors.append(f"provider {label} has no managed key")
        if credential.base_url != entry.get("base_url", ""):
            errors.append(f"provider {label} base URL does not match the profile")
        if credential.model_allowlist != entry["model_allowlist"]:
            errors.append(f"provider {label} model allowlist does not match the profile")
        if credential.provider_config != entry["provider_config"]:
            errors.append(f"provider {label} configuration does not match the profile")
    return errors


def assert_reference_profile_ready(tenant, profile_id: str = REFERENCE_PROFILE_ID) -> None:
    errors = profile_readiness_errors(tenant, profile_id)
    if errors:
        raise ValueError("; ".join(errors))
