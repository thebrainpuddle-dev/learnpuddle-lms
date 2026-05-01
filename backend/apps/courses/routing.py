# apps/courses/routing.py
"""F2 (P0): WebSocket URL routing for MAIC classroom updates.

Provides a single WebSocket endpoint that streams per-element image-task
state transitions for one classroom. The consumer is JWT-authenticated
via the same ``Bearer.<jwt>`` subprotocol convention used by the
notifications consumer (see ``apps/notifications/middleware.py``).
"""

from django.urls import re_path

from . import maic_consumers


websocket_urlpatterns = [
    # Per-classroom MAIC update channel.  Captures ``classroom_id`` so
    # the consumer can scope its group_add to that classroom only.
    re_path(
        r"ws/maic/classrooms/(?P<classroom_id>[0-9a-f-]{36})/$",
        maic_consumers.MAICClassroomConsumer.as_asgi(),
    ),
]
