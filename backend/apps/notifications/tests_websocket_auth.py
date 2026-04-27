# apps/notifications/tests_websocket_auth.py
"""
Tests for WebSocket JWT authentication via subprotocol header.

Validates TASK-005: JWT tokens MUST NOT be accepted via URL query strings
(which leak through browser history, proxy logs, and referer headers).
They MUST be accepted via the WebSocket `Sec-WebSocket-Protocol` header
using the `Bearer.<jwt>` convention.
"""

from django.test import TestCase, override_settings
from rest_framework_simplejwt.tokens import AccessToken
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator

from apps.notifications.middleware import (
    JWTAuthMiddleware,
    BEARER_PREFIX,
    get_user_from_token,
)
from apps.notifications.routing import websocket_urlpatterns
from apps.tenants.models import Tenant
from apps.users.models import User


@override_settings(ALLOWED_HOSTS=["*"])
class WebSocketJWTSubprotocolAuthTests(TestCase):
    """Token must be read from subprotocols, never from the query string."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(
            name="WS Test School",
            slug="ws-test",
            subdomain="ws-test",
            email="ws@test.com",
            is_active=True,
        )
        cls.teacher = User.objects.create_user(
            email="ws-teach@test.com",
            password="testpass123",
            first_name="W",
            last_name="S",
            tenant=cls.tenant,
            role="TEACHER",
        )
        cls.access_token = str(AccessToken.for_user(cls.teacher))

    # ---------- Helpers ----------

    async def _call_middleware_with_subprotocols(self, subprotocols):
        """Invoke JWTAuthMiddleware synchronously and capture the scope it produces."""
        captured = {}

        async def inner_app(scope, receive, send):
            captured["scope"] = scope

        middleware = JWTAuthMiddleware(inner_app)

        scope = {
            "type": "websocket",
            "path": "/ws/notifications/",
            "query_string": b"",
            "headers": [],
            "subprotocols": subprotocols,
        }

        async def receive():
            return {"type": "websocket.connect"}

        async def send(message):
            return None

        await middleware(scope, receive, send)
        return captured["scope"]

    # ---------- Token validator ----------

    def test_get_user_from_valid_token_returns_user(self):
        user = async_to_sync(get_user_from_token)(self.access_token)
        self.assertEqual(user.id, self.teacher.id)
        self.assertTrue(user.is_authenticated)

    def test_get_user_from_invalid_token_returns_anonymous(self):
        user = async_to_sync(get_user_from_token)("not-a-real-jwt")
        self.assertFalse(user.is_authenticated)

    # ---------- Middleware behaviour ----------

    def test_middleware_accepts_bearer_subprotocol(self):
        subprotocol = f"{BEARER_PREFIX}{self.access_token}"
        scope = async_to_sync(self._call_middleware_with_subprotocols)([subprotocol])

        self.assertTrue(scope["user"].is_authenticated)
        self.assertEqual(scope["user"].id, self.teacher.id)
        # Middleware must echo the chosen subprotocol so the consumer can
        # accept it — WebSocket spec requires the handshake to confirm it.
        self.assertEqual(scope["accepted_subprotocol"], subprotocol)

    def test_middleware_ignores_non_bearer_subprotocol(self):
        scope = async_to_sync(self._call_middleware_with_subprotocols)(["chat.v1"])
        self.assertFalse(scope["user"].is_authenticated)
        self.assertIsNone(scope["accepted_subprotocol"])

    def test_middleware_rejects_invalid_bearer_token(self):
        scope = async_to_sync(self._call_middleware_with_subprotocols)(
            [f"{BEARER_PREFIX}garbage-token"]
        )
        self.assertFalse(scope["user"].is_authenticated)

    def test_middleware_does_not_read_query_string_token(self):
        """Regression guard: tokens in query strings must be ignored."""
        captured = {}

        async def inner_app(scope, receive, send):
            captured["scope"] = scope

        middleware = JWTAuthMiddleware(inner_app)

        scope = {
            "type": "websocket",
            "path": "/ws/notifications/",
            "query_string": f"token={self.access_token}".encode(),
            "headers": [],
            "subprotocols": [],
        }

        async def receive():
            return {"type": "websocket.connect"}

        async def send(message):
            return None

        async_to_sync(middleware)(scope, receive, send)

        self.assertFalse(captured["scope"]["user"].is_authenticated)
        self.assertIsNone(captured["scope"]["accepted_subprotocol"])

    # ---------- Full consumer handshake ----------

    def test_consumer_connects_with_valid_bearer_subprotocol(self):
        subprotocol = f"{BEARER_PREFIX}{self.access_token}"

        async def run():
            app = JWTAuthMiddleware(
                __import__(
                    "channels.routing", fromlist=["URLRouter"]
                ).URLRouter(websocket_urlpatterns)
            )
            communicator = WebsocketCommunicator(
                app, "/ws/notifications/", subprotocols=[subprotocol]
            )
            connected, returned_subprotocol = await communicator.connect()
            await communicator.disconnect()
            return connected, returned_subprotocol

        connected, returned_subprotocol = async_to_sync(run)()
        self.assertTrue(connected)
        # Server must echo the Bearer.<jwt> subprotocol back for the
        # browser to accept the handshake.
        self.assertEqual(returned_subprotocol, subprotocol)

    def test_consumer_rejects_missing_subprotocol(self):
        async def run():
            app = JWTAuthMiddleware(
                __import__(
                    "channels.routing", fromlist=["URLRouter"]
                ).URLRouter(websocket_urlpatterns)
            )
            communicator = WebsocketCommunicator(app, "/ws/notifications/")
            result = await communicator.connect()
            await communicator.disconnect()
            return result

        connected, close_code = async_to_sync(run)()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4001)
