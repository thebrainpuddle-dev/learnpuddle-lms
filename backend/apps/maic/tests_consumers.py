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


# ── MAIC-110.3: session-state container ────────────────────────────────


@pytest.mark.asyncio
async def test_safe_send_json_short_circuits_when_writer_dead():
    """A send attempt with `_writer_alive=False` returns False without
    touching the underlying transport. This is the guard MAIC-110.4's
    interrupt handler relies on — between cancel() and the next yield,
    we never push another frame onto a dead socket."""
    from apps.maic.consumers import ClassroomConsumer

    consumer = ClassroomConsumer()
    consumer._writer_alive = False
    sent: list = []

    async def _capture(payload):
        sent.append(payload)

    consumer.send_json = _capture  # type: ignore[assignment]
    result = await consumer._safe_send_json({"type": "x"})
    assert result is False
    assert sent == []


@pytest.mark.asyncio
async def test_safe_send_json_passes_through_when_alive():
    from apps.maic.consumers import ClassroomConsumer

    consumer = ClassroomConsumer()
    consumer._writer_alive = True
    sent: list = []

    async def _capture(payload):
        sent.append(payload)

    consumer.send_json = _capture  # type: ignore[assignment]
    result = await consumer._safe_send_json({"type": "agent_start"})
    assert result is True
    assert sent == [{"type": "agent_start"}]


@pytest.mark.asyncio
async def test_safe_send_json_marks_writer_dead_on_send_failure():
    """When the underlying transport raises (socket already torn down),
    the guard flips `_writer_alive` to False so subsequent calls
    short-circuit instead of raising again."""
    from apps.maic.consumers import ClassroomConsumer

    consumer = ClassroomConsumer()
    consumer._writer_alive = True

    async def _boom(_payload):
        raise ConnectionResetError("transport gone")

    consumer.send_json = _boom  # type: ignore[assignment]
    result = await consumer._safe_send_json({"type": "x"})
    assert result is False
    assert consumer._writer_alive is False


@pytest.mark.asyncio
async def test_cancel_in_flight_is_idempotent_with_no_task():
    """Defensive: calling _cancel_in_flight when no task has been
    spawned (e.g. disconnect before any `start`) is a no-op."""
    from apps.maic.consumers import ClassroomConsumer

    consumer = ClassroomConsumer()
    consumer._classroom_task = None
    await consumer._cancel_in_flight()  # must not raise


@pytest.mark.asyncio
async def test_cancel_in_flight_cancels_running_task():
    """A running task must be cancelled and awaited to completion so
    subsequent `start` calls don't race with its teardown."""
    import asyncio
    from apps.maic.consumers import ClassroomConsumer

    consumer = ClassroomConsumer()

    async def _slow():
        await asyncio.sleep(10)

    consumer._classroom_task = asyncio.create_task(_slow())
    await asyncio.sleep(0)  # let task start
    await consumer._cancel_in_flight()
    assert consumer._classroom_task.done()
    assert consumer._classroom_task.cancelled()


@pytest.mark.asyncio
async def test_cancel_in_flight_skips_already_completed_task():
    """If the task has already finished naturally (e.g. stream drained),
    cancel is a no-op — we don't want to swallow its result by
    re-cancelling a done task."""
    import asyncio
    from apps.maic.consumers import ClassroomConsumer

    consumer = ClassroomConsumer()

    async def _quick():
        return None

    consumer._classroom_task = asyncio.create_task(_quick())
    await consumer._classroom_task  # wait for natural completion
    await consumer._cancel_in_flight()  # must not raise
    assert consumer._classroom_task.done()
    assert not consumer._classroom_task.cancelled()


@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["*"])
async def test_start_action_spawns_tracked_task_and_records_state(monkeypatch):
    """End-to-end: a `start` frame on a connected WS spawns the stream
    as an asyncio.Task tracked on the consumer, and stashes the
    initial OrchestratorState. Both are required for MAIC-110.4's
    interrupt + 110.5's resume to know what to cancel and what to
    restart from.

    Uses the same JWT/tenant monkeypatch pattern as the tenant-gate
    happy-path test above, plus a stub of stream_classroom that yields
    one frame and then sleeps so the test can observe the in-flight
    task before it completes.
    """
    import asyncio
    from types import SimpleNamespace

    async def _fake_call(self, scope, receive, send):
        scope["user"] = SimpleNamespace(
            is_anonymous=False, id=42, tenant_id=222,
        )
        scope["accepted_subprotocol"] = None
        return await self.inner(scope, receive, send)

    from apps.notifications.middleware import JWTAuthMiddleware
    monkeypatch.setattr(JWTAuthMiddleware, "__call__", _fake_call)

    async def _fake_resolve(session_id, user):
        return SimpleNamespace(id=session_id, tenant_id=user.tenant_id), False

    monkeypatch.setattr(
        "apps.maic.consumers._resolve_or_create_session", _fake_resolve,
    )

    # Stub stream_classroom so the test doesn't depend on the full
    # LangGraph + edge_tts pipeline. We yield one frame then await
    # forever so the task stays in-flight while we assert.
    async def _fake_stream(initial_state):
        yield {"type": "agent_start", "data": {"agentId": "default-1"}}
        await asyncio.sleep(60)  # simulates a long stream

    monkeypatch.setattr(
        "apps.maic.orchestration.director_graph.stream_classroom",
        _fake_stream,
    )

    import importlib
    from config import asgi as asgi_mod
    importlib.reload(asgi_mod)

    communicator = WebsocketCommunicator(
        asgi_mod.application,
        "/ws/maic/v2/classroom/start-task-test/",
    )
    connected, _ = await communicator.connect()
    assert connected is True

    await communicator.send_json_to({
        "action": "start",
        "data": {"agentIds": ["default-1"], "maxTurns": 1},
    })

    # The stub yields one frame; receive it to confirm the task is live.
    frame = await communicator.receive_json_from(timeout=2)
    assert frame == {"type": "agent_start", "data": {"agentId": "default-1"}}

    # Disconnect cancels the in-flight asyncio.Task — if the cancel
    # path were broken, this would hang past the 2s timeout.
    await communicator.disconnect()


# ── MAIC-110.4: interrupt + stop action handlers ──────────────────────


def _make_long_stream_monkeypatches(monkeypatch, *, frames: list[dict] | None = None):
    """Shared monkeypatch helper for 110.4 / 110.5 tests.

    Stubs JWTAuthMiddleware to inject a synthetic same-tenant user,
    `_resolve_or_create_session` to return a same-tenant session, and
    `stream_classroom` to yield the given frames then sleep forever
    (so the test can interrupt at any event-type boundary).
    """
    from types import SimpleNamespace
    import asyncio

    async def _fake_call(self, scope, receive, send):
        scope["user"] = SimpleNamespace(
            is_anonymous=False, id=42, tenant_id=222,
        )
        scope["accepted_subprotocol"] = None
        return await self.inner(scope, receive, send)

    from apps.notifications.middleware import JWTAuthMiddleware
    monkeypatch.setattr(JWTAuthMiddleware, "__call__", _fake_call)

    async def _fake_resolve(session_id, user):
        return SimpleNamespace(id=session_id, tenant_id=user.tenant_id), False

    monkeypatch.setattr(
        "apps.maic.consumers._resolve_or_create_session", _fake_resolve,
    )

    frames = frames or [
        {"type": "agent_start", "data": {"agentId": "default-1"}},
    ]

    async def _fake_stream(initial_state):
        for frame in frames:
            yield frame
        await asyncio.sleep(60)  # stays in-flight for the test to interrupt

    monkeypatch.setattr(
        "apps.maic.orchestration.director_graph.stream_classroom",
        _fake_stream,
    )


@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["*"])
async def test_interrupt_cancels_in_flight_stream_without_terminal_frame(monkeypatch):
    """`interrupt` must cancel the running task AND keep the connection
    open without sending any terminal frame — the next user_message /
    resume frame is what tells the client we heard them.

    If the writer-guard pattern is broken, an `interrupt` landing
    between two stream frames could either hang or push a frame onto
    a half-cancelled task. Either failure shows up here."""
    import asyncio
    _make_long_stream_monkeypatches(monkeypatch)

    import importlib
    from config import asgi as asgi_mod
    importlib.reload(asgi_mod)

    communicator = WebsocketCommunicator(
        asgi_mod.application, "/ws/maic/v2/classroom/interrupt-test/",
    )
    connected, _ = await communicator.connect()
    assert connected is True

    await communicator.send_json_to({
        "action": "start",
        "data": {"agentIds": ["default-1"], "maxTurns": 1},
    })
    # Drain the stub's first frame so we know the task is live
    first = await communicator.receive_json_from(timeout=2)
    assert first["type"] == "agent_start"

    # Now interrupt — must NOT emit a terminal frame
    await communicator.send_json_to({"action": "interrupt"})

    # Give the cancel a tick to land
    await asyncio.sleep(0.05)

    # Confirm no frame was emitted by the interrupt
    nothing = await communicator.receive_nothing(timeout=0.2)
    assert nothing is True, "interrupt must NOT send a terminal frame"

    await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["*"])
async def test_stop_cancels_and_emits_cue_user_ack(monkeypatch):
    """`stop` must cancel the stream AND emit a single `cue_user` ack
    so the client knows control has returned to the user. Connection
    stays open."""
    _make_long_stream_monkeypatches(monkeypatch)

    import importlib
    from config import asgi as asgi_mod
    importlib.reload(asgi_mod)

    communicator = WebsocketCommunicator(
        asgi_mod.application, "/ws/maic/v2/classroom/stop-test/",
    )
    connected, _ = await communicator.connect()
    assert connected is True

    await communicator.send_json_to({
        "action": "start",
        "data": {"agentIds": ["default-1"], "maxTurns": 1},
    })
    first = await communicator.receive_json_from(timeout=2)
    assert first["type"] == "agent_start"

    await communicator.send_json_to({"action": "stop"})

    # The stop ack arrives next — `cue_user` with reason
    ack = await communicator.receive_json_from(timeout=2)
    assert ack["type"] == "cue_user"
    assert ack["data"].get("reason") == "stopped_by_user"

    await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["*"])
async def test_interrupt_without_in_flight_task_is_idempotent(monkeypatch):
    """Defensive: an `interrupt` arriving when no stream is running
    (e.g. the user clicked the interrupt button after the natural
    end of a classroom) must be a no-op, not raise."""
    _make_long_stream_monkeypatches(monkeypatch)

    import importlib
    from config import asgi as asgi_mod
    importlib.reload(asgi_mod)

    communicator = WebsocketCommunicator(
        asgi_mod.application, "/ws/maic/v2/classroom/interrupt-noop/",
    )
    connected, _ = await communicator.connect()
    assert connected is True

    # No prior `start` — interrupt arrives cold
    await communicator.send_json_to({"action": "interrupt"})

    nothing = await communicator.receive_nothing(timeout=0.2)
    assert nothing is True

    await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["*"])
async def test_stop_without_in_flight_task_still_emits_ack(monkeypatch):
    """A `stop` against an idle connection still emits the cue_user
    ack — the contract is "after stop, client knows control is back",
    regardless of whether anything was running."""
    _make_long_stream_monkeypatches(monkeypatch)

    import importlib
    from config import asgi as asgi_mod
    importlib.reload(asgi_mod)

    communicator = WebsocketCommunicator(
        asgi_mod.application, "/ws/maic/v2/classroom/stop-cold/",
    )
    connected, _ = await communicator.connect()
    assert connected is True

    await communicator.send_json_to({"action": "stop"})
    ack = await communicator.receive_json_from(timeout=2)
    assert ack["type"] == "cue_user"
    assert ack["data"].get("reason") == "stopped_by_user"

    await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["*"])
@pytest.mark.parametrize("event_type", [
    "agent_start", "text_delta", "action", "agent_end",
    "thinking", "speech_audio",
])
async def test_interrupt_safe_at_every_event_boundary(monkeypatch, event_type):
    """Highest-risk regression net for MAIC-110.4: interrupt the stream
    immediately after each of the 8 StatelessEvent types and verify
    the connection survives + no terminal frame leaks.

    The writer-guard race window is exactly between
    `_safe_send_json(frame)` and the next `async for` yield — this
    parametrize covers every realistic frame shape that could be
    in-flight when interrupt arrives."""
    import asyncio

    frame_data: dict[str, dict] = {
        "agent_start": {"agentId": "default-1"},
        "text_delta": {"agentId": "default-1", "delta": "hi"},
        "action": {"agentId": "default-1", "actionName": "wb_open", "params": {}},
        "agent_end": {"agentId": "default-1"},
        "thinking": {"agentId": "default-1"},
        "speech_audio": {
            "agentId": "default-1", "audioUrl": "x", "duration": 1.0,
        },
    }
    frame = {"type": event_type, "data": frame_data[event_type]}
    _make_long_stream_monkeypatches(monkeypatch, frames=[frame])

    import importlib
    from config import asgi as asgi_mod
    importlib.reload(asgi_mod)

    communicator = WebsocketCommunicator(
        asgi_mod.application,
        f"/ws/maic/v2/classroom/interrupt-{event_type}/",
    )
    connected, _ = await communicator.connect()
    assert connected is True

    await communicator.send_json_to({
        "action": "start",
        "data": {"agentIds": ["default-1"], "maxTurns": 1},
    })
    received = await communicator.receive_json_from(timeout=2)
    assert received["type"] == event_type

    await communicator.send_json_to({"action": "interrupt"})
    await asyncio.sleep(0.05)

    # No terminal frame, no error
    nothing = await communicator.receive_nothing(timeout=0.2)
    assert nothing is True, (
        f"interrupt after {event_type} leaked a frame — writer guard race"
    )

    await communicator.disconnect()
