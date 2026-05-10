"""HTTP API for media generation (Phase 9, MAIC-914).

POST /api/maic/v2/media/generate-image/   {prompt, width?, height?, quality?, seed?, scene_id?}
POST /api/maic/v2/media/generate-video/   {prompt, duration_seconds?, aspect_ratio?, seed?, scene_id?}

Both endpoints follow the same posture:
  - Tenant gate via [IsAuthenticated, MaicV2TenantPermission]
  - Validate request body against the Pydantic request type
  - Resolve TenantAIConfig from the authenticated user's tenant
  - Dispatch to the async orchestrator (asyncio.run from sync DRF view)
  - Return 201 with the result model dumped
  - Surface typed exceptions as appropriate HTTP statuses:
      MaicConfigError      → 400 (request is well-formed but the
                                  tenant config doesn't allow it OR
                                  provider rejected as permanent)
      MaicProviderError    → 502 (upstream provider failed after the
                                  orchestrator's bounded retries)
      ValidationError      → 400 (body shape doesn't match the type)
      Other Exception      → 500 with logger.exception

Phase 4 generation pipeline integration is MAIC-915 (next ticket).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import ValidationError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.maic.exceptions import MaicConfigError, MaicProviderError
from apps.maic.media import adapters  # noqa: F401 — side-effect: register every adapter
from apps.maic.media.orchestrator import generate_image, generate_video
from apps.maic.media.types import (
    ImageGenerationRequest,
    VideoGenerationRequest,
)
from apps.maic.permissions import MaicV2TenantPermission


logger = logging.getLogger("apps.maic.media.views")


def _resolve_tenant_config(user) -> Any:
    """Pull TenantAIConfig off the authenticated user's tenant.

    Returns the config or raises ``MaicConfigError`` if missing —
    upstream guard (MaicV2TenantPermission) has already confirmed the
    tenant has the v2 flag on; reaching here without ai_config is a
    genuine misconfiguration, not a permission issue.
    """
    tenant = getattr(user, "tenant", None)
    if tenant is None:
        raise MaicConfigError(
            "media generation requires a tenant-scoped user; this user has no tenant"
        )
    cfg = getattr(tenant, "ai_config", None)
    if cfg is None:
        raise MaicConfigError(
            f"tenant {tenant.id!r} has no TenantAIConfig — admin must create one "
            f"before media generation can be used"
        )
    return cfg


class GenerateImageView(APIView):
    """POST /api/maic/v2/media/generate-image/

    Request body (JSON):
        prompt: str (required, 1-4000 chars)
        width:  int (optional, 64-4096, default 1024)
        height: int (optional, 64-4096, default 1024)
        quality: "standard" | "high" (optional, default "standard")
        seed:   int (optional, non-negative)
        scene_id: str (optional, embedded in storage key for grep-ability)

    Response 201 (Created):
        {
          media_id: str,
          url: str,
          provider: str,
          model: str,
          latency_ms: int,
          cost_usd_estimate: float | null,
        }

    Response 400 — request body invalid OR tenant config rejects request
    Response 401 — not authenticated
    Response 403 — tenant doesn't have MAIC v2 feature flag on
    Response 502 — provider failed after the orchestrator's bounded retries
    """

    permission_classes = [IsAuthenticated, MaicV2TenantPermission]

    def post(self, request: Request) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        user = request.user

        try:
            tenant_cfg = _resolve_tenant_config(user)
        except MaicConfigError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Tenant id flows into the request so the storage path is
        # tenant-scoped (matches the Phase 9 storage helper contract).
        body.setdefault("tenant_id", str(tenant_cfg.tenant_id))

        try:
            req = ImageGenerationRequest.model_validate(body)
        except ValidationError as exc:
            return Response(
                {"error": "invalid request body", "details": exc.errors()},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = asyncio.run(generate_image(req, tenant_cfg))
        except MaicConfigError as exc:
            logger.warning(
                "media.generate-image config error for tenant=%s: %s",
                tenant_cfg.tenant_id, exc,
            )
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except MaicProviderError as exc:
            logger.warning(
                "media.generate-image provider failure for tenant=%s: %s",
                tenant_cfg.tenant_id, exc,
            )
            return Response(
                {"error": "image provider failed after retries", "detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception as exc:  # noqa: BLE001 — last-resort boundary
            logger.exception(
                "media.generate-image unexpected error for tenant=%s",
                tenant_cfg.tenant_id,
            )
            return Response(
                {"error": "unexpected error during image generation"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(result.model_dump(), status=status.HTTP_201_CREATED)


class GenerateVideoView(APIView):
    """POST /api/maic/v2/media/generate-video/

    Request body (JSON):
        prompt: str (required, 1-4000 chars)
        duration_seconds: int (optional, 1-60, default 5)
        aspect_ratio: "16:9" | "9:16" | "1:1" (optional, default "16:9")
        seed: int (optional, non-negative)
        scene_id: str (optional)

    Response 201:
        {
          media_id: str,
          url: str,
          provider: str,
          model: str,
          duration_seconds: int,
          latency_ms: int,
          cost_usd_estimate: float | null,
        }

    Error matrix: same as image endpoint.
    """

    permission_classes = [IsAuthenticated, MaicV2TenantPermission]

    def post(self, request: Request) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        user = request.user

        try:
            tenant_cfg = _resolve_tenant_config(user)
        except MaicConfigError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        body.setdefault("tenant_id", str(tenant_cfg.tenant_id))

        try:
            req = VideoGenerationRequest.model_validate(body)
        except ValidationError as exc:
            return Response(
                {"error": "invalid request body", "details": exc.errors()},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = asyncio.run(generate_video(req, tenant_cfg))
        except MaicConfigError as exc:
            logger.warning(
                "media.generate-video config error for tenant=%s: %s",
                tenant_cfg.tenant_id, exc,
            )
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except MaicProviderError as exc:
            logger.warning(
                "media.generate-video provider failure for tenant=%s: %s",
                tenant_cfg.tenant_id, exc,
            )
            return Response(
                {"error": "video provider failed after retries", "detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "media.generate-video unexpected error for tenant=%s",
                tenant_cfg.tenant_id,
            )
            return Response(
                {"error": "unexpected error during video generation"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(result.model_dump(), status=status.HTTP_201_CREATED)
