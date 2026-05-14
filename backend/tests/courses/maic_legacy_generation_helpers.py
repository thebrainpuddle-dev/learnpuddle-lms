from __future__ import annotations

from typing import Literal

from rest_framework.test import APIRequestFactory, force_authenticate

from apps.courses import maic_views
from utils.tenant_middleware import clear_current_tenant, set_current_tenant


def call_legacy_scene_content_view(
    *,
    audience: Literal["teacher", "student"],
    user,
    tenant,
    payload: dict,
):
    """Drive the legacy v1 scene-content view without remounting URLconf.

    Production keeps the legacy route unmounted while MAIC v2 generation is the
    default. A few rollback-contract tests still need to exercise the old view
    code directly, especially the deferred image-fill boundary.
    """
    path = f"/api/v1/{audience}/maic/generate/scene-content/"
    request = APIRequestFactory().post(
        path,
        payload,
        format="json",
        HTTP_HOST=f"{tenant.subdomain}.lms.com",
    )
    force_authenticate(request, user=user)
    set_current_tenant(tenant)
    try:
        view = (
            maic_views.teacher_maic_generate_scene_content
            if audience == "teacher"
            else maic_views.student_maic_generate_scene_content
        )
        return view(request)
    finally:
        clear_current_tenant()
