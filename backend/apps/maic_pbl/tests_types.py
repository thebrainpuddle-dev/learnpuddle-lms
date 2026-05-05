"""Tests for apps.maic_pbl.types (MAIC-701).

Validation tests for the Pydantic port of upstream `lib/pbl/types.ts`.
Mirrors the shape expectations the design loop (MAIC-703) and
MaicPBLSession.project_config persistence rely on.

extra='forbid' across the model set means a hostile or stale payload
gets rejected loudly — these tests pin that policy so future drift
between our Pydantic + upstream TS surfaces is caught at validation
time rather than silently propagating.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.maic_pbl.types import (
    PBLAgent,
    PBLChat,
    PBLChatMessage,
    PBLIssue,
    PBLIssueboard,
    PBLProjectConfig,
    PBLProjectInfo,
    PBLToolResult,
)


# ── Sample fixtures (raw dicts — wire shape) ──────────────────────────


_AGENT_QUESTION: dict = {
    "name": "Question",
    "actor_role": "Question",
    "role_division": "management",
    "system_prompt": "Ask probing questions.",
    "default_mode": "idle",
    "delay_time": 0,
    "env": {},
    "is_user_role": False,
    "is_active": True,
    "is_system_agent": True,
}

_AGENT_DEV_FRONTEND: dict = {
    "name": "Frontend Dev",
    "actor_role": "Frontend Dev",
    "role_division": "development",
    "system_prompt": "Implement the UI.",
    "default_mode": "idle",
    "delay_time": 1500,
    "env": {"file_refs": ["src/App.tsx"]},
    "is_user_role": True,
    "is_active": True,
    "is_system_agent": False,
}

_ISSUE_1: dict = {
    "id": "issue-1",
    "title": "Define API",
    "description": "Sketch the public surface.",
    "person_in_charge": "Frontend Dev",
    "participants": ["Frontend Dev", "Question"],
    "notes": "",
    "parent_issue": None,
    "index": 0,
    "is_done": False,
    "is_active": True,
    "generated_questions": "What endpoints do we need?",
    "question_agent_name": "Question",
    "judge_agent_name": "Judge",
}

_FULL_CONFIG: dict = {
    "projectInfo": {
        "title": "Fraction Calculator",
        "description": "Build a CLI fraction calculator.",
    },
    "agents": [_AGENT_QUESTION, _AGENT_DEV_FRONTEND],
    "issueboard": {
        "agent_ids": ["Question", "Frontend Dev"],
        "issues": [_ISSUE_1],
        "current_issue_id": "issue-1",
    },
    "chat": {"messages": []},
    "selectedRole": None,
}


# ── Happy-path validation ─────────────────────────────────────────────


def test_full_project_config_validates():
    cfg = PBLProjectConfig.model_validate(_FULL_CONFIG)
    assert cfg.projectInfo.title == "Fraction Calculator"
    assert len(cfg.agents) == 2
    assert cfg.issueboard.current_issue_id == "issue-1"
    assert cfg.chat.messages == []
    assert cfg.selectedRole is None


def test_project_info_minimal():
    info = PBLProjectInfo(title="t", description="d")
    assert info.title == "t" and info.description == "d"


def test_agent_management_division():
    agent = PBLAgent.model_validate(_AGENT_QUESTION)
    assert agent.role_division == "management"
    assert agent.is_system_agent is True
    assert agent.delay_time == 0


def test_agent_development_division_with_env():
    agent = PBLAgent.model_validate(_AGENT_DEV_FRONTEND)
    assert agent.role_division == "development"
    assert agent.is_user_role is True
    assert agent.env["file_refs"] == ["src/App.tsx"]


def test_issue_with_parent_issue():
    nested = dict(_ISSUE_1, id="issue-1.1", parent_issue="issue-1", index=1)
    issue = PBLIssue.model_validate(nested)
    assert issue.parent_issue == "issue-1"


def test_issueboard_with_no_active_issue():
    """Valid mid-flight state: design just created the board, no
    issues activated yet (current_issue_id None)."""
    board = PBLIssueboard.model_validate({
        "agent_ids": ["a"],
        "issues": [],
        "current_issue_id": None,
    })
    assert board.current_issue_id is None
    assert board.issues == []


def test_chat_message_round_trip():
    msg = PBLChatMessage.model_validate({
        "id": "m1",
        "agent_name": "Question",
        "message": "Welcome!",
        "timestamp": 1234567890.5,
        "read_by": [],
    })
    assert msg.message == "Welcome!"
    assert msg.timestamp == 1234567890.5


# ── Invariant: extra='forbid' on the strict models ───────────────────


@pytest.mark.parametrize("model_cls,fixture", [
    (PBLProjectInfo, {"title": "t", "description": "d"}),
    (PBLAgent, _AGENT_QUESTION),
    (PBLIssue, _ISSUE_1),
    (PBLIssueboard, {"agent_ids": [], "issues": [], "current_issue_id": None}),
    (PBLChatMessage, {"id": "m1", "agent_name": "A", "message": "x", "timestamp": 0, "read_by": []}),
    (PBLChat, {"messages": []}),
    (PBLProjectConfig, _FULL_CONFIG),
])
def test_extra_fields_forbidden_on_strict_models(model_cls, fixture):
    """Stale or hostile payloads with extra fields surface as
    ValidationError — drift between our types + upstream's TS
    interfaces is caught loudly, not propagated."""
    bad = dict(fixture, surprise_field="hello")
    with pytest.raises(ValidationError):
        model_cls.model_validate(bad)


# ── Invariant: PBLToolResult ALLOWS extra fields ─────────────────────


def test_tool_result_minimal_success():
    r = PBLToolResult.model_validate({"success": True})
    assert r.success is True
    assert r.error is None


def test_tool_result_with_extras_preserved():
    """Tools attach result-specific fields (agent_id from create_agent,
    issue_count from list_issues, etc.). extra='allow' preserves them
    so the LLM's tool-result message keeps the data the design loop
    needs to reason about its next step."""
    r = PBLToolResult.model_validate({
        "success": True,
        "message": "Created Frontend Dev",
        "agent_id": "agent-42",
        "agent_count_after": 3,
    })
    dumped = r.model_dump()
    assert dumped["agent_id"] == "agent-42"
    assert dumped["agent_count_after"] == 3


def test_tool_result_failure_path():
    r = PBLToolResult.model_validate({
        "success": False,
        "error": "agent_id 'agent-99' not found",
    })
    assert r.success is False
    assert r.error == "agent_id 'agent-99' not found"


# ── Mode literal ─────────────────────────────────────────────────────


def test_mode_literal_rejects_unknown_value():
    """PBLMode is Literal — set_mode tool (MAIC-702) will guard
    against unknown values before they reach state. Pydantic
    enforcement here is the inner safety net."""
    bad_agent = dict(_AGENT_QUESTION, role_division="not-a-real-division")
    with pytest.raises(ValidationError):
        PBLAgent.model_validate(bad_agent)


# ── Round-trip parity with the wire shape ────────────────────────────


def test_project_config_round_trip_preserves_wire_shape():
    """model_dump() output must be re-validatable. Critical because
    the backend persists project_config as JSON, reads it back at
    next chat turn, and must not lose or re-shape any field."""
    cfg = PBLProjectConfig.model_validate(_FULL_CONFIG)
    dumped = cfg.model_dump(exclude_none=False)
    re_validated = PBLProjectConfig.model_validate(dumped)
    assert re_validated.projectInfo.title == cfg.projectInfo.title
    assert (
        len(re_validated.agents) == len(cfg.agents)
        and re_validated.agents[0].name == cfg.agents[0].name
    )


def test_full_config_serializes_with_camel_case_keys():
    """projectInfo and selectedRole are the two camelCase fields.
    Pydantic by default uses Python attribute names; we must NOT
    snake_case them, since the wire shape (and upstream TS) is
    camelCase. Verify the dumped JSON matches input."""
    cfg = PBLProjectConfig.model_validate(_FULL_CONFIG)
    dumped = cfg.model_dump()
    assert "projectInfo" in dumped
    assert "selectedRole" in dumped
    assert "project_info" not in dumped
    assert "selected_role" not in dumped
