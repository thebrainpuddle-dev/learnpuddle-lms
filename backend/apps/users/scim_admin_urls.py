"""
URL patterns for the SCIM token admin API (TASK-023).

Mounted at admin/sso/ inside _api_patterns → /api/v1/admin/sso/...
"""

from django.urls import path

from . import scim_admin_views

app_name = "scim_admin"

urlpatterns = [
    path(
        "scim-tokens/",
        scim_admin_views.scim_token_list_create,
        name="scim_tokens",
    ),
    path(
        "scim-tokens/<uuid:token_id>/",
        scim_admin_views.scim_token_detail,
        name="scim_token_detail",
    ),
]
