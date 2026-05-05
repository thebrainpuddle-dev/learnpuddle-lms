"""MCP-style state-mutation classes for PBL design phase (Phase 7, MAIC-702).

Each class holds a slice of the in-flight PBLProjectConfig and exposes
methods that the agentic design loop (MAIC-703) drives via LLM tool
calls. Methods return PBLToolResult — success/error + free-form
extras — so the LLM can read what happened and decide its next step.

Slice ownership:
  ModeMCP        — current loop state (project_info | agent | issueboard | idle)
  ProjectMCP     — title + description
  AgentMCP       — list of agents (Question, Judge, dev roles)
  IssueboardMCP  — issueboard.{agent_ids, issues, current_issue_id}

These classes are NOT thread-safe. Each design-loop invocation
constructs a fresh set of MCPs over a fresh PBLProjectConfig dict —
the loop is single-threaded by design (one LLM call at a time).

Why class-style not function-style: the upstream lib/pbl/mcp/*.ts
pattern uses ES classes with state held in private fields. Mirroring
that posture per ADR-001a (clean lift). LangChain Tool wrapping
happens at the design-loop layer (MAIC-703), not here — these MCPs
are the underlying Python objects, the Tools are the LLM-facing
adapters.
"""

from apps.maic_pbl.mcp.agent_mcp import AgentMCP
from apps.maic_pbl.mcp.agent_templates import (
    get_judge_agent_prompt,
    get_question_agent_prompt,
)
from apps.maic_pbl.mcp.issueboard_mcp import IssueboardMCP
from apps.maic_pbl.mcp.mode_mcp import ModeMCP
from apps.maic_pbl.mcp.project_mcp import ProjectMCP

__all__ = [
    "AgentMCP",
    "IssueboardMCP",
    "ModeMCP",
    "ProjectMCP",
    "get_judge_agent_prompt",
    "get_question_agent_prompt",
]
