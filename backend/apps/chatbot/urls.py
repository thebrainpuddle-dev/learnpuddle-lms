"""
URL patterns for the chatbot app (TASK-059).

Mounted at /api/v1/chatbot/ in config/urls.py.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("ask/", views.ask_view, name="chatbot-ask"),
    path("history/", views.history_list_view, name="chatbot-history-list"),
    path("history/<uuid:query_id>/", views.history_delete_view, name="chatbot-history-delete"),
]
