import hashlib
import hmac
import io
import json
import time
import uuid

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import Client, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate
from utils.tenant_middleware import clear_current_tenant, set_current_tenant

from apps.billing.models import SubscriptionPlan, TenantSubscription
from apps.courses.maic_models import MAICClassroom
from apps.tenants.models import Tenant
from apps.users.models import User

from .models import (
    AIClassroomMediaAsset,
    AIQuotaReservation,
    OpenMAICJob,
    TenantAIProviderCredential,
    TenantAIRuntimeConfig,
)
from .reference_profiles import (
    REFERENCE_PROFILE_ID,
    REFERENCE_PROFILE_SHA256,
    load_reference_profile,
    reference_profile_sha256,
)
from .services import (
    SESSION_PREFIX,
    confirm_media_upload,
    load_classroom_artifact,
    persist_classroom_artifact,
    provider_runtime_payload,
    reserve_generation_quota,
    transition_reservation,
)
from .serializers import ProviderCredentialSerializer
from .views import launch_openmaic, provider_credentials


TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "openmaic-integration-tests",
    }
}
TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@pytest.fixture(autouse=True)
def reset_tenant_context():
    clear_current_tenant()
    yield
    clear_current_tenant()


def make_tenant(label: str, plan: str = "PRO") -> Tenant:
    return Tenant.objects.create(
        name=f"{label} School",
        slug=f"{label}-{uuid.uuid4().hex[:8]}",
        subdomain=f"{label}-{uuid.uuid4().hex[:8]}",
        email=f"admin-{uuid.uuid4().hex[:8]}@example.com",
        plan=plan,
        feature_maic=True,
    )


def make_user(tenant: Tenant, role: str = "TEACHER") -> User:
    token = uuid.uuid4().hex[:8]
    return User.objects.create_user(
        email=f"{role.lower()}-{token}@example.com",
        password="test-password-only",
        first_name="Test",
        last_name="User",
        role=role,
        tenant=tenant,
    )


def make_classroom(tenant: Tenant, user: User) -> MAICClassroom:
    return MAICClassroom.all_objects.create(
        tenant=tenant,
        creator=user,
        title="Tenant-scoped classroom",
        topic="Photosynthesis",
    )


def apply_reference_profile(tenant: Tenant, monkeypatch) -> None:
    monkeypatch.setenv("LP_OPENMAIC_OPENAI_API_KEY", "openai-managed-secret")
    monkeypatch.setenv("LP_OPENMAIC_VOLCENGINE_API_KEY", "volcengine-managed-secret")
    monkeypatch.setenv("LP_OPENMAIC_TAVILY_API_KEY", "tavily-managed-secret")
    call_command(
        "apply_openmaic_reference_profile",
        tenant=tenant.slug,
        confirm=True,
        stdout=io.StringIO(),
    )


def service_headers(
    path: str,
    encoded_body: bytes,
    nonce: str | None = None,
    method: str = "POST",
) -> dict:
    timestamp = str(int(time.time()))
    nonce = nonce or uuid.uuid4().hex
    digest = hashlib.sha256(encoded_body).hexdigest()
    canonical = f"{timestamp}\n{nonce}\n{method}\n{path}\n{digest}".encode()
    signature = hmac.new(b"integration-secret", canonical, hashlib.sha256).hexdigest()
    return {
        "HTTP_X_LP_SERVICE_TIMESTAMP": timestamp,
        "HTTP_X_LP_SERVICE_NONCE": nonce,
        "HTTP_X_LP_SERVICE_SIGNATURE": signature,
    }


@pytest.mark.django_db
@override_settings(
    CACHES=TEST_CACHES,
    OPENMAIC_PUBLIC_URL="https://classroom.learnpuddle.test",
)
def test_launch_code_is_single_use_and_bound_to_tenant_user_and_role():
    cache.clear()
    tenant = make_tenant("launch")
    user = make_user(tenant)
    TenantAIRuntimeConfig.all_objects.create(
        tenant=tenant,
        runtime=TenantAIRuntimeConfig.RUNTIME_OPENMAIC,
    )
    request = APIRequestFactory().post(
        "/api/v1/ai-classroom/launch/",
        {"action": "create", "return_path": "/teacher/ai-classroom"},
        format="json",
        HTTP_HOST=f"{tenant.subdomain}.learnpuddle.test",
    )
    request.tenant = tenant
    force_authenticate(request, user=user)
    set_current_tenant(tenant)

    response = launch_openmaic(request)

    assert response.status_code == 201
    code = response.data["launch_url"].split("code=", 1)[1]
    from .services import exchange_launch_code

    session = exchange_launch_code(code)
    assert session["tenant_id"] == str(tenant.id)
    assert session["user_id"] == str(user.id)
    assert session["role"] == "TEACHER"
    assert exchange_launch_code(code) is None


@pytest.mark.django_db
def test_provider_runtime_never_crosses_tenants_and_public_shape_masks_keys():
    first = make_tenant("provider-a")
    second = make_tenant("provider-b")
    TenantAIRuntimeConfig.all_objects.create(tenant=first)
    TenantAIRuntimeConfig.all_objects.create(tenant=second)
    first_credential = TenantAIProviderCredential.all_objects.create(
        tenant=first,
        modality="llm",
        provider_id="openai",
        model_allowlist=["gpt-5-mini"],
        is_default=True,
    )
    first_credential.set_api_key("school-a-secret")
    first_credential.save(update_fields=["api_key_encrypted"])
    second_credential = TenantAIProviderCredential.all_objects.create(
        tenant=second,
        modality="llm",
        provider_id="openai",
        model_allowlist=["gpt-5-mini"],
        is_default=True,
    )
    second_credential.set_api_key("school-b-secret")
    second_credential.save(update_fields=["api_key_encrypted"])

    first_payload = provider_runtime_payload(first)
    second_payload = provider_runtime_payload(second)

    assert first_payload["providers"][0]["api_key"] == "school-a-secret"
    assert second_payload["providers"][0]["api_key"] == "school-b-secret"
    assert first_credential.api_key_preview == "...cret"
    assert first_credential.api_key_encrypted != "school-a-secret"


@pytest.mark.django_db
def test_school_admin_provider_settings_are_read_only_and_never_expose_secret_metadata():
    tenant = make_tenant("managed-provider-status")
    admin = make_user(tenant, role="SCHOOL_ADMIN")
    TenantAIRuntimeConfig.all_objects.create(tenant=tenant)
    credential = TenantAIProviderCredential.all_objects.create(
        tenant=tenant,
        modality="llm",
        provider_id="openai",
        display_name="LearnPuddle managed language model",
        model_allowlist=["openai:gpt-4o-mini"],
        is_default=True,
        verification_status="verified",
    )
    credential.set_api_key("platform-managed-secret")
    credential.save(update_fields=["api_key_encrypted"])
    set_current_tenant(tenant)

    get_request = APIRequestFactory().get("/api/v1/tenants/settings/ai/providers/")
    get_request.tenant = tenant
    force_authenticate(get_request, user=admin)
    get_response = provider_credentials(get_request)

    assert get_response.status_code == 200
    assert get_response.data[0]["provider_id"] == "openai"
    assert "api_key" not in get_response.data[0]
    assert "api_key_preview" not in get_response.data[0]
    assert "base_url" not in get_response.data[0]
    assert "provider_config" not in get_response.data[0]

    post_request = APIRequestFactory().post(
        "/api/v1/tenants/settings/ai/providers/",
        {"provider_id": "anthropic"},
        format="json",
    )
    post_request.tenant = tenant
    force_authenticate(post_request, user=admin)

    assert provider_credentials(post_request).status_code == 405


@pytest.mark.django_db
def test_managed_provider_command_reads_key_from_environment(monkeypatch):
    tenant = make_tenant("managed-provider-command")
    monkeypatch.setenv("LP_TEST_PROVIDER_KEY", "platform-provisioned-secret")

    call_command(
        "provision_openmaic_provider",
        tenant=tenant.slug,
        modality="llm",
        provider="openai",
        models="openai/gpt-4o-mini",
        api_key_env="LP_TEST_PROVIDER_KEY",
        confirm=True,
        stdout=io.StringIO(),
    )

    credential = TenantAIProviderCredential.all_objects.get(
        tenant=tenant,
        modality="llm",
        provider_id="openai",
    )
    assert credential.get_api_key() == "platform-provisioned-secret"
    assert credential.model_allowlist == ["openai:gpt-4o-mini"]
    assert credential.is_default is True
    assert credential.verification_status == "unverified"


@pytest.mark.django_db
def test_reference_profile_command_applies_exact_openmaic_defaults(monkeypatch):
    tenant = make_tenant("reference-profile")

    apply_reference_profile(tenant, monkeypatch)

    profile = load_reference_profile()
    config = TenantAIRuntimeConfig.all_objects.get(tenant=tenant)
    assert config.reference_profile_id == REFERENCE_PROFILE_ID
    assert reference_profile_sha256(profile) == REFERENCE_PROFILE_SHA256
    assert config.reference_profile_sha256 == REFERENCE_PROFILE_SHA256
    assert config.provider_config_version == 2
    assert profile["settings"]["image"] == {
        "enabled": True,
        "provider_id": "seedream",
        "model_id": "doubao-seedream-5-0-260128",
        "default_aspect_ratio": "16:9",
        "size_policy": "scene_aspect_ratio_scaled_to_seedream_minimum",
    }
    assert profile["settings"]["video"] == {
        "enabled": True,
        "provider_id": "seedance",
        "model_id": "doubao-seedance-2-0-260128",
        "default_aspect_ratio": "16:9",
        "default_duration_seconds": 5,
        "default_resolution": "480p",
    }
    credentials = TenantAIProviderCredential.all_objects.filter(tenant=tenant)
    assert credentials.count() == 6
    assert not credentials.exclude(base_url="").exists()
    llm = credentials.get(modality="llm", provider_id="openai")
    assert llm.get_api_key() == "openai-managed-secret"
    assert llm.model_allowlist == ["gpt-5.5"]
    assert llm.provider_config == {"default_model": "gpt-5.5"}
    assert credentials.get(modality="tts").provider_config == {
        "model": "gpt-4o-mini-tts",
        "voice": "alloy",
        "speed": 1.0,
    }


@pytest.mark.django_db
def test_openmaic_runtime_fails_closed_when_certified_provider_drifts(monkeypatch):
    tenant = make_tenant("reference-profile-drift")
    apply_reference_profile(tenant, monkeypatch)
    call_command(
        "set_openmaic_runtime",
        tenant=tenant.slug,
        runtime="openmaic_fork",
        confirm=True,
        stdout=io.StringIO(),
    )
    TenantAIProviderCredential.all_objects.filter(
        tenant=tenant,
        modality="image",
        provider_id="seedream",
    ).update(base_url="https://unexpected.example.com")

    with pytest.raises(ValueError, match="base URL does not match"):
        provider_runtime_payload(tenant)


@pytest.mark.django_db
def test_generic_provider_edit_invalidates_reference_profile(monkeypatch):
    tenant = make_tenant("reference-profile-invalidated")
    apply_reference_profile(tenant, monkeypatch)

    call_command(
        "provision_openmaic_provider",
        tenant=tenant.slug,
        modality="llm",
        provider="openai",
        display_name="Rotated outside certified workflow",
        confirm=True,
        stdout=io.StringIO(),
    )

    config = TenantAIRuntimeConfig.all_objects.get(tenant=tenant)
    assert config.reference_profile_id == ""
    assert config.reference_profile_sha256 == ""


@pytest.mark.django_db
def test_reference_profile_command_is_atomic_when_a_secret_is_missing(monkeypatch):
    tenant = make_tenant("reference-profile-missing")
    monkeypatch.setenv("LP_OPENMAIC_OPENAI_API_KEY", "openai-managed-secret")
    monkeypatch.setenv("LP_OPENMAIC_VOLCENGINE_API_KEY", "volcengine-managed-secret")

    with pytest.raises(CommandError, match="LP_OPENMAIC_TAVILY_API_KEY"):
        call_command(
            "apply_openmaic_reference_profile",
            tenant=tenant.slug,
            confirm=True,
            stdout=io.StringIO(),
        )

    config = TenantAIRuntimeConfig.all_objects.get(tenant=tenant)
    assert config.reference_profile_id == ""
    assert not TenantAIProviderCredential.all_objects.filter(tenant=tenant).exists()


@pytest.mark.django_db
def test_runtime_switch_rejects_tenant_without_certified_profile():
    tenant = make_tenant("runtime-profile-gate")

    with pytest.raises(CommandError, match="reference profile is not ready"):
        call_command(
            "set_openmaic_runtime",
            tenant=tenant.slug,
            runtime="openmaic_fork",
            confirm=True,
            stdout=io.StringIO(),
        )

    config = TenantAIRuntimeConfig.all_objects.get(tenant=tenant)
    assert config.runtime == "legacy"


@pytest.mark.django_db
@override_settings(CACHES=TEST_CACHES, OPENMAIC_SERVICE_SECRET="integration-secret")
def test_service_signature_nonce_cannot_be_replayed():
    cache.clear()
    path = "/api/internal/openmaic/sessions/exchange/"
    body = json.dumps({"code": "x" * 40}, separators=(",", ":")).encode()
    nonce = uuid.uuid4().hex
    headers = service_headers(path, body, nonce)
    client = Client()

    first = client.post(path, data=body, content_type="application/json", secure=True, **headers)
    second = client.post(path, data=body, content_type="application/json", secure=True, **headers)

    assert first.status_code == 401
    assert second.status_code == 409
    assert second.json()["error"] == "Replayed service request"


@pytest.mark.django_db
def test_quota_reservation_is_idempotent_and_consumed_once():
    tenant = make_tenant("quota")
    user = make_user(tenant)
    classroom = make_classroom(tenant, user)
    TenantAIRuntimeConfig.all_objects.create(tenant=tenant)
    job = OpenMAICJob.all_objects.create(
        tenant=tenant,
        created_by=user,
        classroom=classroom,
        upstream_job_id="upstream-1",
        idempotency_key="quota-idempotency-1",
    )

    first = reserve_generation_quota(tenant=tenant, user=user, job=job, classroom=classroom)
    second = reserve_generation_quota(tenant=tenant, user=user, job=job, classroom=classroom)
    transitioned = transition_reservation(job, "consumed")

    assert first.id == second.id
    assert transitioned.status == "consumed"
    assert AIQuotaReservation.all_objects.filter(job=job).count() == 1
    assert transition_reservation(job, "consumed").id == first.id


@pytest.mark.django_db
@override_settings(CACHES=TEST_CACHES, OPENMAIC_SERVICE_SECRET="integration-secret")
def test_generation_creation_is_atomic_and_http_retry_is_idempotent():
    cache.clear()
    tenant = make_tenant("atomic-generation")
    user = make_user(tenant)
    TenantAIRuntimeConfig.all_objects.create(tenant=tenant)
    session_token = "g" * 64
    cache.set(
        f"{SESSION_PREFIX}{session_token}",
        {
            "tenant_id": str(tenant.id),
            "user_id": str(user.id),
            "role": user.role,
            "action": "create",
            "classroom_id": None,
            "return_url": "https://school.example/",
            "session_token": session_token,
        },
        timeout=300,
    )
    path = "/api/internal/openmaic/generations/"
    payload = {
        "session_token": session_token,
        "upstream_job_id": "upstream-first",
        "idempotency_key": "browser-request-1",
        "title": "Atomic classroom",
        "topic": "Atomicity",
    }
    first_body = json.dumps(payload, separators=(",", ":")).encode()
    first = Client().post(
        path,
        data=first_body,
        content_type="application/json",
        secure=True,
        **service_headers(path, first_body),
    )
    payload["upstream_job_id"] = "upstream-retry"
    retry_body = json.dumps(payload, separators=(",", ":")).encode()
    retry = Client().post(
        path,
        data=retry_body,
        content_type="application/json",
        secure=True,
        **service_headers(path, retry_body),
    )

    assert first.status_code == 201
    assert retry.status_code == 200
    assert retry.json()["job_id"] == first.json()["job_id"]
    assert retry.json()["classroom_id"] == first.json()["classroom_id"]
    assert MAICClassroom.all_objects.filter(tenant=tenant).count() == 1
    assert AIQuotaReservation.all_objects.filter(tenant=tenant).count() == 1

    classroom = MAICClassroom.all_objects.get(id=first.json()["classroom_id"])
    persist_classroom_artifact(
        tenant=tenant,
        classroom=classroom,
        artifact={"id": str(classroom.id), "stage": {}, "scenes": []},
        runtime_version="153195ca-lp.test",
        schema_version="openmaic-1",
    )
    classroom.refresh_from_db()
    assert classroom.status == "GENERATING"

    job_path = f"/api/internal/openmaic/jobs/{first.json()['job_id']}/"
    success_body = json.dumps({"status": "succeeded"}, separators=(",", ":")).encode()
    success = Client().patch(
        job_path,
        data=success_body,
        content_type="application/json",
        secure=True,
        **service_headers(job_path, success_body, method="PATCH"),
    )
    classroom.refresh_from_db()
    reservation = AIQuotaReservation.all_objects.get(tenant=tenant)
    assert success.status_code == 200
    assert classroom.status == "READY"
    assert reservation.status == "consumed"


@pytest.mark.django_db
@override_settings(STORAGES=TEST_STORAGES)
def test_artifact_and_media_keys_are_tenant_prefixed_and_checksummed(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    tenant = make_tenant("storage")
    user = make_user(tenant)
    classroom = make_classroom(tenant, user)
    artifact = {"id": "upstream-classroom", "scenes": [{"id": "scene-1"}]}

    row = persist_classroom_artifact(
        tenant=tenant,
        classroom=classroom,
        artifact=artifact,
        runtime_version="153195ca-lp.1",
        schema_version="openmaic-1",
    )
    _stored_row, loaded = load_classroom_artifact(tenant=tenant, classroom=classroom)

    assert row.object_key == f"maic/{tenant.id}/classrooms/{classroom.id}/manifest.json"
    assert loaded == artifact

    content = b"real-media-bytes"
    digest = hashlib.sha256(content).hexdigest()
    object_key = f"maic/{tenant.id}/classrooms/{classroom.id}/image/{digest}.png"
    default_storage.save(object_key, ContentFile(content))
    asset = AIClassroomMediaAsset.all_objects.create(
        tenant=tenant,
        classroom=classroom,
        created_by=user,
        kind="image",
        sha256=digest,
        extension="png",
        content_type="image/png",
        object_key=object_key,
        size_bytes=len(content),
    )
    confirm_media_upload(tenant=tenant, asset=asset)

    assert asset.is_confirmed is True
    assert asset.object_key.startswith(f"maic/{tenant.id}/classrooms/{classroom.id}/")


@pytest.mark.django_db
@override_settings(
    CACHES=TEST_CACHES,
    STORAGES=TEST_STORAGES,
    OPENMAIC_SERVICE_SECRET="integration-secret",
)
def test_same_tenant_peer_cannot_guess_private_artifact_id(tmp_path, settings):
    cache.clear()
    settings.MEDIA_ROOT = tmp_path
    tenant = make_tenant("private-artifact")
    owner = make_user(tenant)
    peer = make_user(tenant)
    classroom = make_classroom(tenant, owner)
    persist_classroom_artifact(
        tenant=tenant,
        classroom=classroom,
        artifact={"id": str(classroom.id), "scenes": []},
        runtime_version="153195ca-lp.1",
        schema_version="openmaic-1",
    )
    session_token = "p" * 64
    cache.set(
        f"{SESSION_PREFIX}{session_token}",
        {
            "tenant_id": str(tenant.id),
            "user_id": str(peer.id),
            "role": peer.role,
            "action": "classroom",
            "classroom_id": str(classroom.id),
            "return_url": "https://school.example/",
            "session_token": session_token,
        },
        timeout=300,
    )
    path = f"/api/internal/openmaic/classrooms/{classroom.id}/artifact/"
    body = json.dumps(
        {"session_token": session_token, "operation": "read"},
        separators=(",", ":"),
    ).encode()

    response = Client().post(
        path,
        data=body,
        content_type="application/json",
        secure=True,
        **service_headers(path, body),
    )

    assert response.status_code == 404


@pytest.mark.django_db
@override_settings(CACHES=TEST_CACHES, OPENMAIC_SERVICE_SECRET="integration-secret")
def test_usage_event_ingestion_rejects_duplicate_billing_rows():
    cache.clear()
    tenant = make_tenant("usage")
    user = make_user(tenant)
    session_token = "s" * 64
    cache.set(
        f"{SESSION_PREFIX}{session_token}",
        {
            "tenant_id": str(tenant.id),
            "user_id": str(user.id),
            "role": user.role,
            "action": "library",
            "classroom_id": None,
            "return_url": "https://school.example/",
            "session_token": session_token,
        },
        timeout=300,
    )
    path = "/api/internal/openmaic/usage/events/"
    payload = {
        "session_token": session_token,
        "events": [
            {
                "idempotency_key": "provider-request-1",
                "modality": "llm",
                "provider_id": "openai",
                "model_id": "gpt-5-mini",
                "input_tokens": 100,
                "output_tokens": 25,
            }
        ],
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    client = Client()

    first = client.post(
        path,
        data=body,
        content_type="application/json",
        secure=True,
        **service_headers(path, body),
    )
    second = client.post(
        path,
        data=body,
        content_type="application/json",
        secure=True,
        **service_headers(path, body),
    )

    assert first.status_code == 200
    assert first.json() == {"created": 1, "duplicates": 0}
    assert second.status_code == 200
    assert second.json() == {"created": 0, "duplicates": 1}


@pytest.mark.django_db
def test_runtime_switch_requires_confirmation_and_supports_rollback(monkeypatch):
    tenant = make_tenant("runtime-switch")
    apply_reference_profile(tenant, monkeypatch)

    with pytest.raises(CommandError, match="No changes applied"):
        call_command(
            "set_openmaic_runtime",
            tenant=tenant.slug,
            runtime="openmaic_fork",
            stdout=io.StringIO(),
        )
    config = TenantAIRuntimeConfig.all_objects.get(tenant=tenant)
    assert config.runtime == "legacy"

    call_command(
        "set_openmaic_runtime",
        tenant=tenant.slug,
        runtime="openmaic_fork",
        student_generation="enabled",
        confirm=True,
        stdout=io.StringIO(),
    )
    config.refresh_from_db()
    assert config.runtime == "openmaic_fork"
    assert config.student_generation_enabled is True

    call_command(
        "set_openmaic_runtime",
        tenant=str(tenant.id),
        runtime="legacy",
        student_generation="disabled",
        confirm=True,
        stdout=io.StringIO(),
    )
    config.refresh_from_db()
    assert config.runtime == "legacy"
    assert config.student_generation_enabled is False


@pytest.mark.django_db
def test_llm_provider_requires_an_explicit_model_allowlist():
    tenant = make_tenant("provider-models")
    serializer = ProviderCredentialSerializer(
        data={
            "modality": "llm",
            "provider_id": "openai",
            "api_key": "provider-secret",
            "model_allowlist": [],
            "is_default": True,
        },
        context={"tenant": tenant},
    )

    assert serializer.is_valid() is False
    assert "model_allowlist" in serializer.errors

    normalized = ProviderCredentialSerializer(
        data={
            "modality": "llm",
            "provider_id": "openai",
            "api_key": "provider-secret",
            "model_allowlist": ["openai/gpt-4o-mini"],
            "is_default": True,
        },
        context={"tenant": tenant},
    )
    assert normalized.is_valid(), normalized.errors
    assert normalized.validated_data["model_allowlist"] == ["openai:gpt-4o-mini"]


@pytest.mark.django_db
def test_provider_config_rejects_embedded_secrets():
    tenant = make_tenant("provider-config-secret")
    serializer = ProviderCredentialSerializer(
        data={
            "modality": "tts",
            "provider_id": "openai",
            "api_key": "encrypted-through-dedicated-field",
            "provider_config": {
                "voice": "alloy",
                "nested": {"access_token": "must-not-live-in-json"},
            },
        },
        context={"tenant": tenant},
    )

    assert serializer.is_valid() is False
    assert "provider_config" in serializer.errors


@pytest.mark.django_db
@override_settings(CACHES=TEST_CACHES, OPENMAIC_SERVICE_SECRET="integration-secret")
def test_generation_rejects_unentitled_video_before_creating_rows():
    cache.clear()
    tenant = make_tenant("no-video", plan="STARTER")
    user = make_user(tenant)
    TenantAIRuntimeConfig.all_objects.create(tenant=tenant)
    session_token = "v" * 64
    cache.set(
        f"{SESSION_PREFIX}{session_token}",
        {
            "tenant_id": str(tenant.id),
            "user_id": str(user.id),
            "role": user.role,
            "action": "create",
            "classroom_id": None,
            "return_url": "https://school.example/",
            "session_token": session_token,
        },
        timeout=300,
    )
    path = "/api/internal/openmaic/generations/"
    payload = {
        "session_token": session_token,
        "upstream_job_id": "video-job",
        "idempotency_key": "video-request",
        "title": "Unentitled video",
        "config": {"enableVideoGeneration": True},
    }
    body = json.dumps(payload, separators=(",", ":")).encode()

    response = Client().post(
        path,
        data=body,
        content_type="application/json",
        secure=True,
        **service_headers(path, body),
    )

    assert response.status_code == 403
    assert MAICClassroom.all_objects.filter(tenant=tenant).count() == 0
    assert OpenMAICJob.all_objects.filter(tenant=tenant).count() == 0


@pytest.mark.django_db
@override_settings(
    CACHES=TEST_CACHES,
    OPENMAIC_PUBLIC_URL="https://classroom.learnpuddle.test",
)
def test_canceled_subscription_cannot_inherit_stale_paid_ai_entitlements():
    tenant = make_tenant("canceled", plan="PRO")
    user = make_user(tenant)
    paid_plan, _created = SubscriptionPlan.objects.get_or_create(
        plan_code="PRO",
        defaults={
            "name": "Professional",
            "ai_entitlements": {
                "max_concurrent_generations": 3,
                "storage_bytes": 1024,
            },
        },
    )
    TenantSubscription.objects.create(
        tenant=tenant,
        plan=paid_plan,
        status="canceled",
        stripe_customer_id=f"cus_{uuid.uuid4().hex}",
    )
    TenantAIRuntimeConfig.all_objects.create(
        tenant=tenant,
        runtime=TenantAIRuntimeConfig.RUNTIME_OPENMAIC,
    )
    request = APIRequestFactory().post(
        "/api/v1/ai-classroom/launch/",
        {"action": "library"},
        format="json",
        HTTP_HOST=f"{tenant.subdomain}.learnpuddle.test",
    )
    request.tenant = tenant
    force_authenticate(request, user=user)
    set_current_tenant(tenant)

    response = launch_openmaic(request)

    assert response.status_code == 403
    assert response.data["error"] == "AI Classroom is not included in this subscription"
