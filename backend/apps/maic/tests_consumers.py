"""WebSocket consumer tests for MAIC v2.

IMPORTANT: For tests that connect to the MAIC v2 route, the env var
`MAIC_V2_ENABLED=true` MUST be set BEFORE Python imports `config.settings`,
because `config/asgi.py` evaluates the flag once at module import time.
The cert script invokes pytest as `MAIC_V2_ENABLED=true pytest ...` —
`@override_settings(MAIC_V2_ENABLED=True)` does NOT work for the asgi
mount because routing is bound before the override fixture runs.

Auth pattern mirrors `apps/notifications/tests_websocket_auth.py`:
JWT delivered via the `Bearer.<jwt>` subprotocol header. We assert
the consumer rejects anonymous connections at the consumer layer
(close code 4001) — the actual JWT round-trip is exercised manually
in MAIC-003-CERTIFICATION's smoke section because pytest-django's
test-DB build currently fails on a pre-existing repo migration issue
(NewCourseSkipRequest.teacher missing field — see MAIC-002 cert).
"""
from __future__ import annotations

import pytest
from channels.testing import WebsocketCommunicator
from django.test import override_settings


@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["*"])
async def test_anonymous_connection_rejected_with_4001():
    """No Bearer subprotocol → JWTAuthMiddleware sets AnonymousUser →
    consumer closes immediately with code 4001 (mirrors the contract
    used by apps/notifications/consumers.py:46-50)."""
    from config.asgi import application  # imported lazily so env-var check runs in correct order

    communicator = WebsocketCommunicator(
        application,
        "/ws/maic/v2/classroom/test-session/",
    )
    connected, code = await communicator.connect()

    assert connected is False, "anonymous connect should be rejected"
    assert code == 4001, f"expected close code 4001, got {code}"


def test_session_id_regex_bounds():
    """Path regex caps session_id at 64 chars (re_path '[\\w-]{1,64}'),
    rejects empty, accepts hyphens + word chars. Tested directly against
    the compiled pattern rather than via WebsocketCommunicator because
    URLRouter raises ValueError on path miss rather than returning a
    graceful close — that's a channels internal behavior, not ours."""
    import re
    from apps.maic.routing import websocket_urlpatterns

    pattern = websocket_urlpatterns[0].pattern.regex

    # Helper: does a session_id pass when wrapped in the full route path?
    def _matches(session_id: str) -> bool:
        return bool(pattern.search(f"ws/maic/v2/classroom/{session_id}/"))

    assert _matches("a")                         # 1 char — boundary low
    assert _matches("x" * 64)                    # 64 chars — boundary high
    assert _matches("session-with-hyphens_123")  # word + hyphen mix
    assert not _matches("")                      # empty — rejected
    assert not _matches("x" * 65)                # 65 chars — over limit
    assert not _matches("bad space")             # whitespace — rejected
    assert not _matches("bad/slash")             # slash — rejected (would shadow next path segment)


def test_consumer_module_exports_classroom_consumer():
    """Pure-import test — no DB, no env-var prerequisite. Catches import
    errors in the consumer module."""
    from apps.maic.consumers import ClassroomConsumer

    assert ClassroomConsumer is not None
    # AsyncJsonWebsocketConsumer subclass — confirms we picked the right base
    from channels.generic.websocket import AsyncJsonWebsocketConsumer
    assert issubclass(ClassroomConsumer, AsyncJsonWebsocketConsumer)


def test_routing_module_publishes_one_pattern():
    """The routing module should expose exactly one re_path for the V2 route."""
    from apps.maic.routing import websocket_urlpatterns

    assert len(websocket_urlpatterns) == 1
    pattern = websocket_urlpatterns[0]
    # Pattern is a URLPattern; pattern.pattern is a RoutePattern
    assert "ws/maic/v2/classroom" in str(pattern.pattern)
