"""Channels routing for MAIC v2.

Path is `/ws/maic/v2/classroom/<session_id>/` — explicit `v2` segment
to avoid collision with the V1 `/ws/maic/classrooms/<uuid>/` route
mounted by `apps/courses/routing.py`. See
obsidian-vault/.../maic-rebuild/phase-0-foundation/READINESS-AUDIT.md §Issue-3.

Mounted into `config/asgi.py` only when `settings.MAIC_V2_ENABLED` is
truthy at import time. The flag itself is added to settings.py in this
ticket (default False); MAIC-007 adds the matching frontend env var.
"""
from django.urls import re_path

from .consumers import ClassroomConsumer
from .generation.consumers import GenerationConsumer

websocket_urlpatterns = [
    re_path(
        r"^ws/maic/v2/classroom/(?P<session_id>[\w-]{1,64})/$",
        ClassroomConsumer.as_asgi(),
    ),
    re_path(
        r"^ws/maic/generation/(?P<job_id>[\w-]{1,64})/$",
        GenerationConsumer.as_asgi(),
    ),
]
