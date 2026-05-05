"""ProjectMCP — projectInfo mutator (title + description).

Source: THU-MAIC/OpenMAIC lib/pbl/mcp/project-mcp.ts (40 lines)
        Lifted under ADR-001a.

Owns the projectInfo slice of the shared PBLProjectConfig dict. The
design loop drives this MCP during the `project_info` mode to set
the project's title + description before pivoting to agent + issue
modes.

The MCP holds a reference to a config dict (NOT a deep copy) — all
four MCPs share the same dict so the agentic loop sees a single
coherent state across mode switches. Caller (MAIC-703) is responsible
for constructing the dict and validating the final result via
PBLProjectConfig at loop close.
"""
from __future__ import annotations

from typing import Any

from apps.maic_pbl.types import PBLToolResult


class ProjectMCP:
    """Owns projectInfo.{title, description} on the shared config dict."""

    def __init__(self, config: dict[str, Any]):
        # Defensive: ensure projectInfo exists. Upstream constructs the
        # config with this slot present; we mirror that posture but
        # tolerate a config without projectInfo by initializing it.
        config.setdefault("projectInfo", {"title": "", "description": ""})
        self._config = config

    def get_project_info(self) -> PBLToolResult:
        """Read current title + description into a tool result."""
        info = self._config["projectInfo"]
        return PBLToolResult(
            success=True,
            title=info.get("title", ""),
            description=info.get("description", ""),
        )

    def update_title(self, title: str) -> PBLToolResult:
        """Set the project title. Empty / whitespace-only is rejected."""
        if not title or not title.strip():
            return PBLToolResult(success=False, error="Title cannot be empty.")
        self._config["projectInfo"]["title"] = title
        return PBLToolResult(
            success=True,
            message="Title updated successfully.",
        )

    def update_description(self, description: str) -> PBLToolResult:
        """Set the project description. None is rejected; empty string
        is allowed (upstream's posture — descriptions can legitimately
        be filled in later)."""
        if description is None:
            return PBLToolResult(
                success=False, error="Description cannot be null.",
            )
        self._config["projectInfo"]["description"] = description
        return PBLToolResult(
            success=True,
            message="Description updated successfully.",
        )
