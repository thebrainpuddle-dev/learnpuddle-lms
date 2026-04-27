"""
Admin API for SCIM token management (TASK-023).

Allows tenant SCHOOL_ADMIN users to create, list, and revoke SCIM tokens.
Mounted under /api/v1/admin/sso/scim-tokens/ via scim_admin_urls.py.

Authentication: standard JWT Bearer token (same as all other admin APIs).
Tenant resolution: via TenantMiddleware (Host header → tenant).

The raw token value is returned once on creation (POST 201) and is NEVER
stored or returned again — only its SHA-256 hash lives in the database.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.audit import log_audit
from utils.decorators import admin_only, tenant_required

from .scim_models import SCIMToken


# ---------------------------------------------------------------------------
# GET/POST /api/v1/admin/sso/scim-tokens/
# ---------------------------------------------------------------------------

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def scim_token_list_create(request):
    """
    GET  — List all (active and revoked) SCIM tokens for this tenant.
           The raw token value is never included in the listing.
    POST — Generate a new SCIM token.  The raw token is included in the
           201 response body and CANNOT be retrieved afterwards.
    """
    tenant = request.tenant

    # ------------------------------------------------------------------
    if request.method == "GET":
        tokens = SCIMToken.objects.filter(tenant=tenant).order_by("-created_at")
        results = [
            {
                "id": str(t.id),
                "name": t.name,
                "created_at": t.created_at.isoformat(),
                "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
                "is_active": t.is_active,
            }
            for t in tokens
        ]
        # Return standard paginated-style envelope so callers can use
        # "results" without special-casing the SCIM token list endpoint.
        return Response({"count": len(results), "results": results})

    # ------------------------------------------------------------------
    # POST — create a new token
    name = (request.data.get("name") or "").strip()
    if not name:
        return Response({"error": "name is required."}, status=400)

    raw_token, scim_token = SCIMToken.generate(
        tenant=tenant,
        name=name,
        created_by=request.user,
    )

    log_audit(
        action="SCIM_TOKEN_CREATE",
        target_type="SCIMToken",
        target_id=str(scim_token.id),
        target_repr=name,
        changes={"name": name},
        request=request,
    )

    return Response(
        {
            "id": str(scim_token.id),
            "name": scim_token.name,
            "token": raw_token,           # ← only returned here; cannot be recovered
            "created_at": scim_token.created_at.isoformat(),
            "is_active": scim_token.is_active,
        },
        status=201,
    )


# ---------------------------------------------------------------------------
# DELETE /api/v1/admin/sso/scim-tokens/{token_id}/
# ---------------------------------------------------------------------------

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def scim_token_detail(request, token_id):
    """
    Soft-revoke (deactivate) a SCIM token.

    Sets ``is_active=False``; the row is retained for audit purposes.
    Returns 204 No Content on success, 404 if not found or cross-tenant.
    """
    tenant = request.tenant

    try:
        scim_token = SCIMToken.objects.get(id=token_id, tenant=tenant)
    except SCIMToken.DoesNotExist:
        return Response({"error": "Not found."}, status=404)

    scim_token.is_active = False
    scim_token.save(update_fields=["is_active"])

    log_audit(
        action="SCIM_TOKEN_REVOKE",
        target_type="SCIMToken",
        target_id=str(scim_token.id),
        target_repr=scim_token.name,
        changes={"revoked": True},
        request=request,
    )

    return Response(status=204)
