# config/asgi.py
"""
ASGI config for LMS project.

Supports both HTTP (Django) and WebSocket (Channels) protocols.
WebSocket endpoints:
  - /ws/notifications/                              real-time notifications
  - /ws/maic/classrooms/<uuid>/                     F2 (P0) per-element MAIC
                                                    image-task state stream
"""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Initialize Django ASGI application early to ensure apps are loaded
django_asgi_app = get_asgi_application()

# Import after Django setup to avoid AppRegistryNotReady
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from apps.notifications.middleware import JWTAuthMiddleware
from apps.notifications.routing import websocket_urlpatterns as notification_ws
from apps.courses.routing import websocket_urlpatterns as courses_ws


# Compose all WebSocket routes from the apps that own them. Order is
# irrelevant because each ``re_path`` carries a distinct prefix.
websocket_urlpatterns = list(notification_ws) + list(courses_ws)


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
