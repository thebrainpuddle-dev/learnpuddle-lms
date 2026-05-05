"""Tests for ProjectMCP (MAIC-702.2)."""
from __future__ import annotations

from apps.maic_pbl.mcp import ProjectMCP


def test_init_seeds_project_info_when_absent():
    """Defensive: caller passes a bare {} config — ProjectMCP doesn't
    crash; it initializes the slot."""
    config: dict = {}
    mcp = ProjectMCP(config)
    assert config["projectInfo"] == {"title": "", "description": ""}
    result = mcp.get_project_info()
    assert result.success is True


def test_init_preserves_existing_project_info():
    """Realistic: the design loop builds up project_info incrementally;
    re-construction shouldn't wipe what's there."""
    config = {"projectInfo": {"title": "Existing", "description": "Stuff"}}
    ProjectMCP(config)
    assert config["projectInfo"]["title"] == "Existing"
    assert config["projectInfo"]["description"] == "Stuff"


def test_get_project_info_returns_current_values():
    config = {"projectInfo": {"title": "Fractions", "description": "Math 101"}}
    mcp = ProjectMCP(config)
    result = mcp.get_project_info()
    assert result.success is True
    dumped = result.model_dump()
    assert dumped["title"] == "Fractions"
    assert dumped["description"] == "Math 101"


def test_update_title_happy_path():
    config: dict = {}
    mcp = ProjectMCP(config)
    result = mcp.update_title("My Project")
    assert result.success is True
    assert result.message == "Title updated successfully."
    assert config["projectInfo"]["title"] == "My Project"


def test_update_title_rejects_empty_string():
    config: dict = {}
    mcp = ProjectMCP(config)
    result = mcp.update_title("")
    assert result.success is False
    assert result.error == "Title cannot be empty."
    assert config["projectInfo"]["title"] == ""  # unchanged


def test_update_title_rejects_whitespace_only():
    """Whitespace-only is empty per upstream's `title?.trim()` guard."""
    config: dict = {}
    mcp = ProjectMCP(config)
    result = mcp.update_title("   \t\n  ")
    assert result.success is False
    assert result.error == "Title cannot be empty."


def test_update_description_happy_path():
    config: dict = {}
    mcp = ProjectMCP(config)
    result = mcp.update_description("A great project description.")
    assert result.success is True
    assert config["projectInfo"]["description"] == "A great project description."


def test_update_description_allows_empty_string():
    """Upstream treats empty string as legal — descriptions can
    legitimately be filled in later. Only None is rejected."""
    config = {"projectInfo": {"title": "T", "description": "old"}}
    mcp = ProjectMCP(config)
    result = mcp.update_description("")
    assert result.success is True
    assert config["projectInfo"]["description"] == ""


def test_update_description_rejects_null():
    """The one rejection: None / null is a caller bug, not a valid
    state. Upstream's `description === null || undefined` guard."""
    config: dict = {}
    mcp = ProjectMCP(config)
    result = mcp.update_description(None)  # type: ignore[arg-type]
    assert result.success is False
    assert result.error == "Description cannot be null."


def test_mutations_share_state_with_caller_dict():
    """Critical: ProjectMCP holds a REFERENCE to the caller's config
    dict, not a copy. The design loop owns the dict; all four MCPs
    must mutate the SAME dict so mode switches see consistent state."""
    config: dict = {"agents": [], "issueboard": {}}
    mcp = ProjectMCP(config)
    mcp.update_title("X")
    mcp.update_description("Y")
    # Caller can directly observe mutations
    assert config["projectInfo"] == {"title": "X", "description": "Y"}
    # Other slices untouched
    assert config["agents"] == []
    assert config["issueboard"] == {}
