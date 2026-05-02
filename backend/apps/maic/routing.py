"""Channels routing for MAIC v2.

Populated by MAIC-003. Mounted into config/asgi.py only when
settings.MAIC_V2_ENABLED is True (gated by MAIC-007).
"""
from django.urls import re_path

websocket_urlpatterns: list = []
