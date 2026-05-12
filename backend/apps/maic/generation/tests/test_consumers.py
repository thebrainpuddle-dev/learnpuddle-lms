"""Tests for `apps.maic.generation.consumers` (MAIC-428.3).

Mirrors the pattern in apps/maic/tests_consumers.py: connection-level
rejection paths use WebsocketCommunicator; pure-shape tests bypass the
WS handshake entirely.

The full DB-backed connect flow (auth + tenant gate + hydrate event)
needs a working test DB, which the V1 migration freeze blocks unless
the test runner uses `--no-migrations --create-db` (the same gate the
new MAIC-428.1 tasks tests ride on). See test_tasks.py provenance
for the invocation recipe.
"""
from __future__ import annotations

import pytest
from channels.testing import WebsocketCommunicator
from django.test import override_settings


@pytest.fixture(autouse=True)
def _allow_maic_v2_ws_access(monkeypatch):
    async def _allow(_user):
        return True

    monkeypatch.setattr(
        "apps.maic.generation.consumers._user_has_maic_v2_access",
        _allow,
    )


# ── Static / shape tests (no DB) ──────────────────────────────────


def test_consumer_module_exports_generation_consumer():
    from apps.maic.generation.consumers import GenerationConsumer
    from channels.generic.websocket import AsyncJsonWebsocketConsumer
    assert issubclass(GenerationConsumer, AsyncJsonWebsocketConsumer)


def test_routing_includes_generation_route():
    """`/ws/maic/generation/<job_id>/` must be reachable. Lock the
    pattern shape so a future routing edit doesn't accidentally drop
    the generation consumer."""
    from apps.maic.routing import websocket_urlpatterns

    paths = [p.pattern.regex.pattern for p in websocket_urlpatterns]
    assert any("ws/maic/generation" in p for p in paths), (
        f"generation route missing; got {paths}"
    )


def test_job_id_regex_bounds():
    """Path regex caps job_id at 64 chars + word/hyphen only."""
    import re
    from apps.maic.routing import websocket_urlpatterns

    # Find the generation route's compiled regex.
    gen_pattern = next(
        p for p in websocket_urlpatterns
        if "generation" in p.pattern.regex.pattern
    ).pattern.regex

    def _matches(job_id: str) -> bool:
        return bool(gen_pattern.search(f"ws/maic/generation/{job_id}/"))

    assert _matches("a")
    assert _matches("x" * 64)
    assert _matches("job-with-hyphens_123")
    assert not _matches("")
    assert not _matches("x" * 65)
    assert not _matches("bad space")


# ── Connection rejection paths ────────────────────────────────────


@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["*"])
async def test_anonymous_connection_rejected_with_4001():
    """No Bearer subprotocol → AnonymousUser → 4001 close."""
    from config.asgi import application

    communicator = WebsocketCommunicator(
        application,
        "/ws/maic/generation/some-job-id/",
    )
    connected, code = await communicator.connect()

    assert connected is False
    assert code == 4001


@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["*"])
async def test_tenant_v2_gate_rejected_with_4403(monkeypatch):
    """The generation progress socket must honor the same v2 gate as
    the HTTP enqueue view before revealing job existence."""
    from types import SimpleNamespace

    async def _fake_call(self, scope, receive, send):
        scope["user"] = SimpleNamespace(
            is_anonymous=False, id=42, tenant_id=222,
        )
        scope["accepted_subprotocol"] = None
        return await self.inner(scope, receive, send)

    from apps.notifications.middleware import JWTAuthMiddleware
    monkeypatch.setattr(JWTAuthMiddleware, "__call__", _fake_call)

    async def _deny(_user):
        return False

    monkeypatch.setattr(
        "apps.maic.generation.consumers._user_has_maic_v2_access",
        _deny,
    )

    import importlib
    from config import asgi as asgi_mod
    importlib.reload(asgi_mod)

    communicator = WebsocketCommunicator(
        asgi_mod.application,
        "/ws/maic/generation/some-job-id/",
    )
    connected, code = await communicator.connect()

    assert connected is False
    assert code == 4403


# ── Channel-layer message handling (in-memory layer) ──────────────


@pytest.mark.asyncio
async def test_generation_progress_message_forwarded_to_client(monkeypatch):
    """The `generation.progress` channel-layer message lands on the
    generation_progress() handler and gets forwarded to the connected
    client as a `{event, payload}` JSON frame.

    This isolates the consumer's group-message dispatch from the full
    auth/connect flow — we instantiate the consumer directly, mock its
    send_json, and call generation_progress() with a sample payload.
    """
    from apps.maic.generation.consumers import GenerationConsumer

    consumer = GenerationConsumer()
    sent: list[dict] = []

    async def _capture(payload):
        sent.append(payload)

    consumer.send_json = _capture
    await consumer.generation_progress({
        "type": "generation.progress",
        "event": "scene_done",
        "payload": {"completed": 4, "total": 10},
    })

    assert sent == [
        {"event": "scene_done", "payload": {"completed": 4, "total": 10}},
    ]


@pytest.mark.asyncio
async def test_receive_json_ignores_client_messages():
    """Phase 4 the consumer is read-only — receive_json() must NOT
    raise on incoming messages, just log and ignore."""
    from apps.maic.generation.consumers import GenerationConsumer

    consumer = GenerationConsumer()
    # Should not raise
    await consumer.receive_json({"type": "anything", "payload": {}})
