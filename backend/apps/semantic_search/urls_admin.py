"""URL routes mounted at /api/v1/admin/search/ (TASK-057)."""

from django.urls import path

from . import views


urlpatterns = [
    path(
        "reindex-tenant/",
        views.reindex_tenant_view,
        name="semantic_search_reindex_tenant",
    ),
    path(
        "status/",
        views.search_status_view,
        name="semantic_search_status",
    ),
]
