from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.billing.models import SubscriptionPlan, TenantSubscription
from apps.courses.models import MAICClassroom
from apps.tenants.models import Tenant
from apps.users.models import User

from .models import (
    AIClassroomArtifact,
    AIClassroomMediaAsset,
    AIQuotaReservation,
    OpenMAICJob,
    TenantAIProviderCredential,
    TenantAIRuntimeConfig,
)


LAUNCH_PREFIX = "openmaic:launch:"
SESSION_PREFIX = "openmaic:session:"

MEDIA_CONTENT_TYPES = {
    "image/png": ("image", "png"),
    "image/jpeg": ("image", "jpg"),
    "image/webp": ("image", "webp"),
    "image/gif": ("image", "gif"),
    "video/mp4": ("video", "mp4"),
    "video/webm": ("video", "webm"),
    "audio/mpeg": ("audio", "mp3"),
    "audio/wav": ("audio", "wav"),
    "audio/ogg": ("audio", "ogg"),
    "audio/aac": ("audio", "aac"),
    "application/pdf": ("attachment", "pdf"),
    "text/plain": ("attachment", "txt"),
    "text/markdown": ("attachment", "md"),
}

DEFAULT_AI_ENTITLEMENTS = {
    "FREE": {
        "monthly_generations": 0,
        "max_concurrent_generations": 0,
        "storage_bytes": 0,
        "max_classrooms_per_teacher": 0,
        "student_generation_enabled": False,
        "high_cost_modalities": [],
    },
    "STARTER": {
        "monthly_generations": 25,
        "max_concurrent_generations": 1,
        "storage_bytes": 5 * 1024**3,
        "max_classrooms_per_teacher": 20,
        "student_generation_enabled": False,
        "high_cost_modalities": [],
    },
    "PRO": {
        "monthly_generations": 200,
        "max_concurrent_generations": 3,
        "storage_bytes": 50 * 1024**3,
        "max_classrooms_per_teacher": 100,
        "student_generation_enabled": False,
        "high_cost_modalities": ["image"],
    },
    "ENTERPRISE": {
        "monthly_generations": 0,
        "max_concurrent_generations": 10,
        "storage_bytes": 500 * 1024**3,
        "max_classrooms_per_teacher": 0,
        "student_generation_enabled": True,
        "high_cost_modalities": ["image", "video"],
    },
}


class AIQuotaError(ValueError):
    pass


def runtime_config_for(tenant: Tenant) -> TenantAIRuntimeConfig:
    config, _ = TenantAIRuntimeConfig.all_objects.get_or_create(tenant=tenant)
    return config


def bump_provider_config_version(tenant: Tenant) -> int:
    with transaction.atomic():
        config = TenantAIRuntimeConfig.all_objects.select_for_update().get(tenant=tenant)
        config.provider_config_version += 1
        config.save(update_fields=["provider_config_version", "updated_at"])
        return config.provider_config_version


def resolve_ai_entitlements(tenant: Tenant) -> dict:
    plan_code = tenant.plan
    plan = None
    subscription = TenantSubscription.objects.select_related("plan").filter(tenant=tenant).first()
    if subscription and subscription.status in {"active", "trialing"}:
        plan = subscription.plan
        plan_code = plan.plan_code
    elif subscription:
        plan_code = "FREE"
        plan = SubscriptionPlan.objects.filter(plan_code="FREE", is_active=True).first()
    else:
        plan = SubscriptionPlan.objects.filter(plan_code=plan_code, is_active=True).first()

    defaults = dict(DEFAULT_AI_ENTITLEMENTS.get(plan_code, DEFAULT_AI_ENTITLEMENTS["FREE"]))
    if plan and plan.ai_entitlements:
        defaults.update(plan.ai_entitlements)
    runtime = runtime_config_for(tenant)
    defaults["student_generation_enabled"] = bool(
        defaults.get("student_generation_enabled") and runtime.student_generation_enabled
    )
    return defaults


def create_launch_code(*, request, action: str, classroom_id: str | None) -> tuple[str, str]:
    return_path = request.data.get("return_path") or "/"
    if (
        not isinstance(return_path, str)
        or not return_path.startswith("/")
        or return_path.startswith("//")
    ):
        raise ValueError("return_path must be a local absolute path")

    origin = f"{request.scheme}://{request.get_host()}"
    code = secrets.token_urlsafe(32)
    payload = {
        "tenant_id": str(request.tenant.id),
        "user_id": str(request.user.id),
        "role": request.user.role,
        "action": action,
        "classroom_id": classroom_id,
        "return_url": f"{origin}{return_path}",
    }
    ttl = getattr(settings, "OPENMAIC_LAUNCH_CODE_TTL", 60)
    if not cache.add(f"{LAUNCH_PREFIX}{code}", payload, timeout=ttl):
        raise RuntimeError("Unable to allocate a launch code")
    public_url = getattr(settings, "OPENMAIC_PUBLIC_URL", "http://localhost:3001").rstrip("/")
    return code, f"{public_url}/auth/learnpuddle?code={code}"


def exchange_launch_code(code: str) -> dict | None:
    if not isinstance(code, str) or len(code) < 32 or len(code) > 128:
        return None
    lock_key = f"{LAUNCH_PREFIX}lock:{code}"
    if not cache.add(lock_key, "1", timeout=120):
        return None
    key = f"{LAUNCH_PREFIX}{code}"
    payload = cache.get(key)
    cache.delete(key)
    if not payload:
        return None

    session_token = secrets.token_urlsafe(48)
    session_ttl = getattr(settings, "OPENMAIC_SESSION_TTL", 8 * 60 * 60)
    session = {**payload, "session_token": session_token}
    cache.set(f"{SESSION_PREFIX}{session_token}", session, timeout=session_ttl)
    return {**session, "expires_in": session_ttl}


def resolve_session(session_token: str) -> tuple[dict, Tenant, User] | None:
    if not isinstance(session_token, str) or len(session_token) < 48:
        return None
    session = cache.get(f"{SESSION_PREFIX}{session_token}")
    if not session:
        return None
    tenant = Tenant.objects.filter(id=session.get("tenant_id"), is_active=True).first()
    user = User.all_objects.filter(
        id=session.get("user_id"),
        tenant_id=session.get("tenant_id"),
        is_active=True,
        is_deleted=False,
    ).first()
    if not tenant or not user or user.role != session.get("role"):
        cache.delete(f"{SESSION_PREFIX}{session_token}")
        return None
    return session, tenant, user


def bind_session_classroom(session_token: str, classroom: MAICClassroom) -> None:
    key = f"{SESSION_PREFIX}{session_token}"
    session = cache.get(key)
    if not session or str(classroom.tenant_id) != session.get("tenant_id"):
        raise ValueError("Invalid OpenMAIC session classroom binding")
    session["classroom_id"] = str(classroom.id)
    timeout = getattr(settings, "OPENMAIC_SESSION_TTL", 8 * 60 * 60)
    cache.set(key, session, timeout=timeout)


def provider_runtime_payload(tenant: Tenant) -> dict:
    config = runtime_config_for(tenant)
    providers = []
    queryset = TenantAIProviderCredential.all_objects.filter(tenant=tenant, is_enabled=True)
    for credential in queryset.order_by("modality", "provider_id"):
        providers.append(
            {
                "id": str(credential.id),
                "modality": credential.modality,
                "provider_id": credential.provider_id,
                "api_key": credential.get_api_key(),
                "base_url": credential.base_url or None,
                "models": credential.model_allowlist,
                "config": credential.provider_config,
                "is_default": credential.is_default,
            }
        )
    return {"version": config.provider_config_version, "providers": providers}


@transaction.atomic
def reserve_generation_quota(*, tenant, user, job, classroom=None) -> AIQuotaReservation:
    runtime_config_for(tenant)
    runtime = TenantAIRuntimeConfig.all_objects.select_for_update().get(tenant=tenant)
    del runtime  # row lock serializes quota decisions for this tenant
    existing = AIQuotaReservation.all_objects.filter(job=job).first()
    if existing:
        return existing

    entitlements = resolve_ai_entitlements(tenant)
    monthly_limit = int(entitlements.get("monthly_generations") or 0)
    concurrent_limit = int(entitlements.get("max_concurrent_generations") or 0)
    if concurrent_limit <= 0:
        raise AIQuotaError("AI Classroom generation is not included in this plan")

    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    used = (
        AIQuotaReservation.all_objects.filter(
            tenant=tenant,
            status="consumed",
            created_at__gte=month_start,
        ).aggregate(total=Sum("units"))["total"]
        or 0
    )
    reserved = (
        AIQuotaReservation.all_objects.filter(
            tenant=tenant,
            status="reserved",
            expires_at__gt=now,
        ).aggregate(total=Sum("units"))["total"]
        or 0
    )
    if monthly_limit and used + reserved >= monthly_limit:
        raise AIQuotaError("Monthly AI Classroom generation allowance exhausted")
    if reserved >= concurrent_limit:
        raise AIQuotaError("Concurrent AI Classroom generation limit reached")

    return AIQuotaReservation.all_objects.create(
        tenant=tenant,
        user=user,
        classroom=classroom,
        job=job,
        expires_at=now + timedelta(hours=2),
    )


def transition_reservation(job: OpenMAICJob, status_value: str) -> AIQuotaReservation:
    if status_value not in {"consumed", "released"}:
        raise ValueError("Unsupported reservation transition")
    with transaction.atomic():
        reservation = AIQuotaReservation.all_objects.select_for_update().get(job=job)
        if reservation.status == status_value:
            return reservation
        if reservation.status != "reserved":
            raise AIQuotaError(f"Reservation is already {reservation.status}")
        reservation.status = status_value
        reservation.save(update_fields=["status", "updated_at"])
        return reservation


def persist_classroom_artifact(
    *,
    tenant,
    classroom: MAICClassroom,
    artifact: dict,
    runtime_version: str,
    schema_version: str,
    upstream_classroom_id: str = "",
) -> AIClassroomArtifact:
    if classroom.tenant_id != tenant.id:
        raise ValueError("Classroom does not belong to tenant")
    encoded = json.dumps(artifact, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    max_bytes = getattr(settings, "OPENMAIC_MAX_ARTIFACT_BYTES", 64 * 1024 * 1024)
    if len(encoded) > max_bytes:
        raise ValueError("Classroom artifact exceeds configured size limit")
    checksum = hashlib.sha256(encoded).hexdigest()
    object_key = f"maic/{tenant.id}/classrooms/{classroom.id}/manifest.json"
    if default_storage.exists(object_key):
        default_storage.delete(object_key)
    default_storage.save(object_key, ContentFile(encoded))
    artifact_row, _ = AIClassroomArtifact.all_objects.update_or_create(
        classroom=classroom,
        defaults={
            "tenant": tenant,
            "object_key": object_key,
            "sha256": checksum,
            "size_bytes": len(encoded),
            "schema_version": schema_version,
            "runtime_version": runtime_version,
            "upstream_classroom_id": upstream_classroom_id,
        },
    )
    return artifact_row


def load_classroom_artifact(
    *, tenant, classroom: MAICClassroom
) -> tuple[AIClassroomArtifact, dict]:
    artifact_row = AIClassroomArtifact.all_objects.get(tenant=tenant, classroom=classroom)
    with default_storage.open(artifact_row.object_key, "rb") as artifact_file:
        encoded = artifact_file.read()
    if hashlib.sha256(encoded).hexdigest() != artifact_row.sha256:
        raise ValueError("Classroom artifact checksum mismatch")
    return artifact_row, json.loads(encoded.decode("utf-8"))


def _media_shape(kind: str, content_type: str) -> tuple[str, str]:
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    expected = MEDIA_CONTENT_TYPES.get(normalized_type)
    if not expected:
        raise ValueError("Unsupported AI Classroom media content type")
    expected_kind, extension = expected
    if kind == "poster" and expected_kind == "image":
        return normalized_type, extension
    if kind != expected_kind:
        raise ValueError("Media kind does not match its content type")
    return normalized_type, extension


def reserve_media_upload(
    *,
    tenant,
    user,
    classroom: MAICClassroom,
    kind: str,
    sha256: str,
    content_type: str,
    size_bytes: int,
) -> tuple[AIClassroomMediaAsset, str | None, dict[str, str]]:
    if classroom.tenant_id != tenant.id:
        raise ValueError("Classroom does not belong to tenant")
    digest = str(sha256).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("sha256 must be a lowercase hexadecimal digest")
    if size_bytes <= 0 or size_bytes > 250 * 1024 * 1024:
        raise ValueError("Media size is outside the allowed range")
    normalized_type, extension = _media_shape(kind, content_type)

    entitlements = resolve_ai_entitlements(tenant)
    storage_limit = int(entitlements.get("storage_bytes") or 0)
    used = (
        AIClassroomMediaAsset.all_objects.filter(
            tenant=tenant,
            is_confirmed=True,
        ).aggregate(
            total=Sum("size_bytes")
        )["total"]
        or 0
    )
    if storage_limit and used + size_bytes > storage_limit:
        raise AIQuotaError("AI Classroom storage allowance exhausted")

    object_key = f"maic/{tenant.id}/classrooms/{classroom.id}/{kind}/{digest}.{extension}"
    asset, _created = AIClassroomMediaAsset.all_objects.get_or_create(
        tenant=tenant,
        classroom=classroom,
        kind=kind,
        sha256=digest,
        defaults={
            "created_by": user,
            "extension": extension,
            "content_type": normalized_type,
            "object_key": object_key,
            "size_bytes": size_bytes,
        },
    )
    if asset.is_confirmed:
        return asset, None, {}
    if asset.content_type != normalized_type or asset.size_bytes != size_bytes:
        raise ValueError("Conflicting metadata for content-addressed media")

    if getattr(settings, "STORAGE_BACKEND", "local").lower() != "s3":
        raise RuntimeError("S3-compatible storage is required for OpenMAIC media uploads")
    storage = default_storage
    client = storage.connection.meta.client
    upload_url = client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": storage.bucket_name,
            "Key": asset.object_key,
            "ContentType": normalized_type,
        },
        ExpiresIn=getattr(settings, "OPENMAIC_MEDIA_UPLOAD_TTL", 900),
    )
    return asset, upload_url, {"content-type": normalized_type}


def confirm_media_upload(*, tenant, asset: AIClassroomMediaAsset) -> AIClassroomMediaAsset:
    if asset.tenant_id != tenant.id:
        raise ValueError("Media asset does not belong to tenant")
    if asset.is_confirmed:
        return asset
    if not default_storage.exists(asset.object_key):
        raise ValueError("Uploaded media object was not found")
    actual_size = default_storage.size(asset.object_key)
    if actual_size != asset.size_bytes:
        default_storage.delete(asset.object_key)
        raise ValueError("Uploaded media size does not match the reservation")
    digest = hashlib.sha256()
    with default_storage.open(asset.object_key, "rb") as media_file:
        for chunk in iter(lambda: media_file.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != asset.sha256:
        default_storage.delete(asset.object_key)
        raise ValueError("Uploaded media checksum does not match the reservation")
    asset.is_confirmed = True
    asset.confirmed_at = timezone.now()
    asset.save(update_fields=["is_confirmed", "confirmed_at", "updated_at"])
    return asset


def signed_media_url(asset: AIClassroomMediaAsset) -> str:
    if not asset.is_confirmed:
        raise ValueError("Media asset is not confirmed")
    if getattr(settings, "STORAGE_BACKEND", "local").lower() != "s3":
        return default_storage.url(asset.object_key)
    storage = default_storage
    return storage.connection.meta.client.generate_presigned_url(
        "get_object",
        Params={"Bucket": storage.bucket_name, "Key": asset.object_key},
        ExpiresIn=getattr(settings, "OPENMAIC_MEDIA_READ_TTL", 900),
    )
