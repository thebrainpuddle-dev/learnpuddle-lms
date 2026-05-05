"""Tests for IssueboardMCP (MAIC-702.4).

Highest-coverage MCP tests because IssueboardMCP has the most surface
area + the most complex invariants (cascade delete, reorder semantics,
active/done lifecycle, per-issue agent auto-spawn).
"""
from __future__ import annotations

import pytest

from apps.maic_pbl.mcp import AgentMCP, IssueboardMCP


def _fresh_setup(language_directive: str = ""):
    """Build a fresh config + AgentMCP + IssueboardMCP triad."""
    config: dict = {"agents": [], "issueboard": {}}
    agent_mcp = AgentMCP(config)
    issueboard_mcp = IssueboardMCP(config, agent_mcp, language_directive)
    return config, agent_mcp, issueboard_mcp


# ── Issueboard-level ─────────────────────────────────────────────────


def test_create_issueboard_resets_to_empty():
    config, _, board = _fresh_setup()
    config["issueboard"] = {
        "agent_ids": ["dirty"],
        "issues": [{"id": "x"}],
        "current_issue_id": "x",
    }
    result = board.create_issueboard()
    assert result.success is True
    assert config["issueboard"] == {
        "agent_ids": [], "issues": [], "current_issue_id": None,
    }


def test_get_issueboard_returns_deep_copies():
    config, _, board = _fresh_setup()
    board.create_issue(
        title="A", description="d", person_in_charge="dev",
    )
    listed = board.get_issueboard().model_dump()
    listed["issues"][0]["title"] = "HACKED"
    # Internal state untouched
    assert config["issueboard"]["issues"][0]["title"] == "A"


def test_update_issueboard_agents_replaces_list():
    config, _, board = _fresh_setup()
    board.update_issueboard_agents(["A", "B", "C"])
    assert config["issueboard"]["agent_ids"] == ["A", "B", "C"]


# ── create_issue ─────────────────────────────────────────────────────


def test_create_issue_happy_path_auto_spawns_q_and_j_agents():
    """The load-bearing invariant: every create_issue spawns a
    Question + Judge agent named "<role> Agent - issue_N"."""
    config, agent_mcp, board = _fresh_setup()
    result = board.create_issue(
        title="Define API",
        description="Sketch endpoints.",
        person_in_charge="Frontend Dev",
    )
    assert result.success is True
    dumped = result.model_dump()
    assert dumped["issue_id"] == "issue_1"

    # Issue persisted
    assert len(config["issueboard"]["issues"]) == 1
    issue = config["issueboard"]["issues"][0]
    assert issue["question_agent_name"] == "Question Agent - issue_1"
    assert issue["judge_agent_name"] == "Judge Agent - issue_1"

    # Agents auto-spawned
    agent_names = {a["name"] for a in config["agents"]}
    assert "Question Agent - issue_1" in agent_names
    assert "Judge Agent - issue_1" in agent_names


def test_create_issue_propagates_language_directive_to_agent_prompts():
    """When language_directive is set, the auto-spawned agents get
    the localized prompt — important for non-English classrooms."""
    config, _, board = _fresh_setup(language_directive="Always respond in 中文.")
    board.create_issue(
        title="X", description="x", person_in_charge="dev",
    )
    q_agent = next(
        a for a in config["agents"] if a["name"].startswith("Question Agent")
    )
    assert "Always respond in 中文." in q_agent["system_prompt"]


def test_create_issue_increments_id_counter():
    config, _, board = _fresh_setup()
    board.create_issue(title="A", description="d", person_in_charge="dev")
    board.create_issue(title="B", description="d", person_in_charge="dev")
    board.create_issue(title="C", description="d", person_in_charge="dev")
    ids = [i["id"] for i in config["issueboard"]["issues"]]
    assert ids == ["issue_1", "issue_2", "issue_3"]


def test_create_issue_rejects_empty_title():
    _, _, board = _fresh_setup()
    result = board.create_issue(
        title="", description="d", person_in_charge="dev",
    )
    assert result.success is False
    assert result.error == "Title cannot be empty."


def test_create_issue_rejects_empty_person_in_charge():
    _, _, board = _fresh_setup()
    result = board.create_issue(
        title="X", description="d", person_in_charge="",
    )
    assert result.success is False
    assert result.error == "Person in charge cannot be empty."


def test_create_issue_with_parent_validates_existence():
    _, _, board = _fresh_setup()
    result = board.create_issue(
        title="X", description="d", person_in_charge="dev",
        parent_issue="ghost",
    )
    assert result.success is False
    assert "ghost" in (result.error or "")


def test_create_sub_issue_under_existing_parent():
    config, _, board = _fresh_setup()
    board.create_issue(title="Parent", description="d", person_in_charge="dev")
    result = board.create_issue(
        title="Child", description="d", person_in_charge="dev",
        parent_issue="issue_1",
    )
    assert result.success is True
    child = config["issueboard"]["issues"][1]
    assert child["parent_issue"] == "issue_1"


# ── list/get_issue ───────────────────────────────────────────────────


def test_list_issues_returns_deep_copies():
    config, _, board = _fresh_setup()
    board.create_issue(title="X", description="d", person_in_charge="dev")
    listed = board.list_issues().model_dump()
    listed["issues"][0]["title"] = "HACKED"
    assert config["issueboard"]["issues"][0]["title"] == "X"


def test_get_issue_present():
    _, _, board = _fresh_setup()
    board.create_issue(title="X", description="d", person_in_charge="dev")
    result = board.get_issue("issue_1")
    assert result.success is True
    assert result.model_dump()["issues"][0]["title"] == "X"


def test_get_issue_missing():
    _, _, board = _fresh_setup()
    result = board.get_issue("ghost")
    assert result.success is False
    assert result.error == 'Issue "ghost" not found.'


# ── update_issue ─────────────────────────────────────────────────────


def test_update_issue_patches_only_provided_fields():
    config, _, board = _fresh_setup()
    board.create_issue(
        title="X", description="d", person_in_charge="dev", notes="orig",
    )
    result = board.update_issue(
        issue_id="issue_1", title="X-renamed", notes="new notes",
    )
    assert result.success is True
    issue = config["issueboard"]["issues"][0]
    assert issue["title"] == "X-renamed"
    assert issue["notes"] == "new notes"
    assert issue["description"] == "d"  # untouched


def test_update_issue_missing_returns_error():
    _, _, board = _fresh_setup()
    result = board.update_issue(issue_id="ghost", title="X")
    assert result.success is False
    assert result.error == 'Issue "ghost" not found.'


def test_set_issue_parent_to_existing_works():
    """set_issue_parent is the dedicated tool for FK changes —
    update_issue can't safely accept parent_issue because the
    LangChain StructuredTool layer can't distinguish field-omitted
    from field-set-to-null."""
    config, _, board = _fresh_setup()
    board.create_issue(title="A", description="d", person_in_charge="dev")
    board.create_issue(title="B", description="d", person_in_charge="dev")
    result = board.set_issue_parent(issue_id="issue_2", parent_issue="issue_1")
    assert result.success is True
    assert config["issueboard"]["issues"][1]["parent_issue"] == "issue_1"


def test_set_issue_parent_to_null_clears():
    """parent_issue=None clears the FK."""
    config, _, board = _fresh_setup()
    board.create_issue(title="A", description="d", person_in_charge="dev")
    board.create_issue(
        title="B", description="d", person_in_charge="dev",
        parent_issue="issue_1",
    )
    result = board.set_issue_parent(issue_id="issue_2", parent_issue=None)
    assert result.success is True
    assert config["issueboard"]["issues"][1]["parent_issue"] is None


def test_set_issue_parent_validates_target_exists():
    _, _, board = _fresh_setup()
    board.create_issue(title="X", description="d", person_in_charge="dev")
    result = board.set_issue_parent(issue_id="issue_1", parent_issue="ghost")
    assert result.success is False
    assert "ghost" in (result.error or "")


def test_set_issue_parent_validates_issue_exists():
    _, _, board = _fresh_setup()
    result = board.set_issue_parent(issue_id="ghost", parent_issue=None)
    assert result.success is False
    assert "ghost" in (result.error or "")


def test_set_issue_parent_rejects_self_parent_cycle():
    """Defensive: an issue can't be its own parent (would create a
    cycle in the parent chain). New invariant added with the API split."""
    _, _, board = _fresh_setup()
    board.create_issue(title="X", description="d", person_in_charge="dev")
    result = board.set_issue_parent(issue_id="issue_1", parent_issue="issue_1")
    assert result.success is False
    assert "own parent" in (result.error or "").lower()


def test_update_issue_no_longer_accepts_parent_issue():
    """parent_issue is gone from update_issue per the LangChain-layer
    fix. Calling with parent_issue= raises TypeError (kwargs)."""
    _, _, board = _fresh_setup()
    board.create_issue(title="X", description="d", person_in_charge="dev")
    with pytest.raises(TypeError):
        board.update_issue(  # type: ignore[call-arg]
            issue_id="issue_1", parent_issue="should-not-work",
        )


# ── delete_issue ─────────────────────────────────────────────────────


def test_delete_issue_happy_path():
    config, _, board = _fresh_setup()
    board.create_issue(title="X", description="d", person_in_charge="dev")
    result = board.delete_issue("issue_1")
    assert result.success is True
    assert config["issueboard"]["issues"] == []


def test_delete_issue_cascades_to_children():
    """Cascade: deleting a parent removes all children pointing at it."""
    config, _, board = _fresh_setup()
    board.create_issue(title="P", description="d", person_in_charge="dev")
    board.create_issue(
        title="C1", description="d", person_in_charge="dev",
        parent_issue="issue_1",
    )
    board.create_issue(
        title="C2", description="d", person_in_charge="dev",
        parent_issue="issue_1",
    )
    board.create_issue(
        title="Standalone", description="d", person_in_charge="dev",
    )
    assert len(config["issueboard"]["issues"]) == 4

    board.delete_issue("issue_1")
    remaining = [i["id"] for i in config["issueboard"]["issues"]]
    assert remaining == ["issue_4"]  # Only the standalone survives


def test_delete_issue_missing_returns_error():
    _, _, board = _fresh_setup()
    result = board.delete_issue("ghost")
    assert result.success is False
    assert result.error == 'Issue "ghost" not found.'


# ── reorder_issues ───────────────────────────────────────────────────


def test_reorder_issues_full_list_resets_indexes():
    config, _, board = _fresh_setup()
    for n in ("A", "B", "C"):
        board.create_issue(title=n, description="d", person_in_charge="dev")
    board.reorder_issues(["issue_3", "issue_1", "issue_2"])
    issues = config["issueboard"]["issues"]
    assert [i["id"] for i in issues] == ["issue_3", "issue_1", "issue_2"]
    assert [i["index"] for i in issues] == [0, 1, 2]


def test_reorder_issues_partial_list_keeps_unmentioned_at_end():
    """Issues NOT in the reorder list stay at the end in their
    original relative order."""
    config, _, board = _fresh_setup()
    for n in ("A", "B", "C", "D"):
        board.create_issue(title=n, description="d", person_in_charge="dev")
    # Reorder only first two; leave issue_3 + issue_4 alone
    board.reorder_issues(["issue_2", "issue_1"])
    ids = [i["id"] for i in config["issueboard"]["issues"]]
    assert ids == ["issue_2", "issue_1", "issue_3", "issue_4"]


def test_reorder_issues_with_unknown_id_returns_error():
    _, _, board = _fresh_setup()
    board.create_issue(title="A", description="d", person_in_charge="dev")
    result = board.reorder_issues(["issue_1", "ghost"])
    assert result.success is False
    assert "ghost" in (result.error or "")


# ── Lifecycle: activate_next + complete_current ─────────────────────


def test_activate_next_issue_picks_lowest_index_undone():
    config, _, board = _fresh_setup()
    for n, idx in [("A", 2), ("B", 0), ("C", 1)]:
        board.create_issue(
            title=n, description="d", person_in_charge="dev", index=idx,
        )
    result = board.activate_next_issue()
    assert result.success is True
    assert result.model_dump()["issue_id"] == "issue_2"  # B has index=0
    assert config["issueboard"]["current_issue_id"] == "issue_2"
    assert config["issueboard"]["issues"][1]["is_active"] is True


def test_activate_next_issue_skips_done():
    config, _, board = _fresh_setup()
    board.create_issue(title="A", description="d", person_in_charge="dev")
    board.create_issue(title="B", description="d", person_in_charge="dev")
    # Mark issue_1 as done by direct mutation (the lifecycle path
    # under test is "skip done"; isolation from complete_current_issue).
    config["issueboard"]["issues"][0]["is_done"] = True
    result = board.activate_next_issue()
    assert result.success is True
    assert result.model_dump()["issue_id"] == "issue_2"


def test_activate_next_issue_when_all_done_returns_terminal_error():
    config, _, board = _fresh_setup()
    board.create_issue(title="A", description="d", person_in_charge="dev")
    config["issueboard"]["issues"][0]["is_done"] = True
    result = board.activate_next_issue()
    assert result.success is False
    assert result.error == "No more issues to activate."


def test_activate_next_deactivates_previous_active():
    config, _, board = _fresh_setup()
    board.create_issue(title="A", description="d", person_in_charge="dev")
    board.create_issue(title="B", description="d", person_in_charge="dev")
    board.activate_next_issue()  # activates issue_1
    assert config["issueboard"]["issues"][0]["is_active"] is True

    # Manually mark issue_1 as done so issue_2 can be next
    config["issueboard"]["issues"][0]["is_done"] = True
    board.activate_next_issue()
    assert config["issueboard"]["issues"][0]["is_active"] is False
    assert config["issueboard"]["issues"][1]["is_active"] is True


def test_complete_current_issue_flips_is_done():
    config, _, board = _fresh_setup()
    board.create_issue(title="A", description="d", person_in_charge="dev")
    board.activate_next_issue()
    result = board.complete_current_issue()
    assert result.success is True
    assert config["issueboard"]["issues"][0]["is_done"] is True
    assert config["issueboard"]["issues"][0]["is_active"] is False
    assert config["issueboard"]["current_issue_id"] is None


def test_complete_current_issue_with_no_active_returns_error():
    _, _, board = _fresh_setup()
    board.create_issue(title="A", description="d", person_in_charge="dev")
    # No activate_next_issue() — nothing is active
    result = board.complete_current_issue()
    assert result.success is False
    assert result.error == "No active issue to complete."


# ── Shared-state invariant ───────────────────────────────────────────


def test_mutations_share_state_with_caller_dict():
    """Same load-bearing invariant as ProjectMCP and AgentMCP."""
    config = {"agents": [], "issueboard": {}, "projectInfo": {"title": "x"}}
    agent_mcp = AgentMCP(config)
    board = IssueboardMCP(config, agent_mcp)
    board.create_issue(title="X", description="d", person_in_charge="dev")
    # Caller observes mutation directly across BOTH slices the
    # IssueboardMCP touches (issueboard + agents — auto-spawn)
    assert len(config["issueboard"]["issues"]) == 1
    assert len(config["agents"]) == 2  # Q+J auto-spawn
    assert config["projectInfo"]["title"] == "x"  # untouched
