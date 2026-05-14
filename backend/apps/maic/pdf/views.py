"""HTTP API for MAIC v2 PDF parsing.

POST /api/maic/v2/pdf/parse/ accepts either:
  - multipart ``file`` / ``pdf`` containing a PDF, or
  - JSON/form ``file_url`` / ``url`` pointing at an external PDF.

The endpoint intentionally stays synchronous for this first HTTP surface,
matching the current adapter contract. Larger PDFs should move to the
generation-job style async/polling flow called out in Phase 11.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

from django.core.files.storage import default_storage
from pydantic import ValidationError
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integrations_chat.ssrf_guard import SSRFError, validate_external_url
from apps.maic.exceptions import MaicConfigError, MaicProviderError
from apps.maic.pdf.orchestrator import parse_pdf
from apps.maic.pdf.types import PDFParseRequest
from apps.maic.permissions import MaicV2TenantPermission
from utils.s3_utils import sign_url


logger = logging.getLogger("apps.maic.pdf.views")

_MAX_PDF_UPLOAD_SIZE_MB = 50
_MAX_PDF_UPLOAD_SIZE_BYTES = _MAX_PDF_UPLOAD_SIZE_MB * 1024 * 1024
_ALLOWED_PDF_MIMES = {"", "application/pdf", "application/x-pdf"}


def _resolve_tenant_config(user) -> Any:
    tenant = getattr(user, "tenant", None)
    if tenant is None:
        raise MaicConfigError(
            "PDF parsing requires a tenant-scoped user; this user has no tenant"
        )
    cfg = getattr(tenant, "ai_config", None)
    if cfg is None:
        raise MaicConfigError(
            f"tenant {tenant.id!r} has no TenantAIConfig; admin must create one "
            f"before PDF parsing can be used"
        )
    return cfg


def _body_dict(request: Request) -> dict[str, Any]:
    if not hasattr(request.data, "keys"):
        return {}
    return {key: request.data.get(key) for key in request.data.keys()}


def _uploaded_pdf(request: Request):
    return request.FILES.get("file") or request.FILES.get("pdf")


def _external_url(body: dict[str, Any]) -> str:
    raw = body.get("file_url") or body.get("url") or ""
    return str(raw).strip()


def _validate_uploaded_pdf(file_obj) -> str | None:
    name = getattr(file_obj, "name", "") or ""
    ext = Path(name).suffix.lower()
    if ext != ".pdf":
        return "Only .pdf uploads are accepted."

    mime = (getattr(file_obj, "content_type", "") or "").lower()
    if mime not in _ALLOWED_PDF_MIMES:
        return f"MIME type '{mime}' is not allowed for PDF parsing."

    size = getattr(file_obj, "size", 0) or 0
    if size > _MAX_PDF_UPLOAD_SIZE_BYTES:
        return (
            f"PDF too large ({size / (1024 * 1024):.1f} MB). "
            f"Maximum: {_MAX_PDF_UPLOAD_SIZE_MB} MB."
        )

    try:
        pos = file_obj.tell()
    except (AttributeError, OSError):
        pos = None
    try:
        file_obj.seek(0)
        header = file_obj.read(5)
    finally:
        try:
            file_obj.seek(pos or 0)
        except (AttributeError, OSError):
            pass

    if header != b"%PDF-":
        return "Uploaded file does not look like a PDF."
    return None


def _pdf_upload_path(tenant_id: str) -> str:
    return f"course_content/tenant/{tenant_id}/ai_studio/pdf/{uuid.uuid4().hex}.pdf"


def _absolute_storage_url(request: Request, storage_key: str) -> str:
    signed = sign_url(storage_key, expires_in=3600)
    if signed.startswith(("http://", "https://")):
        return signed

    url = default_storage.url(storage_key)
    signed = sign_url(url, expires_in=3600)
    if signed.startswith(("http://", "https://")):
        return signed
    return request.build_absolute_uri(url)


class ParsePDFView(APIView):
    """POST /api/maic/v2/pdf/parse/."""

    permission_classes = [IsAuthenticated, MaicV2TenantPermission]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def post(self, request: Request) -> Response:
        body = _body_dict(request)
        uploaded = _uploaded_pdf(request)
        url = _external_url(body)

        if bool(uploaded) == bool(url):
            return Response(
                {"error": "Provide exactly one of file or file_url."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            tenant_cfg = _resolve_tenant_config(request.user)
        except MaicConfigError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        tenant_id = str(tenant_cfg.tenant_id)

        if uploaded:
            validation_error = _validate_uploaded_pdf(uploaded)
            if validation_error:
                return Response(
                    {"error": validation_error},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            storage_key = default_storage.save(_pdf_upload_path(tenant_id), uploaded)
            file_url = _absolute_storage_url(request, storage_key)
        else:
            try:
                validate_external_url(url)
            except SSRFError as exc:
                return Response(
                    {"error": f"file_url failed SSRF validation: {exc}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            file_url = url

        payload = {
            "file_url": file_url,
            "tenant_id": tenant_id,
            "scene_id": body.get("scene_id") or None,
            "page_limit": body.get("page_limit") or None,
            "extract_figures": body.get("extract_figures", True),
        }

        try:
            req = PDFParseRequest.model_validate(payload)
        except ValidationError as exc:
            return Response(
                {"error": "invalid request body", "details": exc.errors()},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = asyncio.run(parse_pdf(req, tenant_cfg))
        except MaicConfigError as exc:
            logger.warning(
                "pdf.parse config error for tenant=%s: %s",
                tenant_cfg.tenant_id,
                exc,
            )
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except MaicProviderError as exc:
            logger.warning(
                "pdf.parse provider failure for tenant=%s: %s",
                tenant_cfg.tenant_id,
                exc,
            )
            return Response(
                {"error": "PDF provider failed", "detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:  # noqa: BLE001 - last-resort HTTP boundary
            logger.exception(
                "pdf.parse unexpected error for tenant=%s",
                tenant_cfg.tenant_id,
            )
            return Response(
                {"error": "unexpected error during PDF parsing"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(result.model_dump(mode="json"), status=status.HTTP_201_CREATED)
