"""IssueboardMCP — issueboard mutator (the biggest MCP).

Source: THU-MAIC/OpenMAIC lib/pbl/mcp/issueboard-mcp.ts (260 lines)
        Lifted under ADR-001a.

Owns config['issueboard'] on the shared PBLProjectConfig dict. The
design loop drives this MCP during the `issueboard` mode (set by
ModeMCP) to populate the project's milestone/task list. Every issue
auto-spawns a Question agent + Judge agent (via the AgentMCP
reference) so chat can route per-issue mentions consistently.

10 methods total (8 from the original spec + activate_next_issue +
complete_current_issue lifecycle helpers):

  create_issueboard           — reset to empty {agent_ids:[], issues:[]}
  get_issueboard              — read whole struct
  update_issueboard_agents    — set agent_ids
  create_issue                — append (auto-spawns Q+J agents per issue)
  list_issues                 — read all
  get_issue(id)               — read one
  update_issue                — patch one
  delete_issue                — remove (cascades to child issues)
  reorder_issues              — drag-and-drop semantics
  activate_next_issue         — deactivate current, activate next undone
  complete_current_issue      — flip is_done=True, clear current_issue_id

Per-issue Q+J agent naming: "Question Agent - issue_N" / "Judge Agent
- issue_N" — matches upstream's pattern verbatim so chat routing stays
deterministic.
"""
from __future__ import annotations

from typing import Any

from apps.maic_pbl.mcp.agent_mcp import AgentMCP
from apps.maic_pbl.mcp.agent_templates import (
    get_judge_agent_prompt,
    get_question_agent_prompt,
)
from apps.maic_pbl.types import PBLToolResult


class IssueboardMCP:
    """Owns config['issueboard']; auto-spawns Q+J agents per issue."""

    def __init__(
        self,
        config: dict[str, Any],
        agent_mcp: AgentMCP,
        language_directive: str = "",
    ):
        # Defensive: caller may pass a config with `issueboard` already
        # present but missing one or more inner keys (common in unit
        # test fixtures and partial-state recovery paths). Ensure the
        # full inner shape via per-key setdefault rather than relying
        # on the outer setdefault alone.
        board = config.setdefault("issueboard", {})
        board.setdefault("agent_ids", [])
        board.setdefault("issues", [])
        board.setdefault("current_issue_id", None)
        self._config = config
        self._agent_mcp = agent_mcp
        self._language_directive = language_directive
        self._next_issue_id = 1

    # ── Issueboard-level ops ──────────────────────────────────────────

    def create_issueboard(self) -> PBLToolResult:
        """Reset issueboard to empty state. Used at design loop start."""
        self._config["issueboard"] = {
            "agent_ids": [],
            "issues": [],
            "current_issue_id": None,
        }
        self._next_issue_id = 1
        return PBLToolResult(
            success=True, message="Issueboard created successfully.",
        )

    def get_issueboard(self) -> PBLToolResult:
        """Read whole issueboard (deep-copied)."""
        board = self._config["issueboard"]
        return PBLToolResult(
            success=True,
            agent_ids=list(board["agent_ids"]),
            issues=[dict(i) for i in board["issues"]],
        )

    def update_issueboard_agents(self, agent_ids: list[str]) -> PBLToolResult:
        """Replace the agent_ids list (which dev-role agents are
        present on this board)."""
        self._config["issueboard"]["agent_ids"] = list(agent_ids)
        return PBLToolResult(
            success=True, message="Issueboard agents updated successfully.",
        )

    # ── Per-issue ops ─────────────────────────────────────────────────

    def create_issue(
        self,
        *,
        title: str,
        description: str,
        person_in_charge: str,
        participants: list[str] | None = None,
        notes: str | None = None,
        parent_issue: str | None = None,
        index: int | None = None,
    ) -> PBLToolResult:
        """Append a new issue. Auto-spawns Question + Judge agents
        named "Question Agent - issue_N" and "Judge Agent - issue_N"
        (matches upstream).

        Coerces None → "" / [] / 0 for the optional fields so a
        LangChain StructuredTool call with Pydantic-defaulted None
        values still produces a schema-valid PBLIssue (notes/index
        are non-nullable in PBLIssue per upstream's TS shape).

        Rejects:
          - empty title
          - empty person_in_charge
          - parent_issue referencing a non-existent issue
        """
        participants = participants or []
        notes = notes if notes is not None else ""
        index = index if index is not None else 0

        if not title or not title.strip():
            return PBLToolResult(success=False, error="Title cannot be empty.")
        if not person_in_charge or not person_in_charge.strip():
            return PBLToolResult(
                success=False, error="Person in charge cannot be empty.",
            )
        if parent_issue and not any(
            i["id"] == parent_issue for i in self._config["issueboard"]["issues"]
        ):
            return PBLToolResult(
                success=False,
                error=f'Parent issue "{parent_issue}" not found.',
            )

        issue_id = f"issue_{self._next_issue_id}"
        self._next_issue_id += 1
        question_agent_name = f"Question Agent - {issue_id}"
        judge_agent_name = f"Judge Agent - {issue_id}"

        new_issue: dict[str, Any] = {
            "id": issue_id,
            "title": title,
            "description": description,
            "person_in_charge": person_in_charge,
            "participants": list(participants),
            "notes": notes,
            "parent_issue": parent_issue,
            "index": index,
            "is_done": False,
            "is_active": False,
            "generated_questions": "",
            "question_agent_name": question_agent_name,
            "judge_agent_name": judge_agent_name,
        }
        self._config["issueboard"]["issues"].append(new_issue)

        # Auto-create the per-issue Q+J system agents
        self._agent_mcp.create_agent(
            name=question_agent_name,
            system_prompt=get_question_agent_prompt(self._language_directive),
            default_mode="chat",
            actor_role="Question Assistant for Issue",
            role_division="development",
            is_system_agent=True,
        )
        self._agent_mcp.create_agent(
            name=judge_agent_name,
            system_prompt=get_judge_agent_prompt(self._language_directive),
            default_mode="chat",
            actor_role="Judge for Issue Completion",
            role_division="management",
            is_system_agent=True,
        )

        return PBLToolResult(
            success=True,
            issue_id=issue_id,
            message="Issue created with question and judge agents.",
        )

    def list_issues(self) -> PBLToolResult:
        """Read all issues (deep-copied)."""
        return PBLToolResult(
            success=True,
            issues=[dict(i) for i in self._config["issueboard"]["issues"]],
        )

    def get_issue(self, issue_id: str) -> PBLToolResult:
        """Read one issue by id."""
        for i in self._config["issueboard"]["issues"]:
            if i["id"] == issue_id:
                return PBLToolResult(success=True, issues=[dict(i)])
        return PBLToolResult(
            success=False, error=f'Issue "{issue_id}" not found.',
        )

    def update_issue(
        self,
        *,
        issue_id: str,
        title: str | None = None,
        description: str | None = None,
        person_in_charge: str | None = None,
        participants: list[str] | None = None,
        notes: str | None = None,
        index: int | None = None,
    ) -> PBLToolResult:
        """Patch one issue. Optional fields stay unchanged when omitted.

        Note: parent_issue is intentionally NOT in this method. The
        LangChain StructuredTool layer can't distinguish "field omitted"
        from "field set to None" (Pydantic's model_dump fills defaults),
        so a single update_issue call wired through a tool would always
        clobber parent_issue to None. set_issue_parent below is the
        dedicated tool the design loop uses to mutate the FK.
        """
        issues = self._config["issueboard"]["issues"]
        issue = next((i for i in issues if i["id"] == issue_id), None)
        if issue is None:
            return PBLToolResult(
                success=False, error=f'Issue "{issue_id}" not found.',
            )

        if title is not None:
            issue["title"] = title
        if description is not None:
            issue["description"] = description
        if person_in_charge is not None:
            issue["person_in_charge"] = person_in_charge
        if participants is not None:
            issue["participants"] = list(participants)
        if notes is not None:
            issue["notes"] = notes
        if index is not None:
            issue["index"] = index

        return PBLToolResult(success=True, message="Issue updated successfully.")

    def set_issue_parent(
        self, *, issue_id: str, parent_issue: str | None,
    ) -> PBLToolResult:
        """Set or clear an issue's parent_issue FK.

        parent_issue=None clears the FK; passing a string sets it
        (must reference an existing issue). Split out from update_issue
        so the LangChain tool layer can distinguish "I want to clear
        the parent" from "I'm patching other fields and parent should
        stay alone" — see update_issue's docstring for the upstream
        TS-undefined-vs-null asymmetry that motivated the split.
        """
        issues = self._config["issueboard"]["issues"]
        issue = next((i for i in issues if i["id"] == issue_id), None)
        if issue is None:
            return PBLToolResult(
                success=False, error=f'Issue "{issue_id}" not found.',
            )
        if parent_issue is not None and not any(
            i["id"] == parent_issue for i in issues
        ):
            return PBLToolResult(
                success=False,
                error=f'Parent issue "{parent_issue}" not found.',
            )
        if parent_issue == issue_id:
            return PBLToolResult(
                success=False,
                error="An issue cannot be its own parent.",
            )
        issue["parent_issue"] = parent_issue
        return PBLToolResult(
            success=True,
            message=(
                f'Issue "{issue_id}" parent set to {parent_issue!r}.'
                if parent_issue is not None
                else f'Issue "{issue_id}" parent cleared.'
            ),
        )

    def delete_issue(self, issue_id: str) -> PBLToolResult:
        """Remove an issue. Cascades: child issues whose parent_issue
        points at this id are also removed (matches upstream)."""
        issues = self._config["issueboard"]["issues"]
        for i, issue in enumerate(issues):
            if issue["id"] == issue_id:
                issues.pop(i)
                # Cascade: remove all children
                self._config["issueboard"]["issues"] = [
                    i_ for i_ in issues if i_.get("parent_issue") != issue_id
                ]
                return PBLToolResult(
                    success=True, message="Issue deleted successfully.",
                )
        return PBLToolResult(
            success=False, error=f'Issue "{issue_id}" not found.',
        )

    def reorder_issues(self, issue_ids: list[str]) -> PBLToolResult:
        """Reorder issues. `issue_ids` is the new front-of-list order;
        any issues not mentioned stay at the end of the list in their
        original relative order. issue.index is updated to match the
        new ordering for the prefix.

        Rejects if any id in the list doesn't exist.
        """
        existing = self._config["issueboard"]["issues"]
        existing_by_id = {i["id"]: i for i in existing}

        for id_ in issue_ids:
            if id_ not in existing_by_id:
                return PBLToolResult(
                    success=False, error=f'Issue "{id_}" not found.',
                )

        reordered: list[dict[str, Any]] = []
        for new_idx, id_ in enumerate(issue_ids):
            issue = existing_by_id[id_]
            issue["index"] = new_idx
            reordered.append(issue)
        # Append issues NOT in the reorder list (preserving relative order)
        for issue in existing:
            if issue["id"] not in issue_ids:
                reordered.append(issue)

        self._config["issueboard"]["issues"] = reordered
        return PBLToolResult(success=True, message="Issues reordered successfully.")

    # ── Lifecycle helpers ─────────────────────────────────────────────

    def activate_next_issue(self) -> PBLToolResult:
        """Deactivate current (if any), then activate the lowest-index
        not-done issue. Sets current_issue_id on the issueboard.

        Returns success=False with "No more issues" when all issues
        are marked is_done — terminal state for the design phase."""
        issues = self._config["issueboard"]["issues"]
        # Deactivate any currently-active issue
        for i in issues:
            if i.get("is_active"):
                i["is_active"] = False
        self._config["issueboard"]["current_issue_id"] = None

        # Find the lowest-index undone issue
        candidates = sorted(
            (i for i in issues if not i.get("is_done")),
            key=lambda i: i.get("index", 0),
        )
        if not candidates:
            return PBLToolResult(
                success=False, error="No more issues to activate.",
            )

        next_issue = candidates[0]
        next_issue["is_active"] = True
        self._config["issueboard"]["current_issue_id"] = next_issue["id"]
        return PBLToolResult(
            success=True,
            issue_id=next_issue["id"],
            message=f'Activated issue: {next_issue["title"]}',
        )

    def complete_current_issue(self) -> PBLToolResult:
        """Mark the active issue as done; clear current_issue_id.

        The chat consumer (MAIC-704) calls this when the Judge agent's
        reply contains "COMPLETE". After this, the consumer typically
        calls activate_next_issue() to advance the workspace.
        """
        issues = self._config["issueboard"]["issues"]
        current = next((i for i in issues if i.get("is_active")), None)
        if current is None:
            return PBLToolResult(
                success=False, error="No active issue to complete.",
            )
        current["is_done"] = True
        current["is_active"] = False
        self._config["issueboard"]["current_issue_id"] = None
        return PBLToolResult(
            success=True,
            message=f'Issue "{current["id"]}" marked as complete.',
        )
