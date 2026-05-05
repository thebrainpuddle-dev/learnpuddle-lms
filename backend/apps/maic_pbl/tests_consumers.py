"""WebSocket tests for PBLChatConsumer (MAIC-704).

Patterns mirror apps.maic.tests_consumers — JWT subprotocol auth,
middleware monkeypatch for synthetic users, channels.testing
WebsocketCommunicator. Pure-helper tests (regex, prompt assembly,
agent resolution) live alongside so a fast pytest pass covers both
HTTP-boundary and unit-level surface in a single run.
"""
from __future__ import annotations

import importlib

import pytest
from channels.testing import WebsocketCommunicator
from django.test import override_settings


# ── Pure unit tests (no DB, no env-var prerequisite) ───────────────────


def test_consumer_module_exports():
    """Pure-import test — catches ImportError before anything else."""
    from apps.maic_pbl.consumers import PBLChatConsumer
    from channels.generic.websocket import AsyncJsonWebsocketConsumer

    assert PBLChatConsumer is not None
    assert issubclass(PBLChatConsumer, AsyncJsonWebsocketConsumer)


def test_routing_publishes_pbl_pattern():
    from apps.maic_pbl.routing import websocket_urlpatterns

    assert len(websocket_urlpatterns) == 1
    assert "ws/maic/pbl" in str(websocket_urlpatterns[0].pattern)


def test_session_id_regex_bounds():
    """Path regex caps session_id at 64 chars, rejects empty + slashes."""
    from apps.maic_pbl.routing import websocket_urlpatterns

    pattern = websocket_urlpatterns[0].pattern.regex

    def _matches(session_id: str) -> bool:
        return bool(pattern.search(f"ws/maic/pbl/{session_id}/"))

    assert _matches("a")
    assert _matches("x" * 64)
    assert _matches("uuid-with-hyphens_abc")
    assert not _matches("")
    assert not _matches("x" * 65)
    assert not _matches("bad space")
    assert not _matches("bad/slash")


def test_mention_regex_picks_judge_or_question_case_insensitive():
    from apps.maic_pbl.consumers import _MENTION_RE

    assert _MENTION_RE.search("@question hello").group(1).lower() == "question"
    assert _MENTION_RE.search("@JUDGE rate this").group(1).lower() == "judge"
    assert _MENTION_RE.search("@Question mixed").group(1).lower() == "question"
    assert _MENTION_RE.search("hello world") is None
    # Word-boundary: @questions (plural) should NOT match — \b after 'question'
    assert _MENTION_RE.search("@questionnaire long word") is None


def test_resolve_target_agent_default_to_question_no_mention():
    from apps.maic_pbl.consumers import _resolve_target_agent

    config = {
        "agents": [
            {"name": "Q1", "system_prompt": "q"},
            {"name": "J1", "system_prompt": "j"},
        ],
        "issueboard": {
            "issues": [{
                "id": "issue-1",
                "is_active": True,
                "question_agent_name": "Q1",
                "judge_agent_name": "J1",
            }],
        },
    }
    agent, kind = _resolve_target_agent(config, "what should I do?")
    assert kind == "question"
    assert agent["name"] == "Q1"


def test_resolve_target_agent_picks_judge_on_mention():
    from apps.maic_pbl.consumers import _resolve_target_agent

    config = {
        "agents": [
            {"name": "Q1", "system_prompt": "q"},
            {"name": "J1", "system_prompt": "j"},
        ],
        "issueboard": {
            "issues": [{
                "id": "issue-1",
                "is_active": True,
                "question_agent_name": "Q1",
                "judge_agent_name": "J1",
            }],
        },
    }
    agent, kind = _resolve_target_agent(config, "@judge please rate")
    assert kind == "judge"
    assert agent["name"] == "J1"


def test_resolve_target_agent_returns_none_when_no_active_issue():
    from apps.maic_pbl.consumers import _resolve_target_agent

    config = {"agents": [], "issueboard": {"issues": []}}
    agent, kind = _resolve_target_agent(config, "anything")
    assert agent is None
    assert kind == ""


def test_resolve_target_agent_returns_none_when_target_name_missing():
    """Active issue exists but its question_agent_name is empty —
    config drift; consumer must surface error not crash."""
    from apps.maic_pbl.consumers import _resolve_target_agent

    config = {
        "agents": [{"name": "Q1", "system_prompt": "q"}],
        "issueboard": {
            "issues": [{
                "id": "issue-1",
                "is_active": True,
                "question_agent_name": "",  # drift
                "judge_agent_name": "",
            }],
        },
    }
    agent, kind = _resolve_target_agent(config, "hello")
    assert agent is None
    assert kind == "question"


def test_build_chat_system_prompt_assembles_all_sections():
    from apps.maic_pbl.consumers import _build_chat_system_prompt

    agent = {"name": "Q1", "system_prompt": "BASE_PROMPT"}
    config = {
        "issueboard": {
            "issues": [{
                "id": "i1",
                "is_active": True,
                "title": "Build the thing",
                "description": "do it",
                "person_in_charge": "Dev",
                "generated_questions": "Q1\nQ2",
            }],
        },
        "chat": {
            "messages": [
                {"agent_name": "user", "message": "hi"},
                {"agent_name": "Q1", "message": "hello"},
            ],
        },
    }
    out = _build_chat_system_prompt(agent, config, "Designer", "question")
    assert out.startswith("BASE_PROMPT")
    assert "Build the thing" in out
    assert "Generated Questions" in out  # question label, not judge
    assert "Q1: hello" in out  # recent conversation formatted
    assert "student's role is: Designer" in out


def test_build_chat_system_prompt_judge_uses_evaluation_label():
    from apps.maic_pbl.consumers import _build_chat_system_prompt

    agent = {"name": "J1", "system_prompt": "JUDGE_PROMPT"}
    config = {
        "issueboard": {
            "issues": [{
                "is_active": True,
                "title": "T",
                "description": "D",
                "person_in_charge": "Dev",
                "generated_questions": "Q?",
            }],
        },
    }
    out = _build_chat_system_prompt(agent, config, "", "judge")
    assert "Questions to Evaluate Against" in out
    assert "Generated Questions" not in out  # judge label, not question


def test_build_chat_system_prompt_no_active_issue_just_returns_base():
    from apps.maic_pbl.consumers import _build_chat_system_prompt

    agent = {"name": "Q1", "system_prompt": "ONLY_BASE"}
    config = {"issueboard": {"issues": []}, "chat": {"messages": []}}
    out = _build_chat_system_prompt(agent, config, "", "question")
    assert out == "ONLY_BASE"


# ── HTTP-boundary tests (require ASGI app + middleware monkeypatch) ────


@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["*"])
async def test_anonymous_connection_rejected_with_4001():
    """No JWT → AnonymousUser → consumer closes with 4001."""
    from config.asgi import application

    communicator = WebsocketCommunicator(
        application, "/ws/maic/pbl/some-session/",
    )
    connected, code = await communicator.connect()
    assert connected is False
    assert code == 4001


@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["*"])
async def test_no_tenant_user_rejected_with_4040(monkeypatch):
    """Authenticated user with tenant_id=None → 4040 (corrupt-state)."""
    from types import SimpleNamespace

    async def _fake_call(self, scope, receive, send):
        scope["user"] = SimpleNamespace(
            is_anonymous=False, id=999, tenant_id=None,
        )
        scope["accepted_subprotocol"] = None
        return await self.inner(scope, receive, send)

    from apps.notifications.middleware import JWTAuthMiddleware
    monkeypatch.setattr(JWTAuthMiddleware, "__call__", _fake_call)

    from config import asgi as asgi_mod
    importlib.reload(asgi_mod)

    communicator = WebsocketCommunicator(
        asgi_mod.application, "/ws/maic/pbl/no-tenant-test/",
    )
    connected, code = await communicator.connect()
    assert connected is False
    assert code == 4040


@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["*"])
async def test_session_not_found_rejected_with_4004(monkeypatch):
    """Authenticated, has tenant, but session row doesn't exist → 4004."""
    from types import SimpleNamespace

    async def _fake_call(self, scope, receive, send):
        scope["user"] = SimpleNamespace(
            is_anonymous=False, id=42, tenant_id=222,
        )
        scope["accepted_subprotocol"] = None
        return await self.inner(scope, receive, send)

    from apps.notifications.middleware import JWTAuthMiddleware
    monkeypatch.setattr(JWTAuthMiddleware, "__call__", _fake_call)

    async def _fake_load(session_id, user):
        return None, 4004

    monkeypatch.setattr(
        "apps.maic_pbl.consumers._load_session", _fake_load,
    )

    from config import asgi as asgi_mod
    importlib.reload(asgi_mod)

    communicator = WebsocketCommunicator(
        asgi_mod.application, "/ws/maic/pbl/missing-session/",
    )
    connected, code = await communicator.connect()
    assert connected is False
    assert code == 4004


@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["*"])
async def test_cross_tenant_session_rejected_with_4003(monkeypatch):
    """Session belongs to tenant A, user is tenant B → 4003."""
    from types import SimpleNamespace

    async def _fake_call(self, scope, receive, send):
        scope["user"] = SimpleNamespace(
            is_anonymous=False, id=42, tenant_id=999,
        )
        scope["accepted_subprotocol"] = None
        return await self.inner(scope, receive, send)

    from apps.notifications.middleware import JWTAuthMiddleware
    monkeypatch.setattr(JWTAuthMiddleware, "__call__", _fake_call)

    async def _fake_load(session_id, user):
        # Session is tenant 111, user is 999
        return SimpleNamespace(id=session_id, tenant_id=111), 4003

    monkeypatch.setattr(
        "apps.maic_pbl.consumers._load_session", _fake_load,
    )

    from config import asgi as asgi_mod
    importlib.reload(asgi_mod)

    communicator = WebsocketCommunicator(
        asgi_mod.application, "/ws/maic/pbl/cross-tenant-test/",
    )
    connected, code = await communicator.connect()
    assert connected is False
    assert code == 4003


@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["*"])
async def test_authenticated_same_tenant_connects_successfully(monkeypatch):
    """Same-tenant happy path → connection accepted."""
    from types import SimpleNamespace

    async def _fake_call(self, scope, receive, send):
        scope["user"] = SimpleNamespace(
            is_anonymous=False, id=42, tenant_id=222,
        )
        scope["accepted_subprotocol"] = "Bearer.fake-token"
        return await self.inner(scope, receive, send)

    from apps.notifications.middleware import JWTAuthMiddleware
    monkeypatch.setattr(JWTAuthMiddleware, "__call__", _fake_call)

    async def _fake_load(session_id, user):
        return (
            SimpleNamespace(
                id=session_id, tenant_id=user.tenant_id, project_config={},
            ),
            0,
        )

    monkeypatch.setattr(
        "apps.maic_pbl.consumers._load_session", _fake_load,
    )

    from config import asgi as asgi_mod
    importlib.reload(asgi_mod)

    communicator = WebsocketCommunicator(
        asgi_mod.application,
        "/ws/maic/pbl/happy-path-test/",
        subprotocols=["Bearer.fake", "Bearer"],
    )
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.disconnect()


# ── Receive-action tests (use the same connect harness) ─────────────────


@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["*"])
async def test_chat_with_empty_message_emits_error(monkeypatch):
    """Empty `data.message` → server returns error frame, no agent_start."""
    from types import SimpleNamespace

    async def _fake_call(self, scope, receive, send):
        scope["user"] = SimpleNamespace(
            is_anonymous=False, id=42, tenant_id=222,
        )
        scope["accepted_subprotocol"] = None
        return await self.inner(scope, receive, send)

    from apps.notifications.middleware import JWTAuthMiddleware
    monkeypatch.setattr(JWTAuthMiddleware, "__call__", _fake_call)

    async def _fake_load(session_id, user):
        return (
            SimpleNamespace(
                id=session_id, tenant_id=user.tenant_id, project_config={},
            ),
            0,
        )

    monkeypatch.setattr(
        "apps.maic_pbl.consumers._load_session", _fake_load,
    )

    from config import asgi as asgi_mod
    importlib.reload(asgi_mod)

    communicator = WebsocketCommunicator(
        asgi_mod.application, "/ws/maic/pbl/empty-msg-test/",
    )
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.send_json_to({"action": "chat", "data": {"message": "   "}})
    frame = await communicator.receive_json_from()
    assert frame["type"] == "error"
    assert "non-empty" in frame["data"]["message"]
    await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["*"])
async def test_unknown_action_emits_error(monkeypatch):
    from types import SimpleNamespace

    async def _fake_call(self, scope, receive, send):
        scope["user"] = SimpleNamespace(
            is_anonymous=False, id=42, tenant_id=222,
        )
        scope["accepted_subprotocol"] = None
        return await self.inner(scope, receive, send)

    from apps.notifications.middleware import JWTAuthMiddleware
    monkeypatch.setattr(JWTAuthMiddleware, "__call__", _fake_call)

    async def _fake_load(session_id, user):
        return (
            SimpleNamespace(
                id=session_id, tenant_id=user.tenant_id, project_config={},
            ),
            0,
        )

    monkeypatch.setattr(
        "apps.maic_pbl.consumers._load_session", _fake_load,
    )

    from config import asgi as asgi_mod
    importlib.reload(asgi_mod)

    communicator = WebsocketCommunicator(
        asgi_mod.application, "/ws/maic/pbl/unknown-action/",
    )
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.send_json_to({"action": "frobnicate"})
    frame = await communicator.receive_json_from()
    assert frame["type"] == "error"
    assert "unknown action" in frame["data"]["message"]
    await communicator.disconnect()
