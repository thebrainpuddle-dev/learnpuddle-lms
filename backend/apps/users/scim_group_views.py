"""
SCIM 2.0 Groups Provisioning views (TASK-024).

Implements the RFC 7643 / RFC 7644 SCIM Group resource for the /scim/v2/ namespace:

    GET    /scim/v2/Groups              — list (pagination + displayName filter)
    POST   /scim/v2/Groups              — provision a new group → TeacherGroup
    GET    /scim/v2/Groups/{id}         — retrieve single group with member list
    PUT    /scim/v2/Groups/{id}         — full replace (rename + set members)
    PATCH  /scim/v2/Groups/{id}         — partial update via Operations array
    DELETE /scim/v2/Groups/{id}         — delete the group

Authentication:  Authorization: Bearer <raw_scim_token>
The raw token is hashed (SHA-256) and looked up in SCIMToken; the matching
row provides the tenant for the entire request.

These are plain Django views (not DRF APIView) so that DRF's JWT authentication
backend is never invoked for SCIM requests.

Design decisions:
- Groups map 1-to-1 to TeacherGroup objects (same tenant, same UUID primary key).
- Member list is the User M2M relation `TeacherGroup.members`.
- Members from other tenants in a PUT/PATCH payload are silently ignored; they
  will never be added.  This prevents cross-tenant escalation via SCIM group push.
- DELETE is a hard delete on TeacherGroup — groups are lightweight and not
  independently tracked for compliance purposes.  The audit log records the delete.
"""

import json
import re
import uuid as uuid_module

from django.db import IntegrityError
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from apps.courses.models import TeacherGroup
from apps.users.models import User
from utils.audit import log_audit

# ---------------------------------------------------------------------------
# SCIM URNs / constants
# ---------------------------------------------------------------------------

_SCHEMA_GROUP = "urn:ietf:params:scim:schemas:core:2.0:Group"
_SCHEMA_LIST = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
_SCHEMA_PATCH = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
_SCHEMA_ERROR = "urn:ietf:params:scim:api:messages:2.0:Error"
_CONTENT_TYPE = "application/scim+json"

# Regex for SCIM filter:  displayName eq "Math Teachers"
_FILTER_RE = re.compile(r'displayName\s+eq\s+"([^"]+)"', re.IGNORECASE)

# Regex for PATCH remove path:  members[value eq "uuid"]
# Uses re.search so paths with surrounding context (e.g. trailing whitespace or
# filter sub-expressions) are still matched leniently per RFC 7644.
_MEMBER_FILTER_RE = re.compile(r'members\[value\s+eq\s+"([^"]+)"\]', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _json_resp(data, status=200):
    return JsonResponse(data, status=status, content_type=_CONTENT_TYPE)


def _scim_error(status, detail, scim_type=None):
    body = {"schemas": [_SCHEMA_ERROR], "status": status, "detail": detail}
    if scim_type:
        body["scimType"] = scim_type
    return _json_resp(body, status=status)


def _scim_401():
    return _scim_error(401, "Authentication required.")


def _authenticate_scim(request):
    """
    Parse the Authorization header and verify the SCIM Bearer token.

    Returns the :class:`~apps.users.scim_models.SCIMToken` instance on success,
    or ``None`` when the token is absent / invalid / revoked.
    """
    from apps.users.scim_models import SCIMToken

    auth = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth.startswith("Bearer "):
        return None
    # .rstrip() strips trailing whitespace / newlines that some HTTP clients
    # append, without stripping a leading space (which would silently accept a
    # "Bearer  token" double-space header and look up the wrong hash).
    raw_token = auth[len("Bearer "):].rstrip()
    return SCIMToken.verify(raw_token)


def _serialize_group(group):
    """Return the SCIM Group resource dict for *group*."""
    members = [
        {
            "value": str(u.id),
            "display": f"{u.first_name} {u.last_name}".strip(),
            "$ref": f"/scim/v2/Users/{u.id}",
        }
        for u in group.members.all()
    ]
    return {
        "schemas": [_SCHEMA_GROUP],
        "id": str(group.id),
        "displayName": group.name,
        "members": members,
        "meta": {
            "resourceType": "Group",
            "created": group.created_at.isoformat() if group.created_at else None,
            "lastModified": group.updated_at.isoformat() if group.updated_at else None,
            "location": f"/scim/v2/Groups/{group.id}",
        },
    }


def _tenant_groups(tenant):
    """
    Return a QuerySet of all TeacherGroups for *tenant*.

    Uses `all_objects` manager to bypass TenantManager thread-local context,
    which may be None for SCIM requests that don't carry a regular Host header.
    """
    return TeacherGroup.all_objects.filter(tenant=tenant)


def _resolve_members(tenant, member_list):
    """
    Given a SCIM members array (list of {"value": "<user_id>"} dicts),
    return a QuerySet of User objects that belong to *tenant*.

    Members referencing users from other tenants are silently skipped.
    Members with invalid UUIDs are silently skipped.
    """
    ids = []
    for entry in (member_list or []):
        raw = (entry.get("value") or "").strip()
        try:
            ids.append(uuid_module.UUID(raw))
        except (ValueError, AttributeError):
            continue

    if not ids:
        return User.objects.none()

    # Filter by tenant to prevent cross-tenant membership injection
    return User.objects.all_tenants().filter(id__in=ids, tenant=tenant)


# ---------------------------------------------------------------------------
# Endpoint: GET/POST /scim/v2/Groups
# ---------------------------------------------------------------------------

@csrf_exempt
def scim_groups_view(request):
    """List groups (GET) or provision a new group (POST)."""
    scim_token = _authenticate_scim(request)
    if scim_token is None:
        return _scim_401()

    tenant = scim_token.tenant

    # ------------------------------------------------------------------
    if request.method == "GET":
        groups = _tenant_groups(tenant)

        # SCIM filter: displayName eq "..."
        filter_param = request.GET.get("filter", "").strip()
        if filter_param:
            m = _FILTER_RE.search(filter_param)
            if m:
                groups = groups.filter(name__iexact=m.group(1))
            # Unknown filter → return empty per spec (don't 400)

        total = groups.count()

        # Pagination (1-indexed per RFC 7644 §3.4.2.4)
        try:
            start_index = max(1, int(request.GET.get("startIndex", 1)))
            count = max(1, int(request.GET.get("count", 100)))
        except (TypeError, ValueError):
            start_index, count = 1, 100

        offset = start_index - 1
        page_groups = groups.prefetch_related("members").order_by("name")[offset: offset + count]

        return _json_resp({
            "schemas": [_SCHEMA_LIST],
            "totalResults": total,
            "startIndex": start_index,
            "itemsPerPage": count,
            "Resources": [_serialize_group(g) for g in page_groups],
        })

    # ------------------------------------------------------------------
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _scim_error(400, "Invalid JSON body.", "invalidSyntax")

        display_name = (data.get("displayName") or "").strip()
        if not display_name:
            return _scim_error(400, "displayName is required.", "invalidValue")

        # Check uniqueness within this tenant (unique_together: tenant + name)
        if TeacherGroup.all_objects.filter(tenant=tenant, name__iexact=display_name).exists():
            return _scim_error(
                409,
                f"Group with displayName '{display_name}' already exists.",
                "uniqueness",
            )

        try:
            # Use all_objects.create() to bypass the TenantManager thread-local
            # context, which may be None for SCIM requests without a Host header.
            group = TeacherGroup.all_objects.create(
                tenant=tenant,
                name=display_name,
            )
        except IntegrityError:
            return _scim_error(
                409,
                f"Group with displayName '{display_name}' already exists.",
                "uniqueness",
            )

        # Add members if provided
        members_data = data.get("members") or []
        if members_data:
            valid_members = _resolve_members(tenant, members_data)
            group.members.set(valid_members)

        log_audit(
            action="SCIM_GROUP_CREATE",
            target_type="TeacherGroup",
            target_id=str(group.id),
            target_repr=group.name,
            changes={
                "displayName": display_name,
                "scim_token": scim_token.name,
                "tenant": str(tenant.id),
                "member_count": group.members.count(),
            },
            tenant=tenant,
        )

        return _json_resp(_serialize_group(group), status=201)

    return _scim_error(405, "Method not allowed.")


# ---------------------------------------------------------------------------
# Endpoint: GET/PUT/PATCH/DELETE /scim/v2/Groups/{group_id}
# ---------------------------------------------------------------------------

@csrf_exempt
def scim_group_detail_view(request, group_id):
    """Retrieve, replace, patch, or delete a single group."""
    scim_token = _authenticate_scim(request)
    if scim_token is None:
        return _scim_401()

    tenant = scim_token.tenant

    try:
        group = _tenant_groups(tenant).prefetch_related("members").get(pk=group_id)
    except TeacherGroup.DoesNotExist:
        return _scim_error(404, "Resource not found.")

    # ------------------------------------------------------------------
    if request.method == "GET":
        return _json_resp(_serialize_group(group))

    # ------------------------------------------------------------------
    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _scim_error(400, "Invalid JSON body.", "invalidSyntax")

        display_name = (data.get("displayName") or "").strip()
        if display_name:
            group.name = display_name
            group.save(update_fields=["name"])

        # Full replace of member list
        members_data = data.get("members") or []
        valid_members = _resolve_members(tenant, members_data)
        group.members.set(valid_members)

        log_audit(
            action="SCIM_GROUP_UPDATE",
            target_type="TeacherGroup",
            target_id=str(group.id),
            target_repr=group.name,
            changes={"method": "PUT", "scim_token": scim_token.name},
            tenant=tenant,
        )

        return _json_resp(_serialize_group(group))

    # ------------------------------------------------------------------
    if request.method == "PATCH":
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _scim_error(400, "Invalid JSON body.", "invalidSyntax")

        operations = data.get("Operations")
        if not operations:
            return _scim_error(400, "Operations array is required.", "invalidValue")

        save_fields = []
        audit_ops = []  # Collect per-op detail for forensic audit log

        for op in operations:
            op_type = (op.get("op") or "").lower()
            path = (op.get("path") or "")
            value = op.get("value")

            if op_type == "replace":
                if path.lower() == "displayname":
                    new_name = str(value).strip() if value is not None else ""
                    if not new_name:
                        return _scim_error(
                            400,
                            "displayName cannot be empty.",
                            "invalidValue",
                        )
                    group.name = new_name
                    save_fields.append("name")
                    audit_ops.append({"op": "replace", "path": "displayName"})
                elif path.lower() == "members":
                    # Full member replace
                    valid_members = _resolve_members(tenant, value or [])
                    group.members.set(valid_members)
                    audit_ops.append({"op": "replace", "path": "members"})

            elif op_type == "add":
                if path.lower() == "members":
                    valid_members = _resolve_members(tenant, value or [])
                    group.members.add(*valid_members)
                    audit_ops.append({"op": "add", "path": "members"})

            elif op_type == "remove":
                # path can be:
                #   "members"                         → clear all
                #   'members[value eq "<uuid>"]'      → remove specific member
                if path.lower() == "members":
                    group.members.clear()
                    audit_ops.append({"op": "remove", "path": "members"})
                else:
                    # Use re.search for lenient matching (RFC 7644 §3.5.2)
                    m = _MEMBER_FILTER_RE.search(path)
                    if m:
                        member_id_str = m.group(1)
                        try:
                            member_uuid = uuid_module.UUID(member_id_str)
                            try:
                                member = User.objects.all_tenants().get(
                                    id=member_uuid, tenant=tenant
                                )
                                group.members.remove(member)
                                audit_ops.append({
                                    "op": "remove",
                                    "path": "members",
                                    "value": str(member_uuid),
                                })
                            except User.DoesNotExist:
                                pass  # Silently ignore unknown member
                        except (ValueError, AttributeError):
                            pass  # Silently ignore malformed UUID
                    # Unknown path → silently ignore per RFC 7644

        if save_fields:
            group.save(update_fields=list(set(save_fields)))

        log_audit(
            action="SCIM_GROUP_PATCH",
            target_type="TeacherGroup",
            target_id=str(group.id),
            target_repr=group.name,
            changes={
                "method": "PATCH",
                "op_count": len(operations),
                "ops": audit_ops,
                "scim_token": scim_token.name,
            },
            tenant=tenant,
        )

        return _json_resp(_serialize_group(group))

    # ------------------------------------------------------------------
    if request.method == "DELETE":
        group_name = group.name
        group_id_str = str(group.id)
        group.delete()

        log_audit(
            action="SCIM_GROUP_DELETE",
            target_type="TeacherGroup",
            target_id=group_id_str,
            target_repr=group_name,
            changes={"deleted": True, "scim_token": scim_token.name},
            tenant=tenant,
        )

        # 204 No Content — no body per RFC 7644 §3.6
        return HttpResponse(status=204)

    return _scim_error(405, "Method not allowed.")
