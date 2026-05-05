"""Tests for AgentMCP + agent templates (MAIC-702.3)."""
from __future__ import annotations

import pytest

from apps.maic_pbl.mcp import (
    AgentMCP,
    get_judge_agent_prompt,
    get_question_agent_prompt,
)


# ── Fixtures ──────────────────────────────────────────────────────────


def _fresh_config() -> dict:
    return {"agents": []}


# ── list_agents ──────────────────────────────────────────────────────


def test_list_agents_empty_returns_no_agents_message():
    mcp = AgentMCP(_fresh_config())
    result = mcp.list_agents()
    dumped = result.model_dump()
    assert result.success is True
    assert dumped["agents"] == []
    assert dumped.get("message") == "No agents found."


def test_list_agents_returns_deep_copies():
    """Mutation safety: caller mutating the returned list MUST NOT
    affect the MCP's internal state."""
    config: dict = {"agents": []}
    mcp = AgentMCP(config)
    mcp.create_agent(
        name="Coder",
        system_prompt="Write code.",
        default_mode="idle",
    )

    listed = mcp.list_agents().model_dump()["agents"]
    listed[0]["name"] = "HACKED"

    # Internal state untouched
    assert config["agents"][0]["name"] == "Coder"


# ── get_agent_info ───────────────────────────────────────────────────


def test_get_agent_info_returns_agent_when_present():
    config: dict = {"agents": []}
    mcp = AgentMCP(config)
    mcp.create_agent(name="X", system_prompt="x", default_mode="idle")
    result = mcp.get_agent_info("X")
    assert result.success is True
    assert result.model_dump()["agent"]["name"] == "X"


def test_get_agent_info_returns_error_when_missing():
    mcp = AgentMCP(_fresh_config())
    result = mcp.get_agent_info("ghost")
    assert result.success is False
    assert result.error == 'Agent "ghost" not found.'


# ── create_agent ─────────────────────────────────────────────────────


def test_create_agent_happy_path():
    config: dict = {"agents": []}
    mcp = AgentMCP(config)
    result = mcp.create_agent(
        name="Frontend Dev",
        system_prompt="Implement the UI.",
        default_mode="idle",
        actor_role="Frontend Dev",
        role_division="development",
    )
    assert result.success is True
    assert result.message == 'Agent "Frontend Dev" created successfully.'
    assert config["agents"][0]["name"] == "Frontend Dev"
    assert config["agents"][0]["env"]["chat"]["system_prompt"] == "Implement the UI."
    assert config["agents"][0]["env"]["chat"]["max_tokens"] == 4096
    assert config["agents"][0]["is_active"] is False
    assert config["agents"][0]["is_user_role"] is False


def test_create_agent_with_system_agent_flag():
    """Question / Judge are spawned with is_system_agent=True so the
    chat UI can hide them from the user-pickable role selector."""
    config: dict = {"agents": []}
    mcp = AgentMCP(config)
    mcp.create_agent(
        name="Question",
        system_prompt=get_question_agent_prompt(),
        default_mode="idle",
        actor_role="Question",
        role_division="management",
        is_system_agent=True,
    )
    assert config["agents"][0]["is_system_agent"] is True
    assert config["agents"][0]["role_division"] == "management"


@pytest.mark.parametrize("bad_name", ["", "   ", "\t\n"])
def test_create_agent_rejects_empty_or_whitespace_name(bad_name):
    mcp = AgentMCP(_fresh_config())
    result = mcp.create_agent(
        name=bad_name, system_prompt="x", default_mode="idle",
    )
    assert result.success is False
    assert result.error == "Agent name cannot be empty."


def test_create_agent_rejects_empty_system_prompt():
    mcp = AgentMCP(_fresh_config())
    result = mcp.create_agent(name="X", system_prompt="", default_mode="idle")
    assert result.success is False
    assert result.error == "System prompt cannot be empty."


def test_create_agent_rejects_duplicate_name():
    """Name uniqueness is enforced — chat protocol uses @<name> for
    routing; duplicates would create ambiguity."""
    mcp = AgentMCP(_fresh_config())
    mcp.create_agent(name="X", system_prompt="x", default_mode="idle")
    result = mcp.create_agent(name="X", system_prompt="y", default_mode="idle")
    assert result.success is False
    assert result.error == 'Agent "X" already exists.'


# ── update_agent ─────────────────────────────────────────────────────


def test_update_agent_patches_only_provided_fields():
    config: dict = {"agents": []}
    mcp = AgentMCP(config)
    mcp.create_agent(name="X", system_prompt="old", default_mode="idle")
    result = mcp.update_agent(name="X", system_prompt="new prompt")
    assert result.success is True
    assert config["agents"][0]["system_prompt"] == "new prompt"
    # env.chat.system_prompt also synced (upstream invariant)
    assert config["agents"][0]["env"]["chat"]["system_prompt"] == "new prompt"
    # default_mode untouched
    assert config["agents"][0]["default_mode"] == "idle"


def test_update_agent_rename_happy_path():
    config: dict = {"agents": []}
    mcp = AgentMCP(config)
    mcp.create_agent(name="OldName", system_prompt="x", default_mode="idle")
    result = mcp.update_agent(name="OldName", new_name="NewName")
    assert result.success is True
    assert config["agents"][0]["name"] == "NewName"


def test_update_agent_rename_to_existing_rejected():
    """Rename collision protection."""
    mcp = AgentMCP(_fresh_config())
    mcp.create_agent(name="A", system_prompt="x", default_mode="idle")
    mcp.create_agent(name="B", system_prompt="x", default_mode="idle")
    result = mcp.update_agent(name="A", new_name="B")
    assert result.success is False
    assert result.error == 'Agent "B" already exists.'


def test_update_agent_rename_to_self_is_no_op():
    """Renaming to the same name should not trigger the duplicate-
    name guard. Upstream's check uses `!== params.name` so same-name
    rename is silently allowed."""
    mcp = AgentMCP(_fresh_config())
    mcp.create_agent(name="X", system_prompt="x", default_mode="idle")
    result = mcp.update_agent(name="X", new_name="X")
    assert result.success is True


def test_update_agent_missing_returns_error():
    mcp = AgentMCP(_fresh_config())
    result = mcp.update_agent(name="ghost", system_prompt="y")
    assert result.success is False
    assert result.error == 'Agent "ghost" not found.'


# ── delete_agent ─────────────────────────────────────────────────────


def test_delete_agent_happy_path():
    config: dict = {"agents": []}
    mcp = AgentMCP(config)
    mcp.create_agent(name="X", system_prompt="x", default_mode="idle")
    mcp.create_agent(name="Y", system_prompt="y", default_mode="idle")
    result = mcp.delete_agent("X")
    assert result.success is True
    names = [a["name"] for a in config["agents"]]
    assert "X" not in names
    assert "Y" in names


def test_delete_agent_missing_returns_error():
    mcp = AgentMCP(_fresh_config())
    result = mcp.delete_agent("ghost")
    assert result.success is False
    assert result.error == 'Agent "ghost" not found.'


# ── Agent templates ──────────────────────────────────────────────────


def test_question_agent_prompt_default_no_language_section():
    prompt = get_question_agent_prompt()
    assert "Question Agent" in prompt
    assert "Initial Question Generation" in prompt
    assert "## Language" not in prompt


def test_question_agent_prompt_with_language_directive():
    prompt = get_question_agent_prompt("Always respond in 中文.")
    assert "## Language" in prompt
    assert "Always respond in 中文." in prompt


def test_judge_agent_prompt_includes_complete_verdict_protocol():
    """The Judge prompt MUST include the COMPLETE/NEEDS_REVISION
    verdict protocol — the chat consumer (MAIC-704) parses this
    string to flip an issue's is_done flag."""
    prompt = get_judge_agent_prompt()
    assert "Judge Agent" in prompt
    assert "COMPLETE" in prompt
    assert "NEEDS_REVISION" in prompt


def test_judge_agent_prompt_with_language_directive():
    prompt = get_judge_agent_prompt("Respond in français.")
    assert "## Language" in prompt
    assert "Respond in français." in prompt


# ── Shared-state invariant ───────────────────────────────────────────


def test_mutations_share_state_with_caller_dict():
    """Same load-bearing invariant as ProjectMCP: AgentMCP holds a
    reference to the caller's config dict, not a copy."""
    config: dict = {"agents": [], "projectInfo": {"title": "x"}}
    mcp = AgentMCP(config)
    mcp.create_agent(name="X", system_prompt="x", default_mode="idle")
    # Caller observes the mutation directly
    assert config["agents"][0]["name"] == "X"
    # Other slices untouched
    assert config["projectInfo"]["title"] == "x"
