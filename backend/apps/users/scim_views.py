"""
SCIM 2.0 User Provisioning views (TASK-023).

Implements the RFC 7644 SCIM Protocol for the /scim/v2/ namespace:

    GET  /scim/v2/Users               — list (pagination + userName filter)
    POST /scim/v2/Users               — provision a new user
    GET  /scim/v2/Users/{id}          — retrieve single user
    PUT  /scim/v2/Users/{id}          — full replace
    PATCH /scim/v2/Users/{id}         — partial update via Operations array
    DELETE /scim/v2/Users/{id}        — soft deprovision (set is_active=False)
    GET  /scim/v2/ServiceProviderConfig — advertise capabilities

Authentication:  Authorization: Bearer <raw_scim_token>
The raw token is hashed (SHA-256) and looked up in SCIMToken; the matching
row provides the tenant for the entire request.

These are intentionally plain Django views (not DRF APIView) so that DRF's
JWT authentication backend is never invoked for SCIM requests.
"""

import json
import logging
import re

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from utils.audit import log_audit

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SCIM URNs / constants
# ---------------------------------------------------------------------------

_SCHEMA_USER = "urn:ietf:params:scim:schemas:core:2.0:User"
_SCHEMA_LIST = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
_SCHEMA_PATCH = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
_SCHEMA_ERROR = "urn:ietf:params:scim:api:messages:2.0:Error"
_SCHEMA_SPC = "urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"
_EXT_USER = "urn:learnpuddle:1.0:User"
_CONTENT_TYPE = "application/scim+json"

# Regex for SCIM filter:  userName eq "alice@example.com"
_FILTER_RE = re.compile(r'userName\s+eq\s+"([^"]+)"', re.IGNORECASE)


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


def _serialize_user(user):
    """Return the SCIM User resource dict for *user*."""
    return {
        "schemas": [_SCHEMA_USER],
        "id": str(user.id),
        "externalId": user.employee_id or None,
        "userName": user.email,
        "name": {
            "givenName": user.first_name,
            "familyName": user.last_name,
            "formatted": f"{user.first_name} {user.last_name}".strip(),
        },
        "displayName": f"{user.first_name} {user.last_name}".strip(),
        "active": user.is_active and not user.is_deleted,
        "emails": [{"value": user.email, "primary": True, "type": "work"}],
        _EXT_USER: {
            "role": user.role,
            "department": user.department or "",
        },
        "meta": {
            "resourceType": "User",
            "created": user.date_joined.isoformat() if user.date_joined else None,
            "lastModified": user.updated_at.isoformat() if user.updated_at else None,
            "location": f"/scim/v2/Users/{user.id}",
        },
    }


def _tenant_users(tenant):
    """
    Return a QuerySet of non-deleted users for *tenant*, bypassing the
    thread-local tenant context set by TenantMiddleware (which may be None
    for SCIM requests that don't carry a regular Host header).
    """
    from apps.users.models import User

    return User.objects.all_tenants().filter(tenant=tenant)


# ---------------------------------------------------------------------------
# Endpoint: GET/POST /scim/v2/Users
# ---------------------------------------------------------------------------

@csrf_exempt
def scim_users_view(request):
    """List users (GET) or provision a new user (POST)."""
    scim_token = _authenticate_scim(request)
    if scim_token is None:
        return _scim_401()

    tenant = scim_token.tenant

    # ------------------------------------------------------------------
    if request.method == "GET":
        users = _tenant_users(tenant)

        # SCIM filter: userName eq "..."
        filter_param = request.GET.get("filter", "").strip()
        if filter_param:
            m = _FILTER_RE.search(filter_param)
            if m:
                users = users.filter(email__iexact=m.group(1))
            # Unknown filter → return empty per spec (don't 400)

        total = users.count()

        # Pagination (1-indexed per RFC 7644 §3.4.2.4)
        try:
            start_index = max(1, int(request.GET.get("startIndex", 1)))
            count = max(1, int(request.GET.get("count", 100)))
        except (TypeError, ValueError):
            start_index, count = 1, 100

        offset = start_index - 1
        page_users = users.order_by("email")[offset: offset + count]

        return _json_resp({
            "schemas": [_SCHEMA_LIST],
            "totalResults": total,
            "startIndex": start_index,
            "itemsPerPage": count,
            "Resources": [_serialize_user(u) for u in page_users],
        })

    # ------------------------------------------------------------------
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _scim_error(400, "Invalid JSON body.", "invalidSyntax")

        user_name = (data.get("userName") or "").strip()
        if not user_name:
            return _scim_error(400, "userName is required.", "invalidValue")

        from apps.users.models import User

        # 1) Legitimate in-tenant collision → 409 uniqueness (SCIM-spec required).
        #    Use all_with_deleted() to include soft-deleted rows because
        #    User.email has unique=True at the DB level across ALL rows
        #    (including is_deleted=True ones).  Without this, a user soft-
        #    deleted via the admin path would pass this check, and create_user()
        #    would raise IntegrityError → 500.  (M1 fix, TASK-023-followup.)
        if User.objects.all_with_deleted().filter(
            tenant=tenant, email__iexact=user_name
        ).exists():
            return _scim_error(
                409,
                f"User with userName '{user_name}' already exists.",
                "uniqueness",
            )

        # 2) Cross-tenant collision → generic 400, no enumeration leak.
        #    Email is globally unique so we still cannot insert; surface a
        #    non-specific failure and log for ops investigation.
        #    Also uses all_with_deleted() to catch soft-deleted cross-tenant
        #    rows (same M1 rationale).
        if User.objects.all_with_deleted().filter(email__iexact=user_name).exists():
            logger.warning(
                "scim_post: cross-tenant email collision token_tenant=%s email=%s",
                tenant.id,
                user_name,
            )
            return _scim_error(400, "Email unavailable.", "invalidValue")

        name_obj = data.get("name") or {}
        first_name = (name_obj.get("givenName") or "").strip()
        last_name = (name_obj.get("familyName") or "").strip()
        external_id = (data.get("externalId") or "").strip()
        is_active = bool(data.get("active", True))

        # LearnPuddle custom extension
        ext = data.get(_EXT_USER) or {}
        department = (ext.get("department") or "").strip()

        user = User.objects.create_user(
            email=user_name,
            password=None,           # SCIM users authenticate via SSO
            first_name=first_name,
            last_name=last_name,
            tenant=tenant,
            role="TEACHER",          # Default role for provisioned users
            is_active=is_active,
            employee_id=external_id,
            department=department,
        )

        log_audit(
            action="SCIM_CREATE",
            target_type="User",
            target_id=str(user.id),
            target_repr=user.email,
            changes={
                "email": user_name,
                "scim_token": scim_token.name,
                "tenant": str(tenant.id),
            },
            tenant=tenant,
        )

        return _json_resp(_serialize_user(user), status=201)

    return _scim_error(405, "Method not allowed.")


# ---------------------------------------------------------------------------
# PATCH helpers — shared by scim_user_detail_view
# ---------------------------------------------------------------------------

def _apply_scim_replace_path(user, path: str, value) -> None:
    """
    Apply a single SCIM PATCH 'replace' operation that carries an explicit path.

    Recognised paths:
        active               → is_active (bool coerced)
        name.givenName       → first_name (stripped)
        name.familyName      → last_name (stripped)
        externalId           → employee_id (stripped)
        <_EXT_USER>:department → department (stripped)

    Unrecognised paths are silently ignored per RFC 7644 §3.5.2.
    """
    if path == "active":
        user.is_active = bool(value)
    elif path == "name.givenName":
        user.first_name = str(value).strip()
    elif path == "name.familyName":
        user.last_name = str(value).strip()
    elif path == "externalId":
        user.employee_id = (str(value) if value else "").strip()
    elif path == f"{_EXT_USER}:department":
        user.department = (str(value) if value else "").strip()
    # Unrecognised paths are silently ignored (RFC 7644 §3.5.2)


def _apply_scim_replace_dict(user, value_dict: dict) -> None:
    """
    Apply a path-less SCIM PATCH 'replace' operation (RFC 7644 §3.5.2.3).

    When 'path' is absent the 'value' is a dict whose keys are treated as
    attribute names.  Azure AD frequently sends:
        {"op": "replace", "value": {"active": false, "name": {"givenName": "X"}}}

    Supported keys:
        active               → bool → is_active
        name                 → dict with givenName / familyName
        externalId           → str  → employee_id
        <_EXT_USER>          → dict with department
    """
    if "active" in value_dict:
        user.is_active = bool(value_dict["active"])

    name_obj = value_dict.get("name")
    if isinstance(name_obj, dict):
        if "givenName" in name_obj:
            user.first_name = str(name_obj["givenName"]).strip()
        if "familyName" in name_obj:
            user.last_name = str(name_obj["familyName"]).strip()

    if "externalId" in value_dict:
        user.employee_id = (str(value_dict["externalId"]) if value_dict["externalId"] else "").strip()

    ext_obj = value_dict.get(_EXT_USER)
    if isinstance(ext_obj, dict) and "department" in ext_obj:
        user.department = (str(ext_obj["department"]) if ext_obj["department"] else "").strip()


# ---------------------------------------------------------------------------
# Endpoint: GET/PUT/PATCH/DELETE /scim/v2/Users/{user_id}
# ---------------------------------------------------------------------------

@csrf_exempt
def scim_user_detail_view(request, user_id):
    """Retrieve, replace, patch, or deprovision a single user."""
    scim_token = _authenticate_scim(request)
    if scim_token is None:
        return _scim_401()

    tenant = scim_token.tenant

    from apps.users.models import User
    try:
        user = _tenant_users(tenant).get(pk=user_id)
    except User.DoesNotExist:
        return _scim_error(404, "Resource not found.")

    # ------------------------------------------------------------------
    if request.method == "GET":
        return _json_resp(_serialize_user(user))

    # ------------------------------------------------------------------
    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _scim_error(400, "Invalid JSON body.", "invalidSyntax")

        name_obj = data.get("name") or {}
        user.first_name = (name_obj.get("givenName") or user.first_name).strip()
        user.last_name = (name_obj.get("familyName") or user.last_name).strip()

        if "active" in data:
            user.is_active = bool(data["active"])

        if "externalId" in data:
            user.employee_id = (data["externalId"] or "").strip()

        ext = data.get(_EXT_USER) or {}
        if "department" in ext:
            user.department = (ext["department"] or "").strip()

        user.save()

        log_audit(
            action="SCIM_UPDATE",
            target_type="User",
            target_id=str(user.id),
            target_repr=user.email,
            changes={"method": "PUT", "scim_token": scim_token.name},
            tenant=tenant,
        )

        return _json_resp(_serialize_user(user))

    # ------------------------------------------------------------------
    if request.method == "PATCH":
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _scim_error(400, "Invalid JSON body.", "invalidSyntax")

        operations = data.get("Operations")
        if not operations:
            return _scim_error(400, "Operations array is required.", "invalidValue")

        for op in operations:
            op_type = (op.get("op") or "").lower()
            path = (op.get("path") or "")
            value = op.get("value")

            if op_type == "replace":
                if not path and isinstance(value, dict):
                    # M3 (RFC 7644 §3.5.2.3): path-less replace — apply the
                    # value dict's keys as if each were individual pathed ops.
                    # Azure AD uses this form: {"op":"replace","value":{"active":false,...}}
                    _apply_scim_replace_dict(user, value)
                else:
                    _apply_scim_replace_path(user, path, value)
            else:
                # M4: log unrecognised op types at DEBUG so IdP quirks are
                # visible without flooding info/warning logs.
                if op_type:
                    logger.debug(
                        "scim_patch: unrecognised op type %r for user=%s — skipping",
                        op_type, user.id,
                    )

        user.save()

        log_audit(
            action="SCIM_PATCH",
            target_type="User",
            target_id=str(user.id),
            target_repr=user.email,
            changes={
                "method": "PATCH",
                "op_count": len(operations),
                "scim_token": scim_token.name,
            },
            tenant=tenant,
        )

        return _json_resp(_serialize_user(user))

    # ------------------------------------------------------------------
    if request.method == "DELETE":
        user.is_active = False
        user.save(update_fields=["is_active"])

        log_audit(
            action="SCIM_DEPROVISION",
            target_type="User",
            target_id=str(user.id),
            target_repr=user.email,
            changes={"deprovisioned": True, "scim_token": scim_token.name},
            tenant=tenant,
        )

        # 204 No Content — no body per RFC 7644 §3.6
        return HttpResponse(status=204)

    return _scim_error(405, "Method not allowed.")


# ---------------------------------------------------------------------------
# Endpoint: GET /scim/v2/ServiceProviderConfig  (no auth required)
# ---------------------------------------------------------------------------

def scim_service_provider_config_view(request):
    """
    Advertise the SCIM capabilities of this service provider.

    Per RFC 7644 §4, this endpoint is public — no authentication needed.
    IdPs call it to discover which operations and filters are supported
    before configuring their SCIM integration.

    Updated in TASK-024 to advertise Groups support.
    """
    return _json_resp({
        "schemas": [_SCHEMA_SPC],
        "documentationUri": "https://learnpuddle.com/docs/scim",
        "patch": {"supported": True},
        "bulk": {
            "supported": False,
            "maxOperations": 0,
            "maxPayloadSize": 0,
        },
        "filter": {
            "supported": True,
            "maxResults": 200,
        },
        "changePassword": {"supported": False},
        "sort": {"supported": False},
        "etag": {"supported": False},
        # TASK-024: Groups provisioning is now supported.
        "groups": {"supported": True},
        # Enumerated schema URNs so IdPs know which resource types to expect.
        "supportedSchemas": [
            {
                "id": "urn:ietf:params:scim:schemas:core:2.0:User",
                "name": "User",
                "description": "User account (maps to LearnPuddle User model)",
            },
            {
                "id": "urn:ietf:params:scim:schemas:core:2.0:Group",
                "name": "Group",
                "description": "Group (maps to LearnPuddle TeacherGroup)",
            },
            {
                "id": "urn:learnpuddle:1.0:User",
                "name": "LearnPuddleUser",
                "description": "Custom extension: role and department fields",
            },
        ],
        "authenticationSchemes": [
            {
                "type": "oauthbearertoken",
                "name": "OAuth Bearer Token",
                "description": (
                    "Per-tenant static Bearer tokens generated in the "
                    "LearnPuddle admin console.  Tokens are stored as "
                    "SHA-256 hashes and cannot be recovered after creation."
                ),
                "specUri": "https://www.rfc-editor.org/rfc/rfc6750",
                "primary": True,
            }
        ],
    })


# ---------------------------------------------------------------------------
# SCIM schema catalogue — used by /scim/v2/Schemas discovery endpoint
# ---------------------------------------------------------------------------

_SCIM_SCHEMA_USER = {
    "id": "urn:ietf:params:scim:schemas:core:2.0:User",
    "name": "User",
    "description": "User account resource (RFC 7643 §4.1)",
    "attributes": [
        {
            "name": "userName",
            "type": "string",
            "multiValued": False,
            "description": "Primary identifier for the user; maps to User.email.",
            "required": True,
            "caseExact": False,
            "mutability": "readWrite",
            "returned": "default",
            "uniqueness": "global",
        },
        {
            "name": "name",
            "type": "complex",
            "multiValued": False,
            "description": "The components of the user's name.",
            "required": False,
            "mutability": "readWrite",
            "returned": "default",
            "subAttributes": [
                {
                    "name": "givenName",
                    "type": "string",
                    "multiValued": False,
                    "description": "First name.",
                    "required": False,
                    "caseExact": False,
                    "mutability": "readWrite",
                    "returned": "default",
                    "uniqueness": "none",
                },
                {
                    "name": "familyName",
                    "type": "string",
                    "multiValued": False,
                    "description": "Last name.",
                    "required": False,
                    "caseExact": False,
                    "mutability": "readWrite",
                    "returned": "default",
                    "uniqueness": "none",
                },
                {
                    "name": "formatted",
                    "type": "string",
                    "multiValued": False,
                    "description": "Full name, formatted for display.",
                    "required": False,
                    "caseExact": False,
                    "mutability": "readOnly",
                    "returned": "default",
                    "uniqueness": "none",
                },
            ],
        },
        {
            "name": "displayName",
            "type": "string",
            "multiValued": False,
            "description": "Name of the user suitable for display.",
            "required": False,
            "caseExact": False,
            "mutability": "readOnly",
            "returned": "default",
            "uniqueness": "none",
        },
        {
            "name": "active",
            "type": "boolean",
            "multiValued": False,
            "description": "Whether the user account is active.",
            "required": False,
            "mutability": "readWrite",
            "returned": "default",
        },
        {
            "name": "emails",
            "type": "complex",
            "multiValued": True,
            "description": "Email addresses for the user.",
            "required": False,
            "mutability": "readOnly",
            "returned": "default",
            "subAttributes": [
                {
                    "name": "value",
                    "type": "string",
                    "multiValued": False,
                    "description": "Email address.",
                    "required": False,
                    "caseExact": False,
                    "mutability": "readOnly",
                    "returned": "default",
                    "uniqueness": "none",
                },
                {
                    "name": "primary",
                    "type": "boolean",
                    "multiValued": False,
                    "description": "Whether this is the primary email.",
                    "required": False,
                    "mutability": "readOnly",
                    "returned": "default",
                },
            ],
        },
        {
            "name": "externalId",
            "type": "string",
            "multiValued": False,
            "description": "Identifier set by the provisioning client (maps to employee_id).",
            "required": False,
            "caseExact": True,
            "mutability": "readWrite",
            "returned": "default",
            "uniqueness": "none",
        },
    ],
}

_SCIM_SCHEMA_GROUP = {
    "id": "urn:ietf:params:scim:schemas:core:2.0:Group",
    "name": "Group",
    "description": "Group resource — maps to LearnPuddle TeacherGroup (RFC 7643 §4.2)",
    "attributes": [
        {
            "name": "displayName",
            "type": "string",
            "multiValued": False,
            "description": "Human-readable name for the group.",
            "required": True,
            "caseExact": False,
            "mutability": "readWrite",
            "returned": "default",
            "uniqueness": "server",
        },
        {
            "name": "members",
            "type": "complex",
            "multiValued": True,
            "description": "List of members of the group.",
            "required": False,
            "mutability": "readWrite",
            "returned": "default",
            "subAttributes": [
                {
                    "name": "value",
                    "type": "string",
                    "multiValued": False,
                    "description": "User UUID.",
                    "required": False,
                    "caseExact": False,
                    "mutability": "readWrite",
                    "returned": "default",
                    "uniqueness": "none",
                },
                {
                    "name": "display",
                    "type": "string",
                    "multiValued": False,
                    "description": "Display name of the member.",
                    "required": False,
                    "caseExact": False,
                    "mutability": "readOnly",
                    "returned": "default",
                    "uniqueness": "none",
                },
            ],
        },
    ],
}

_SCIM_SCHEMA_LP_USER_EXT = {
    "id": "urn:learnpuddle:1.0:User",
    "name": "LearnPuddleUser",
    "description": "LearnPuddle-specific User extension: role and department.",
    "attributes": [
        {
            "name": "role",
            "type": "string",
            "multiValued": False,
            "description": "LearnPuddle user role: TEACHER, HOD, IB_COORDINATOR, etc.",
            "required": False,
            "caseExact": True,
            "mutability": "readOnly",
            "returned": "default",
            "uniqueness": "none",
        },
        {
            "name": "department",
            "type": "string",
            "multiValued": False,
            "description": "User's department (e.g. Science, Mathematics).",
            "required": False,
            "caseExact": False,
            "mutability": "readWrite",
            "returned": "default",
            "uniqueness": "none",
        },
    ],
}

# Ordered by precedence for /scim/v2/Schemas list response
_SCIM_SCHEMAS_BY_ID = {
    _SCIM_SCHEMA_USER["id"]: _SCIM_SCHEMA_USER,
    _SCIM_SCHEMA_GROUP["id"]: _SCIM_SCHEMA_GROUP,
    _SCIM_SCHEMA_LP_USER_EXT["id"]: _SCIM_SCHEMA_LP_USER_EXT,
}

# ResourceType catalogue — used by /scim/v2/ResourceTypes discovery endpoint
_SCIM_RESOURCE_TYPES = [
    {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"],
        "id": "User",
        "name": "User",
        "description": "User account",
        "endpoint": "/scim/v2/Users",
        "schema": "urn:ietf:params:scim:schemas:core:2.0:User",
        "schemaExtensions": [
            {
                "schema": "urn:learnpuddle:1.0:User",
                "required": False,
            }
        ],
        "meta": {
            "resourceType": "ResourceType",
            "location": "/scim/v2/ResourceTypes/User",
        },
    },
    {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"],
        "id": "Group",
        "name": "Group",
        "description": "Group (TeacherGroup)",
        "endpoint": "/scim/v2/Groups",
        "schema": "urn:ietf:params:scim:schemas:core:2.0:Group",
        "schemaExtensions": [],
        "meta": {
            "resourceType": "ResourceType",
            "location": "/scim/v2/ResourceTypes/Group",
        },
    },
]

_SCIM_RESOURCE_TYPES_BY_NAME = {rt["name"]: rt for rt in _SCIM_RESOURCE_TYPES}


# ---------------------------------------------------------------------------
# Endpoint: GET /scim/v2/Schemas[/{schema_id}]  (RFC 7644 §7, public)
# ---------------------------------------------------------------------------

def scim_schemas_view(request):
    """
    Return all supported SCIM schema definitions.

    Per RFC 7644 §4 this endpoint requires no authentication — it is a
    public discovery endpoint that IdPs call during integration setup.
    """
    resources = list(_SCIM_SCHEMAS_BY_ID.values())
    return _json_resp({
        "schemas": [_SCHEMA_LIST],
        "totalResults": len(resources),
        "itemsPerPage": len(resources),
        "startIndex": 1,
        "Resources": resources,
    })


def scim_schema_detail_view(request, schema_id):
    """
    Return a single SCIM schema definition by its URN identifier.

    ``schema_id`` is URL-decoded by Django before reaching this view, so
    colons in the URN path do not need escaping in practice.
    """
    schema = _SCIM_SCHEMAS_BY_ID.get(schema_id)
    if schema is None:
        return _scim_error(404, f"Schema '{schema_id}' not found.")
    return _json_resp(schema)


# ---------------------------------------------------------------------------
# Endpoint: GET /scim/v2/ResourceTypes[/{name}]  (RFC 7644 §6, public)
# ---------------------------------------------------------------------------

def scim_resource_types_view(request):
    """
    Return all supported SCIM ResourceType definitions.

    Per RFC 7644 §4 this endpoint requires no authentication.
    """
    return _json_resp({
        "schemas": [_SCHEMA_LIST],
        "totalResults": len(_SCIM_RESOURCE_TYPES),
        "itemsPerPage": len(_SCIM_RESOURCE_TYPES),
        "startIndex": 1,
        "Resources": _SCIM_RESOURCE_TYPES,
    })


def scim_resource_type_detail_view(request, name):
    """Return a single SCIM ResourceType by name (e.g. 'User' or 'Group')."""
    rt = _SCIM_RESOURCE_TYPES_BY_NAME.get(name)
    if rt is None:
        return _scim_error(404, f"ResourceType '{name}' not found.")
    return _json_resp(rt)
