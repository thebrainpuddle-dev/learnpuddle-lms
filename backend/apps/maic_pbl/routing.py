"""Channels routing for the PBL subsystem (Phase 7, MAIC-704).

Path: `/ws/maic/pbl/<session_id>/` — distinct prefix from the
classroom WS at `/ws/maic/v2/classroom/...`. Mounted into
config/asgi.py only when settings.MAIC_V2_ENABLED is truthy at
import time (same posture as apps.maic.routing).
"""
from django.urls import re_path

from apps.maic_pbl.consumers import PBLChatConsumer


websocket_urlpatterns = [
    re_path(
        r"^ws/maic/pbl/(?P<session_id>[\w-]{1,64})/$",
        PBLChatConsumer.as_asgi(),
    ),
]
