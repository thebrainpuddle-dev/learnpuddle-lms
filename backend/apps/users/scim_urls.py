"""
URL patterns for the SCIM 2.0 protocol endpoints (TASK-023 / TASK-024).

Mounted at /scim/v2/ in config/urls.py — outside /api/v1/ intentionally,
because the SCIM namespace is defined by RFC 7644 and must not be versioned
by the LearnPuddle API version scheme.

No trailing slashes: SCIM IdPs (Okta, Azure AD) do not append slashes.
"""

from django.urls import path

from . import scim_group_views, scim_views

urlpatterns = [
    # ── RFC 7644 §4 Discovery endpoints — no auth required ─────────────────
    path(
        "ServiceProviderConfig",
        scim_views.scim_service_provider_config_view,
        name="scim_service_provider_config",
    ),
    # Schema definitions (RFC 7644 §7)
    path(
        "Schemas",
        scim_views.scim_schemas_view,
        name="scim_schemas",
    ),
    # Single schema lookup by URN — the full URN is passed as a path segment;
    # Django's <path:> converter preserves colons and dots in the URN.
    path(
        "Schemas/<path:schema_id>",
        scim_views.scim_schema_detail_view,
        name="scim_schema_detail",
    ),
    # ResourceType definitions (RFC 7644 §6)
    path(
        "ResourceTypes",
        scim_views.scim_resource_types_view,
        name="scim_resource_types",
    ),
    # Single ResourceType by name (e.g. "User" or "Group")
    path(
        "ResourceTypes/<str:name>",
        scim_views.scim_resource_type_detail_view,
        name="scim_resource_type_detail",
    ),
    # ── Users (RFC 7644 §3) ────────────────────────────────────────────────
    path(
        "Users",
        scim_views.scim_users_view,
        name="scim_users",
    ),
    path(
        "Users/<uuid:user_id>",
        scim_views.scim_user_detail_view,
        name="scim_user_detail",
    ),
    # ── Groups (RFC 7644 §3, TASK-024) ────────────────────────────────────
    path(
        "Groups",
        scim_group_views.scim_groups_view,
        name="scim_groups",
    ),
    path(
        "Groups/<uuid:group_id>",
        scim_group_views.scim_group_detail_view,
        name="scim_group_detail",
    ),
]
