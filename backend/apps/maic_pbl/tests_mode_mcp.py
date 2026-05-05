"""Tests for ModeMCP (MAIC-702.1)."""
from __future__ import annotations

import pytest

from apps.maic_pbl.mcp import ModeMCP


_ALL_MODES = ["project_info", "agent", "issueboard", "idle"]


def test_construction_with_default_in_available():
    mcp = ModeMCP(_ALL_MODES, "project_info")
    assert mcp.get_current_mode() == "project_info"
    assert mcp.get_available_modes() == _ALL_MODES


def test_construction_rejects_default_not_in_available():
    """Defensive guard — caller can't construct an MCP whose initial
    state is already invalid."""
    with pytest.raises(ValueError, match="not in available_modes"):
        ModeMCP(["project_info", "agent"], "idle")  # type: ignore[arg-type]


def test_set_mode_happy_path_returns_success():
    mcp = ModeMCP(_ALL_MODES, "project_info")
    result = mcp.set_mode("agent")
    assert result.success is True
    assert result.message == 'Switched to "agent" mode.'
    assert mcp.get_current_mode() == "agent"


def test_set_mode_to_current_returns_error_no_mutation():
    """Upstream's same-mode guard: don't burn an LLM step re-entering
    the mode we're already in."""
    mcp = ModeMCP(_ALL_MODES, "project_info")
    result = mcp.set_mode("project_info")
    assert result.success is False
    assert result.error == 'Already in "project_info" mode.'
    assert mcp.get_current_mode() == "project_info"


def test_set_mode_to_unavailable_returns_error_no_mutation():
    """Mode not in the configured list rejects with diagnostic."""
    mcp = ModeMCP(["project_info", "agent"], "project_info")  # type: ignore[arg-type]
    result = mcp.set_mode("idle")
    assert result.success is False
    assert result.error is not None
    assert 'Mode "idle" not available' in result.error
    assert "project_info" in result.error
    assert mcp.get_current_mode() == "project_info"


def test_get_available_modes_returns_copy():
    """Mutation-safety — callers can't poison the MCP's mode list
    by mutating the returned list."""
    mcp = ModeMCP(_ALL_MODES, "project_info")
    modes = mcp.get_available_modes()
    modes.clear()
    # MCP's internal state untouched
    assert mcp.get_available_modes() == _ALL_MODES


def test_set_mode_sequence_through_all_four():
    """Realistic loop trace: project_info → agent → issueboard → idle."""
    mcp = ModeMCP(_ALL_MODES, "project_info")
    for next_mode in ("agent", "issueboard", "idle"):
        result = mcp.set_mode(next_mode)  # type: ignore[arg-type]
        assert result.success is True
        assert mcp.get_current_mode() == next_mode


def test_set_mode_after_idle_can_re_enter():
    """idle is the loop terminator but isn't sticky; if the design
    loop's stop-when guard hasn't fired, set_mode back to project_info
    is legal. (Upstream pattern — idle is just another mode value.)"""
    mcp = ModeMCP(_ALL_MODES, "idle")
    result = mcp.set_mode("project_info")
    assert result.success is True
    assert mcp.get_current_mode() == "project_info"
