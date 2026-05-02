# config/asgi.py
"""
ASGI config for LMS project.

Supports both HTTP (Django) and WebSocket (Channels) protocols.
WebSocket endpoints:
  - /ws/notifications/                              real-time notifications
  - /ws/maic/classrooms/<uuid>/                     F2 (P0) per-element MAIC
                                                    image-task state stream
  - /ws/maic/v2/classroom/<session_id>/             MAIC v2 — gated by
                                                    settings.MAIC_V2_ENABLED
"""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Initialize Django ASGI application early to ensure apps are loaded
django_asgi_app = get_asgi_application()

# Import after Django setup to avoid AppRegistryNotReady
from django.conf import settings
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from apps.notifications.middleware import JWTAuthMiddleware
from apps.notifications.routing import websocket_urlpatterns as notification_ws
from apps.courses.routing import websocket_urlpatterns as courses_ws

# MAIC v2 routes are mounted only when the flag is on at startup. Tests
# that need the route set MAIC_V2_ENABLED=true in the env BEFORE pytest
# imports settings — see apps/maic/tests_consumers.py header comment.
maic_v2_ws: list = []
if getattr(settings, "MAIC_V2_ENABLED", False):
    from apps.maic.routing import websocket_urlpatterns as maic_v2_ws_routes
    maic_v2_ws = list(maic_v2_ws_routes)

# Compose all WebSocket routes from the apps that own them. Order is
# irrelevant because each ``re_path`` carries a distinct prefix.
websocket_urlpatterns = list(notification_ws) + list(courses_ws) + maic_v2_ws


application = ProtocolTypeRouter({
    # HTTP requests handled by Django
    "http": django_asgi_app,

    # WebSocket requests handled by Channels
    "websocket": AllowedHostsOriginValidator(
        JWTAuthMiddleware(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
