from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.courses.maic_models import MAICClassroom
from utils.audit import log_audit
from utils.decorators import admin_only, tenant_required

from .models import (
    AIClassroomArtifact,
    AIClassroomMediaAsset,
    AIQuotaReservation,
    AIUsageEvent,
    OpenMAICJob,
    TenantAIProviderCredential,
)
from .security import require_openmaic_service
from .serializers import ProviderCredentialSerializer
from .services import (
    AIQuotaError,
    bind_session_classroom,
    bump_provider_config_version,
    create_launch_code,
    confirm_media_upload,
    exchange_launch_code,
    load_classroom_artifact,
    persist_classroom_artifact,
    provider_runtime_payload,
    reserve_media_upload,
    reserve_generation_quota,
    resolve_ai_entitlements,
    resolve_session,
    runtime_config_for,
    signed_media_url,
    transition_reservation,
)


def _can_launch_classroom(user, classroom) -> bool:
    # Reuse the current canonical visibility gate during the rollback window.
    from apps.courses.maic_views import _can_view_classroom

    return _can_view_classroom(user, classroom)


def _can_mutate_classroom(user, classroom) -> bool:
    return user.role in {"SUPER_ADMIN", "SCHOOL_ADMIN"} or classroom.creator_id == user.id


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@tenant_required
def launch_openmaic(request):
    tenant = request.tenant
    runtime = runtime_config_for(tenant)
    if runtime.runtime != runtime.RUNTIME_OPENMAIC:
        return Response({"error": "OpenMAIC runtime is not enabled for this school"}, status=409)
    if not tenant.is_active or not (tenant.feature_maic or tenant.feature_maic_v2):
        return Response({"error": "AI Classroom is not enabled"}, status=403)

    entitlements = resolve_ai_entitlements(tenant)
    if not any(
        int(entitlements.get(key) or 0) > 0
        for key in ("max_concurrent_generations", "storage_bytes")
    ):
        return Response({"error": "AI Classroom is not included in this subscription"}, status=403)

    allowed_roles = {"SUPER_ADMIN", "SCHOOL_ADMIN", "TEACHER", "HOD", "IB_COORDINATOR", "STUDENT"}
    if request.user.role not in allowed_roles:
        return Response({"error": "Role is not allowed to use AI Classroom"}, status=403)

    action = request.data.get("action", "library")
    if action not in {"library", "create", "classroom"}:
        return Response({"error": "Unsupported launch action"}, status=400)
    if action == "create" and request.user.role == "STUDENT":
        if not entitlements.get("student_generation_enabled"):
            return Response({"error": "Student classroom generation is disabled"}, status=403)

    classroom_id = request.data.get("classroom_id")
    if action == "classroom":
        classroom = MAICClassroom.all_objects.filter(id=classroom_id).first()
        if not classroom or not _can_launch_classroom(request.user, classroom):
            return Response({"error": "Classroom not found"}, status=404)
        classroom_id = str(classroom.id)
    else:
        classroom_id = None

    try:
        _code, launch_url = create_launch_code(
            request=request,
            action=action,
            classroom_id=classroom_id,
        )
    except (RuntimeError, ValueError) as exc:
        return Response({"error": str(exc)}, status=503 if isinstance(exc, RuntimeError) else 400)

    log_audit(
        "AI_CLASSROOM_LAUNCH",
        "OpenMAICSession",
        target_id=classroom_id or "",
        target_repr=action,
        request=request,
    )
    return Response({"launch_url": launch_url, "expires_in": 60}, status=201)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def provider_credentials(request):
    runtime_config_for(request.tenant)
    if request.method == "GET":
        queryset = TenantAIProviderCredential.objects.filter(tenant=request.tenant)
        return Response(ProviderCredentialSerializer(queryset, many=True).data)

    serializer = ProviderCredentialSerializer(
        data=request.data,
        context={"tenant": request.tenant},
    )
    serializer.is_valid(raise_exception=True)
    try:
        credential = serializer.save()
        bump_provider_config_version(request.tenant)
    except IntegrityError:
        return Response(
            {"error": "This provider already exists or the modality already has a default"},
            status=409,
        )
    log_audit(
        "CREATE",
        "TenantAIProviderCredential",
        target_id=credential.id,
        target_repr=f"{credential.modality}:{credential.provider_id}",
        request=request,
    )
    return Response(ProviderCredentialSerializer(credential).data, status=201)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def provider_credential_detail(request, credential_id):
    credential = get_object_or_404(
        TenantAIProviderCredential.objects,
        id=credential_id,
        tenant=request.tenant,
    )
    if request.method == "DELETE":
        target_repr = f"{credential.modality}:{credential.provider_id}"
        credential.delete()
        bump_provider_config_version(request.tenant)
        log_audit(
            "DELETE",
            "TenantAIProviderCredential",
            target_id=credential_id,
            target_repr=target_repr,
            request=request,
        )
        return Response(status=204)

    serializer = ProviderCredentialSerializer(
        credential,
        data=request.data,
        partial=True,
        context={"tenant": request.tenant},
    )
    serializer.is_valid(raise_exception=True)
    try:
        credential = serializer.save()
        bump_provider_config_version(request.tenant)
    except IntegrityError:
        return Response({"error": "The modality already has a default provider"}, status=409)
    log_audit(
        "UPDATE",
        "TenantAIProviderCredential",
        target_id=credential.id,
        target_repr=f"{credential.modality}:{credential.provider_id}",
        request=request,
    )
    return Response(ProviderCredentialSerializer(credential).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def usage_summary(request):
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    events = AIUsageEvent.objects.filter(tenant=request.tenant, occurred_at__gte=month_start)
    aggregate = events.aggregate(
        input_tokens=Sum("input_tokens"),
        output_tokens=Sum("output_tokens"),
        quantity=Sum("quantity"),
    )
    consumed = (
        AIQuotaReservation.objects.filter(
            tenant=request.tenant,
            status="consumed",
            created_at__gte=month_start,
        ).aggregate(total=Sum("units"))["total"]
        or 0
    )
    return Response(
        {
            "period": month_start.date().isoformat(),
            "events": events.count(),
            "input_tokens": aggregate["input_tokens"] or 0,
            "output_tokens": aggregate["output_tokens"] or 0,
            "quantity": aggregate["quantity"] or 0,
            "successful_generations": consumed,
            "entitlements": resolve_ai_entitlements(request.tenant),
            "costs_are_provider_estimates": True,
        }
    )


def _resolved_session_or_response(request):
    resolved = resolve_session(request.data.get("session_token", ""))
    if not resolved:
        return None, Response({"error": "Invalid or expired OpenMAIC session"}, status=401)
    return resolved, None


@api_view(["POST"])
@permission_classes([AllowAny])
@require_openmaic_service
def internal_exchange_session(request):
    session = exchange_launch_code(request.data.get("code", ""))
    if not session:
        return Response({"error": "Invalid, expired or already-used launch code"}, status=401)
    return Response(session)


@api_view(["POST"])
@permission_classes([AllowAny])
@require_openmaic_service
def internal_introspect_session(request):
    resolved, error = _resolved_session_or_response(request)
    if error:
        return error
    session, tenant, user = resolved
    runtime = runtime_config_for(tenant)
    return Response(
        {
            "tenant_id": str(tenant.id),
            "user_id": str(user.id),
            "role": user.role,
            "action": session.get("action"),
            "classroom_id": session.get("classroom_id"),
            "return_url": session.get("return_url"),
            "branding": {
                "name": tenant.name,
                "primary_color": tenant.primary_color,
                "secondary_color": tenant.secondary_color,
                "logo_url": tenant.logo.url if tenant.logo else None,
            },
            "provider_config_version": runtime.provider_config_version,
            "student_generation_enabled": runtime.student_generation_enabled,
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@require_openmaic_service
def internal_runtime_context(request):
    resolved, error = _resolved_session_or_response(request)
    if error:
        return error
    session, tenant, user = resolved
    return Response(
        {
            "tenant_id": str(tenant.id),
            "user_id": str(user.id),
            "role": user.role,
            "action": session.get("action"),
            "classroom_id": session.get("classroom_id"),
            "return_url": session.get("return_url"),
            "entitlements": resolve_ai_entitlements(tenant),
            "provider_config": provider_runtime_payload(tenant),
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@require_openmaic_service
def internal_create_classroom(request):
    resolved, error = _resolved_session_or_response(request)
    if error:
        return error
    _session, tenant, user = resolved
    if user.role == "STUDENT" and not resolve_ai_entitlements(tenant).get(
        "student_generation_enabled"
    ):
        return Response({"error": "Student classroom generation is disabled"}, status=403)

    entitlements = resolve_ai_entitlements(tenant)
    config = request.data.get("config")
    config = config if isinstance(config, dict) else {}
    enabled_high_cost = set(entitlements.get("high_cost_modalities") or [])
    if config.get("enableImageGeneration") and "image" not in enabled_high_cost:
        return Response({"error": "Image generation is not included in this plan"}, status=403)
    if config.get("enableVideoGeneration") and "video" not in enabled_high_cost:
        return Response({"error": "Video generation is not included in this plan"}, status=403)
    per_teacher_limit = int(entitlements.get("max_classrooms_per_teacher") or 0)
    existing_count = (
        MAICClassroom.all_objects.filter(tenant=tenant, creator=user)
        .exclude(status="ARCHIVED")
        .count()
    )
    if per_teacher_limit and existing_count >= per_teacher_limit:
        return Response({"error": "Classroom limit reached"}, status=429)

    title = str(request.data.get("title") or request.data.get("topic") or "AI Classroom")[:300]
    classroom = MAICClassroom.all_objects.create(
        tenant=tenant,
        creator=user,
        title=title,
        description=str(request.data.get("description", ""))[:5000],
        topic=str(request.data.get("topic", title))[:500],
        language=str(request.data.get("language", "en"))[:10],
        status="GENERATING",
        config=config,
        is_public=False,
    )
    bind_session_classroom(request.data.get("session_token", ""), classroom)
    log_audit(
        "CREATE",
        "MAICClassroom",
        target_id=classroom.id,
        target_repr=classroom.title,
        actor=user,
        tenant=tenant,
    )
    return Response({"classroom_id": str(classroom.id), "status": classroom.status}, status=201)


@api_view(["POST"])
@permission_classes([AllowAny])
@require_openmaic_service
def internal_list_classrooms(request):
    resolved, error = _resolved_session_or_response(request)
    if error:
        return error
    _session, tenant, user = resolved
    classrooms = MAICClassroom.all_objects.filter(tenant=tenant).exclude(status="ARCHIVED")
    rows = []
    for classroom in classrooms.order_by("-updated_at"):
        if not _can_launch_classroom(user, classroom):
            continue
        artifact = AIClassroomArtifact.all_objects.filter(classroom=classroom).first()
        rows.append(
            {
                "id": str(classroom.id),
                "name": classroom.title,
                "description": classroom.description,
                "status": classroom.status,
                "scene_count": len((classroom.config or {}).get("scene_ids", [])),
                "created_at": classroom.created_at.isoformat(),
                "updated_at": classroom.updated_at.isoformat(),
                "is_public": classroom.is_public,
                "creator_id": str(classroom.creator_id),
                "has_artifact": bool(artifact),
            }
        )
    return Response({"classrooms": rows})


@api_view(["PATCH", "DELETE"])
@permission_classes([AllowAny])
@require_openmaic_service
def internal_classroom_metadata(request, classroom_id):
    resolved, error = _resolved_session_or_response(request)
    if error:
        return error
    _session, tenant, user = resolved
    classroom = get_object_or_404(MAICClassroom.all_objects, id=classroom_id, tenant=tenant)
    if not _can_mutate_classroom(user, classroom):
        return Response({"error": "Classroom not found"}, status=404)
    if request.method == "DELETE":
        classroom.status = "ARCHIVED"
        classroom.save(update_fields=["status", "updated_at"])
        return Response(status=204)
    if "title" in request.data:
        title = str(request.data.get("title", "")).strip()[:300]
        if not title:
            return Response({"error": "title cannot be blank"}, status=400)
        classroom.title = title
    if "is_public" in request.data:
        classroom.is_public = bool(request.data["is_public"])
    classroom.save(update_fields=["title", "is_public", "updated_at"])
    return Response(
        {
            "id": str(classroom.id),
            "title": classroom.title,
            "is_public": classroom.is_public,
            "status": classroom.status,
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@require_openmaic_service
def internal_create_job(request):
    resolved, error = _resolved_session_or_response(request)
    if error:
        return error
    _session, tenant, user = resolved
    upstream_job_id = str(request.data.get("upstream_job_id", ""))[:80]
    idempotency_key = str(request.data.get("idempotency_key", ""))[:120]
    if not upstream_job_id or not idempotency_key:
        return Response({"error": "upstream_job_id and idempotency_key are required"}, status=400)

    classroom = None
    classroom_id = request.data.get("classroom_id")
    if classroom_id:
        classroom = MAICClassroom.all_objects.filter(id=classroom_id, tenant=tenant).first()
        if not classroom:
            return Response({"error": "Classroom not found"}, status=404)
    try:
        with transaction.atomic():
            job, created = OpenMAICJob.all_objects.get_or_create(
                tenant=tenant,
                idempotency_key=idempotency_key,
                defaults={
                    "created_by": user,
                    "classroom": classroom,
                    "upstream_job_id": upstream_job_id,
                },
            )
            if created:
                runtime_config_for(tenant)
                reserve_generation_quota(tenant=tenant, user=user, job=job, classroom=classroom)
            elif job.upstream_job_id != upstream_job_id or job.classroom_id != (
                classroom.id if classroom else None
            ):
                return Response(
                    {"error": "Idempotency key is already bound to another generation"},
                    status=409,
                )
    except AIQuotaError as exc:
        return Response({"error": str(exc)}, status=429)
    except IntegrityError:
        return Response({"error": "Job id is already in use"}, status=409)
    return Response(
        {"job_id": str(job.id), "upstream_job_id": job.upstream_job_id, "status": job.status},
        status=201 if created else 200,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@require_openmaic_service
def internal_create_generation(request):
    resolved, error = _resolved_session_or_response(request)
    if error:
        return error
    _session, tenant, user = resolved
    if user.role == "STUDENT" and not resolve_ai_entitlements(tenant).get(
        "student_generation_enabled"
    ):
        return Response({"error": "Student classroom generation is disabled"}, status=403)
    upstream_job_id = str(request.data.get("upstream_job_id", ""))[:80]
    idempotency_key = str(request.data.get("idempotency_key", ""))[:120]
    if not upstream_job_id or not idempotency_key:
        return Response({"error": "upstream_job_id and idempotency_key are required"}, status=400)

    existing = (
        OpenMAICJob.all_objects.select_related("classroom")
        .filter(
            tenant=tenant,
            idempotency_key=idempotency_key,
        )
        .first()
    )
    if existing:
        if existing.created_by_id != user.id:
            return Response({"error": "Idempotency key is already in use"}, status=409)
        return Response(
            {
                "classroom_id": str(existing.classroom_id),
                "job_id": str(existing.id),
                "upstream_job_id": existing.upstream_job_id,
                "status": existing.status,
            }
        )

    entitlements = resolve_ai_entitlements(tenant)
    config = request.data.get("config")
    config = config if isinstance(config, dict) else {}
    enabled_high_cost = set(entitlements.get("high_cost_modalities") or [])
    if config.get("enableImageGeneration") and "image" not in enabled_high_cost:
        return Response({"error": "Image generation is not included in this plan"}, status=403)
    if config.get("enableVideoGeneration") and "video" not in enabled_high_cost:
        return Response({"error": "Video generation is not included in this plan"}, status=403)
    per_teacher_limit = int(entitlements.get("max_classrooms_per_teacher") or 0)
    existing_count = (
        MAICClassroom.all_objects.filter(tenant=tenant, creator=user)
        .exclude(status="ARCHIVED")
        .count()
    )
    if per_teacher_limit and existing_count >= per_teacher_limit:
        return Response({"error": "Classroom limit reached"}, status=429)

    title = str(request.data.get("title") or request.data.get("topic") or "AI Classroom")[:300]
    try:
        with transaction.atomic():
            classroom = MAICClassroom.all_objects.create(
                tenant=tenant,
                creator=user,
                title=title,
                description=str(request.data.get("description", ""))[:5000],
                topic=str(request.data.get("topic", title))[:500],
                language=str(request.data.get("language", "en"))[:10],
                status="GENERATING",
                config=config,
                is_public=False,
            )
            job = OpenMAICJob.all_objects.create(
                tenant=tenant,
                created_by=user,
                classroom=classroom,
                upstream_job_id=upstream_job_id,
                idempotency_key=idempotency_key,
            )
            runtime_config_for(tenant)
            reserve_generation_quota(tenant=tenant, user=user, job=job, classroom=classroom)
            bind_session_classroom(request.data.get("session_token", ""), classroom)
    except AIQuotaError as exc:
        return Response({"error": str(exc)}, status=429)
    except IntegrityError:
        return Response({"error": "Generation idempotency conflict"}, status=409)
    log_audit(
        "CREATE",
        "MAICClassroom",
        target_id=classroom.id,
        target_repr=classroom.title,
        actor=user,
        tenant=tenant,
    )
    return Response(
        {
            "classroom_id": str(classroom.id),
            "job_id": str(job.id),
            "upstream_job_id": job.upstream_job_id,
            "status": job.status,
        },
        status=201,
    )


@api_view(["GET", "PATCH"])
@permission_classes([AllowAny])
@require_openmaic_service
def internal_update_job(request, job_id):
    job = get_object_or_404(OpenMAICJob.all_objects, id=job_id)
    session_token = request.data.get("session_token") if request.method == "PATCH" else None
    if session_token:
        resolved = resolve_session(session_token)
        if not resolved or resolved[1].id != job.tenant_id:
            return Response({"error": "Invalid or expired OpenMAIC session"}, status=401)
    if request.method == "GET":
        return Response(
            {
                "job_id": str(job.id),
                "upstream_job_id": job.upstream_job_id,
                "classroom_id": str(job.classroom_id) if job.classroom_id else None,
                "status": job.status,
                "progress": job.progress,
                "error": job.error,
                "completed_at": job.completed_at,
            }
        )
    with transaction.atomic():
        job = OpenMAICJob.all_objects.select_for_update().get(id=job_id)
        new_status = request.data.get("status", job.status)
        allowed = {value for value, _label in OpenMAICJob.STATUS_CHOICES}
        if new_status not in allowed:
            return Response({"error": "Invalid job status"}, status=400)
        if job.status in {"succeeded", "failed", "cancelled"} and new_status != job.status:
            return Response({"error": "Completed jobs are immutable"}, status=409)

        job.status = new_status
        if "progress" in request.data:
            job.progress = request.data["progress"]
        if "error" in request.data:
            job.error = str(request.data["error"])[:10000]
        if new_status in {"succeeded", "failed", "cancelled"}:
            job.completed_at = timezone.now()
        job.save()
        if new_status == "succeeded":
            transition_reservation(job, "consumed")
            if job.classroom_id:
                MAICClassroom.all_objects.filter(id=job.classroom_id).update(
                    status="READY",
                    error_message="",
                    updated_at=timezone.now(),
                )
        elif new_status in {"failed", "cancelled"}:
            transition_reservation(job, "released")
            if job.classroom_id:
                MAICClassroom.all_objects.filter(id=job.classroom_id).update(
                    status="FAILED" if new_status == "failed" else "DRAFT",
                    error_message=job.error,
                    updated_at=timezone.now(),
                )
    return Response({"job_id": str(job.id), "status": job.status})


@api_view(["POST"])
@permission_classes([AllowAny])
@require_openmaic_service
def internal_job_runtime_context(request, job_id):
    job = get_object_or_404(OpenMAICJob.all_objects, id=job_id)
    tenant = job.tenant
    user = job.created_by
    if not tenant.is_active or not user or not user.is_active or user.is_deleted:
        return Response({"error": "Job principal is no longer active"}, status=403)
    return Response(
        {
            "tenant_id": str(tenant.id),
            "user_id": str(user.id),
            "role": user.role,
            "classroom_id": str(job.classroom_id) if job.classroom_id else None,
            "entitlements": resolve_ai_entitlements(tenant),
            "provider_config": provider_runtime_payload(tenant),
        }
    )


@api_view(["PUT", "POST"])
@permission_classes([AllowAny])
@require_openmaic_service
def internal_classroom_artifact(request, classroom_id):
    job_id = request.data.get("job_id")
    if job_id:
        job = get_object_or_404(OpenMAICJob.all_objects, id=job_id, classroom_id=classroom_id)
        if job.status in {"succeeded", "failed", "cancelled"}:
            return Response({"error": "Generation job is no longer writable"}, status=409)
        tenant = job.tenant
    else:
        resolved, error = _resolved_session_or_response(request)
        if error:
            return error
        _session, tenant, user = resolved
    classroom = get_object_or_404(MAICClassroom.all_objects, id=classroom_id, tenant=tenant)

    if request.method == "POST" and request.data.get("operation") == "read":
        if not job_id and not _can_launch_classroom(user, classroom):
            return Response({"error": "Classroom artifact not found"}, status=404)
        try:
            artifact_row, artifact = load_classroom_artifact(tenant=tenant, classroom=classroom)
        except AIClassroomArtifact.DoesNotExist:
            return Response({"error": "Classroom artifact not found"}, status=404)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=409)
        return Response(
            {
                "artifact": artifact,
                "sha256": artifact_row.sha256,
                "schema_version": artifact_row.schema_version,
                "runtime_version": artifact_row.runtime_version,
            }
        )

    if not job_id and not _can_mutate_classroom(user, classroom):
        return Response({"error": "Classroom not found"}, status=404)
    artifact = request.data.get("artifact")
    if not isinstance(artifact, dict):
        return Response({"error": "artifact must be a JSON object"}, status=400)
    try:
        artifact_row = persist_classroom_artifact(
            tenant=tenant,
            classroom=classroom,
            artifact=artifact,
            runtime_version=str(request.data.get("runtime_version", ""))[:80],
            schema_version=str(request.data.get("schema_version", "openmaic-1"))[:40],
            upstream_classroom_id=str(request.data.get("upstream_classroom_id", ""))[:120],
        )
    except ValueError as exc:
        return Response({"error": str(exc)}, status=400)
    return Response({"sha256": artifact_row.sha256, "object_key": artifact_row.object_key})


def _internal_media_principal(request, classroom_id):
    job_id = request.data.get("job_id")
    if job_id:
        job = OpenMAICJob.all_objects.filter(id=job_id, classroom_id=classroom_id).first()
        if not job:
            return None
        return job.tenant, job.created_by
    resolved = resolve_session(request.data.get("session_token", ""))
    if not resolved:
        return None
    _session, tenant, user = resolved
    classroom = MAICClassroom.all_objects.filter(id=classroom_id, tenant=tenant).first()
    if not classroom or not _can_launch_classroom(user, classroom):
        return None
    return tenant, user


@api_view(["POST"])
@permission_classes([AllowAny])
@require_openmaic_service
def internal_media_presign(request, classroom_id):
    principal = _internal_media_principal(request, classroom_id)
    if not principal:
        return Response({"error": "Classroom media principal not found"}, status=404)
    tenant, user = principal
    classroom = get_object_or_404(MAICClassroom.all_objects, id=classroom_id, tenant=tenant)
    try:
        asset, upload_url, headers = reserve_media_upload(
            tenant=tenant,
            user=user,
            classroom=classroom,
            kind=str(request.data.get("kind", "")),
            sha256=str(request.data.get("sha256", "")),
            content_type=str(request.data.get("content_type", "")),
            size_bytes=int(request.data.get("size_bytes") or 0),
        )
    except AIQuotaError as exc:
        return Response({"error": str(exc)}, status=429)
    except (TypeError, ValueError) as exc:
        return Response({"error": str(exc)}, status=400)
    except RuntimeError as exc:
        return Response({"error": str(exc)}, status=503)
    return Response(
        {
            "asset_id": str(asset.id),
            "upload_required": not asset.is_confirmed,
            "upload_url": upload_url,
            "headers": headers,
            "stable_url": f"/api/learnpuddle/media/{asset.id}",
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@require_openmaic_service
def internal_media_confirm(request, classroom_id, asset_id):
    principal = _internal_media_principal(request, classroom_id)
    if not principal:
        return Response({"error": "Classroom media principal not found"}, status=404)
    tenant, _user = principal
    asset = get_object_or_404(
        AIClassroomMediaAsset.all_objects,
        id=asset_id,
        classroom_id=classroom_id,
        tenant=tenant,
    )
    try:
        confirm_media_upload(tenant=tenant, asset=asset)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=409)
    return Response(
        {
            "asset_id": str(asset.id),
            "stable_url": f"/api/learnpuddle/media/{asset.id}",
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@require_openmaic_service
def internal_media_read(request, asset_id):
    asset = AIClassroomMediaAsset.all_objects.filter(id=asset_id, is_confirmed=True).first()
    if not asset:
        return Response({"error": "Media asset not found"}, status=404)
    principal = _internal_media_principal(request, asset.classroom_id)
    if not principal or principal[0].id != asset.tenant_id:
        return Response({"error": "Media asset not found"}, status=404)
    try:
        url = signed_media_url(asset)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=409)
    return Response({"url": url, "content_type": asset.content_type})


@api_view(["POST"])
@permission_classes([AllowAny])
@require_openmaic_service
def internal_usage_events(request):
    bridge_job = None
    bridge_job_id = request.data.get("job_id")
    if bridge_job_id:
        bridge_job = get_object_or_404(OpenMAICJob.all_objects, id=bridge_job_id)
        tenant = bridge_job.tenant
        user = bridge_job.created_by
    else:
        resolved, error = _resolved_session_or_response(request)
        if error:
            return error
        _session, tenant, user = resolved
    events = request.data.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 500:
        return Response({"error": "events must contain between 1 and 500 rows"}, status=400)

    created = 0
    duplicates = 0
    for row in events:
        if not isinstance(row, dict):
            return Response({"error": "Every usage event must be an object"}, status=400)
        idempotency_key = str(row.get("idempotency_key", ""))[:160]
        modality = row.get("modality")
        provider_id = str(row.get("provider_id", ""))[:80]
        if (
            not idempotency_key
            or modality not in dict(AIUsageEvent.MODALITY_CHOICES)
            or not provider_id
        ):
            return Response({"error": "Invalid usage event identity"}, status=400)
        job = bridge_job
        if row.get("job_id") and not bridge_job:
            job = OpenMAICJob.all_objects.filter(id=row["job_id"], tenant=tenant).first()
            if not job:
                return Response({"error": "Usage event job not found"}, status=404)
        classroom = job.classroom if job else None
        try:
            quantity = Decimal(str(row.get("quantity") or 0))
        except (InvalidOperation, ValueError):
            return Response({"error": "Usage quantity must be numeric"}, status=400)
        if quantity < 0:
            return Response({"error": "Usage quantity cannot be negative"}, status=400)
        try:
            token_values = {
                field: max(0, int(row.get(field) or 0))
                for field in (
                    "input_tokens",
                    "output_tokens",
                    "cache_read_tokens",
                    "cache_creation_tokens",
                    "reasoning_tokens",
                )
            }
        except (TypeError, ValueError):
            return Response({"error": "Usage token counts must be integers"}, status=400)
        try:
            _event, was_created = AIUsageEvent.all_objects.get_or_create(
                tenant=tenant,
                idempotency_key=idempotency_key,
                defaults={
                    "user": user,
                    "classroom": classroom,
                    "job": job,
                    "modality": modality,
                    "provider_id": provider_id,
                    "model_id": str(row.get("model_id", ""))[:160],
                    **token_values,
                    "quantity": quantity,
                    "unit": str(row.get("unit", "token"))[:24],
                    "source": str(row.get("source", ""))[:80],
                    "metadata": (
                        row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
                    ),
                },
            )
        except IntegrityError:
            was_created = False
        if was_created:
            created += 1
        else:
            duplicates += 1
    return Response({"created": created, "duplicates": duplicates})
