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


# ── MAIC-101: tenant-gate tests (mock the DB helper) ───────────────────


@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["*"])
async def test_no_tenant_id_user_rejected_with_4004(monkeypatch):
    """Authenticated user with tenant_id=None (corrupt-state scenario) is
    rejected with close code 4004 — distinct from anonymous (4001) and
    cross-tenant (4003) so we can monitor each path separately."""
    from types import SimpleNamespace

    # Patch the JWT auth middleware to inject a synthetic user
    async def _fake_call(self, scope, receive, send):
        scope["user"] = SimpleNamespace(
            is_anonymous=False, id=999, tenant_id=None,
        )
        scope["accepted_subprotocol"] = None
        return await self.inner(scope, receive, send)

    from apps.notifications.middleware import JWTAuthMiddleware
    monkeypatch.setattr(JWTAuthMiddleware, "__call__", _fake_call)

    # Re-import application after patch so middleware change takes effect
    import importlib
    from config import asgi as asgi_mod
    importlib.reload(asgi_mod)

    communicator = WebsocketCommunicator(
        asgi_mod.application, "/ws/maic/v2/classroom/no-tenant-test/",
    )
    connected, code = await communicator.connect()
    assert connected is False
    assert code == 4004


@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["*"])
async def test_cross_tenant_session_rejected_with_4003(monkeypatch):
    """Session exists for tenant A; user from tenant B connects → 4003.
    Mocks _resolve_or_create_session to simulate the tenant mismatch
    (avoids pytest-django test-DB build which fails on a pre-existing
    repo migration issue, see MAIC-002 cert)."""
    from types import SimpleNamespace

    async def _fake_call(self, scope, receive, send):
        scope["user"] = SimpleNamespace(
            is_anonymous=False, id=42, tenant_id=999,  # user is tenant 999
        )
        scope["accepted_subprotocol"] = None
        return await self.inner(scope, receive, send)

    from apps.notifications.middleware import JWTAuthMiddleware
    monkeypatch.setattr(JWTAuthMiddleware, "__call__", _fake_call)

    # Mock the helper to return cross_tenant=True
    async def _fake_resolve(session_id, user):
        return SimpleNamespace(id=session_id, tenant_id=111), True

    monkeypatch.setattr(
        "apps.maic.consumers._resolve_or_create_session", _fake_resolve,
    )

    import importlib
    from config import asgi as asgi_mod
    importlib.reload(asgi_mod)

    communicator = WebsocketCommunicator(
        asgi_mod.application, "/ws/maic/v2/classroom/cross-tenant-test/",
    )
    connected, code = await communicator.connect()
    assert connected is False
    assert code == 4003


@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["*"])
async def test_authenticated_same_tenant_connects_successfully(monkeypatch):
    """Same-tenant happy path — user's tenant matches session's tenant
    (or session is created on the fly), connection accepts."""
    from types import SimpleNamespace

    async def _fake_call(self, scope, receive, send):
        scope["user"] = SimpleNamespace(
            is_anonymous=False, id=42, tenant_id=222,
        )
        scope["accepted_subprotocol"] = "Bearer.fake-token"
        return await self.inner(scope, receive, send)

    from apps.notifications.middleware import JWTAuthMiddleware
    monkeypatch.setattr(JWTAuthMiddleware, "__call__", _fake_call)

    async def _fake_resolve(session_id, user):
        # Same-tenant — return a session with matching tenant
        return SimpleNamespace(id=session_id, tenant_id=user.tenant_id), False

    monkeypatch.setattr(
        "apps.maic.consumers._resolve_or_create_session", _fake_resolve,
    )

    import importlib
    from config import asgi as asgi_mod
    importlib.reload(asgi_mod)

    communicator = WebsocketCommunicator(
        asgi_mod.application,
        "/ws/maic/v2/classroom/happy-path-test/",
        subprotocols=["Bearer.fake", "Bearer"],
    )
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.disconnect()
