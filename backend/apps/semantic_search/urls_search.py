"""URL routes mounted at /api/v1/search/ (TASK-057)."""

from django.urls import path

from . import views


urlpatterns = [
    path("semantic/", views.semantic_search_view, name="semantic_search_query"),
]
