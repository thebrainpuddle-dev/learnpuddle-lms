"""
Minimal xAPI (Experience API) 1.0.3 Learning Record Store endpoint.

Implements POST + GET only. POST validates the minimum required fields
(actor, verb, object) per xAPI spec, then stores the raw statement plus
extracted indices (``actor_mbox``, ``verb_id``, ``object_id``).

Tenant isolation: the tenant is resolved from the standard
``TenantMiddleware`` (subdomain or ``X-Tenant-Subdomain``) and cross-checked
against the authenticated user's tenant.

Actor impersonation defense (H1):
    Non-admin users cannot post statements on behalf of another user. Their
    ``actor.mbox`` is forcibly rewritten to ``mailto:{request.user.email}``
    before persistence. Admins (SCHOOL_ADMIN / SUPER_ADMIN) may send on
    behalf of any teacher in their own tenant; cross-tenant mbox values are
    rejected.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from utils.decorators import tenant_required

from .xapi_models import XAPIStatement

logger = logging.getLogger(__name__)

ADMIN_ROLES = {"SCHOOL_ADMIN", "SUPER_ADMIN"}

# GET pagination defaults (M-pagination). The caller may request fewer rows
# but cannot exceed LIST_MAX_LIMIT to avoid unbounded scans.
LIST_DEFAULT_LIMIT = 100
LIST_MAX_LIMIT = 500


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _extract_actor_mbox(actor: dict) -> str:
    """Return the best-effort ``mailto:`` form of an xAPI actor.

    Handles both the ``mbox`` and ``account`` shapes permitted by xAPI 1.0.3
    (section 4.1). ``mbox_sha1sum`` and ``openid`` are intentionally ignored
    for this MVP — we need a concrete email to compare against the authed
    user's identity.
    """
    mbox = actor.get("mbox")
    if isinstance(mbox, str) and mbox.lower().startswith("mailto:"):
        return mbox[:320]

    # Account shape: {"account": {"homePage": "...", "name": "..."}}
    account = actor.get("account")
    if isinstance(account, dict):
        name = account.get("name")
        if isinstance(name, str) and "@" in name:
            return f"mailto:{name.strip()}"[:320]

    return ""


def _validate_statement(body: Any) -> tuple[dict, str | None]:
    """Validate minimum xAPI 1.0.3 fields.

    Returns (parsed, error). On success ``parsed`` has the extracted fields
    ready for model insertion.
    """
    if not isinstance(body, dict):
        return {}, "Statement must be a JSON object"

    actor = body.get("actor")
    verb = body.get("verb")
    obj = body.get("object")
    if not isinstance(actor, dict):
        return {}, "actor is required and must be an object"
    if not isinstance(verb, dict):
        return {}, "verb is required and must be an object"
    if not isinstance(obj, dict):
        return {}, "object is required and must be an object"

    # Actor mbox: accept either mbox or account.name-with-@ shape.
    actor_mbox = _extract_actor_mbox(actor)
    actor_name = actor.get("name") if isinstance(actor.get("name"), str) else ""

    # Verb: id is mandatory (IRI). Whitespace-only verb ids are rejected.
    verb_id = verb.get("id")
    if not isinstance(verb_id, str) or not verb_id.strip():
        return {}, "verb.id is required and must be a non-empty IRI"
    verb_id = verb_id.strip()
    verb_display = ""
    display = verb.get("display")
    if isinstance(display, dict):
        # Pick first language value
        for v in display.values():
            if isinstance(v, str):
                verb_display = v[:255]
                break

    # Object: id required (IRI).
    object_id = obj.get("id")
    if not isinstance(object_id, str) or not object_id.strip():
        return {}, "object.id is required and must be a non-empty IRI"
    object_id = object_id.strip()
    object_name = ""
    definition = obj.get("definition")
    if isinstance(definition, dict):
        name = definition.get("name")
        if isinstance(name, dict):
            for v in name.values():
                if isinstance(v, str):
                    object_name = v[:500]
                    break

    # Statement id: optional; generate a UUIDv4 server-side if missing.
    stmt_id = body.get("id")
    if stmt_id in (None, ""):
        stmt_uuid = uuid.uuid4()
    else:
        try:
            stmt_uuid = uuid.UUID(str(stmt_id))
        except (ValueError, TypeError):
            return {}, "id must be a UUID if supplied"

    result = body.get("result") if isinstance(body.get("result"), dict) else {}
    context = body.get("context") if isinstance(body.get("context"), dict) else {}

    return {
        "statement_id": stmt_uuid,
        "actor_mbox": actor_mbox,
        "actor_name": actor_name[:255] if isinstance(actor_name, str) else "",
        "verb_id": verb_id[:500],
        "verb_display": verb_display,
        "object_id": object_id[:500],
        "object_name": object_name,
        "result": result,
        "context": context,
        "raw": body,
    }, None


def _enforce_actor_identity(
    request: Request, parsed: dict
) -> tuple[dict, Response | None]:
    """Rewrite / validate ``actor_mbox`` to defeat impersonation (H1).

    * Non-admins: ``actor_mbox`` is forcibly set to the authed user's email.
      The ``raw`` payload is also patched so stored/returned data is
      consistent with the indexed column.
    * Admins: ``actor_mbox`` must belong to a user in the same tenant. An
      empty/missing mbox defaults to the admin's own email for convenience.
    """
    authed_email = (request.user.email or "").strip().lower()
    authed_mbox = f"mailto:{authed_email}" if authed_email else ""

    is_admin = getattr(request.user, "role", None) in ADMIN_ROLES

    if not is_admin:
        # Overwrite unconditionally — we do not trust caller-supplied mbox.
        parsed["actor_mbox"] = authed_mbox
        raw_actor = parsed.get("raw", {}).get("actor")
        if isinstance(raw_actor, dict):
            raw_actor["mbox"] = authed_mbox
            # Strip any account-shaped claim that could re-impersonate.
            raw_actor.pop("account", None)
        return parsed, None

    # Admin path: empty mbox -> default to self.
    submitted = parsed.get("actor_mbox", "") or ""
    if not submitted:
        parsed["actor_mbox"] = authed_mbox
        raw_actor = parsed.get("raw", {}).get("actor")
        if isinstance(raw_actor, dict):
            raw_actor["mbox"] = authed_mbox
        return parsed, None

    # Same-tenant user required.
    if not submitted.lower().startswith("mailto:"):
        return parsed, Response(
            {"error": "actor.mbox must be a mailto: IRI"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    email = submitted[len("mailto:"):].strip().lower()
    if not email:
        return parsed, Response(
            {"error": "actor.mbox must contain an email"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    User = get_user_model()
    exists = User.objects.filter(
        email__iexact=email, tenant=request.tenant
    ).exists()
    if not exists:
        return parsed, Response(
            {"error": "actor.mbox does not match any user in this tenant"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Normalise to lower-case mailto form for consistency.
    parsed["actor_mbox"] = f"mailto:{email}"
    raw_actor = parsed.get("raw", {}).get("actor")
    if isinstance(raw_actor, dict):
        raw_actor["mbox"] = parsed["actor_mbox"]
    return parsed, None


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

def _parse_positive_int(raw: str | None, default: int, maximum: int) -> int:
    try:
        value = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default
    if value < 1:
        return default
    return min(value, maximum)


def _list_statements(request: Request) -> Response:
    qs = XAPIStatement.objects.order_by("-stored")

    actor = request.query_params.get("actor")
    if actor:
        # M3 — exact match on mbox (was icontains). Support comma-separated
        # list to keep admin UX practical.
        actor_values = [a.strip() for a in actor.split(",") if a.strip()]
        if len(actor_values) == 1:
            qs = qs.filter(actor_mbox__iexact=actor_values[0])
        elif actor_values:
            qs = qs.filter(actor_mbox__in=actor_values)

    verb = request.query_params.get("verb")
    if verb:
        qs = qs.filter(verb_id=verb)

    since = request.query_params.get("since")
    if since:
        parsed_dt = parse_datetime(since)
        if parsed_dt is not None:
            qs = qs.filter(stored__gte=parsed_dt)

    # Pagination (offset/limit).
    limit = _parse_positive_int(
        request.query_params.get("limit"), LIST_DEFAULT_LIMIT, LIST_MAX_LIMIT
    )
    try:
        offset = max(0, int(request.query_params.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0

    total = qs.count()
    rows = list(qs[offset : offset + limit])
    return Response(
        {
            "count": len(rows),
            "total": total,
            "offset": offset,
            "limit": limit,
            "results": [
                {
                    "id": str(s.statement_id),
                    "actor": s.actor_mbox,
                    "verb": s.verb_id,
                    "object": s.object_id,
                    "stored": s.stored.isoformat(),
                    "result": s.result,
                }
                for s in rows
            ],
        }
    )


def _create_statement(request: Request) -> Response:
    parsed, err = _validate_statement(request.data)
    if err:
        return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)

    parsed, impersonation_err = _enforce_actor_identity(request, parsed)
    if impersonation_err is not None:
        return impersonation_err

    # Idempotency: if (tenant, statement_id) already exists, return that row.
    #
    # Defence-in-depth — although ``XAPIStatement.objects`` is a
    # ``TenantManager`` (auto-scoped to ``get_current_tenant()``), pass
    # ``tenant=request.tenant`` explicitly so:
    #   * the code matches the comment + the
    #     ``xapi_statement_unique_per_tenant`` model constraint, and
    #   * a future refactor that swaps ``objects`` for ``all_objects``
    #     cannot silently re-introduce a cross-tenant idempotency leak
    #     (Tenant B reusing Tenant A's ``statement_id`` and getting back
    #     A's stored timestamp).
    existing = XAPIStatement.objects.filter(
        tenant=request.tenant,
        statement_id=parsed["statement_id"],
    ).first()
    if existing:
        return Response(
            {"id": str(existing.statement_id), "stored": existing.stored.isoformat()},
            status=status.HTTP_200_OK,
        )

    stmt = XAPIStatement.objects.create(tenant=request.tenant, **parsed)
    return Response(
        {"id": str(stmt.statement_id), "stored": stmt.stored.isoformat()},
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
@tenant_required
def xapi_statements(request: Request) -> Response:
    """Handle POST (any authed tenant user) or GET (admin-only) at the same URL."""
    if request.method == "POST":
        return _create_statement(request)

    # GET is admin-only
    if request.user.role not in ADMIN_ROLES:
        return Response(
            {"error": "Admin access required"},
            status=status.HTTP_403_FORBIDDEN,
        )
    return _list_statements(request)
