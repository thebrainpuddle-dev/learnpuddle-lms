"""PBL type definitions — Pydantic port of upstream OpenMAIC.

Source: THU-MAIC/OpenMAIC lib/pbl/types.ts (lines 1-80)
        Lifted under ADR-001a (full OpenMAIC license ownership).

Frontend mirror at frontend/src/types/pbl.ts (clean TS lift). Keep
these in lockstep — drift between the two surfaces is the most
common Phase 7 regression source. Backend validates via Pydantic at
write time (model save / API ingest); frontend gets TS-time checking
on every consumer.

Why these matter:
- `PBLProjectConfig` is the blob persisted in MaicPBLSession.project_config
- The 13 MCP tools (MAIC-702) all return `PBLToolResult`
- The design loop (MAIC-703) emits PBLProjectConfig as its terminal output

extra='forbid' across all models so a future drift between our types
and upstream's TS interfaces gets caught loudly at validation time
rather than silently propagating into a stale schema.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


# ── Enums ──────────────────────────────────────────────────────────────


PBLMode = Literal["project_info", "agent", "issueboard", "idle"]

# Module-level constants for the four loop modes. Use these instead
# of raw strings so a typo in design_graph.py or a tool wrapper
# surfaces at import time rather than as a runtime mode-gate failure.
MODE_PROJECT_INFO: PBLMode = "project_info"
MODE_AGENT: PBLMode = "agent"
MODE_ISSUEBOARD: PBLMode = "issueboard"
MODE_IDLE: PBLMode = "idle"

PBLRoleDivision = Literal["management", "development"]

ROLE_DIVISION_MANAGEMENT: PBLRoleDivision = "management"
ROLE_DIVISION_DEVELOPMENT: PBLRoleDivision = "development"


# ── Project info ───────────────────────────────────────────────────────


class PBLProjectInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    description: str


# ── Agent ──────────────────────────────────────────────────────────────


class PBLAgent(BaseModel):
    """One participant in the PBL workspace.

    `actor_role` is a short verb ("Question", "Judge", "Frontend Dev")
    used in chat mentions; `role_division` segregates system agents
    (Question/Judge) from development agents the student picks among.
    `is_user_role=True` flags an agent the student CAN select; only
    development-division agents are typically marked thus.

    `delay_time` is upstream's typing pause in ms (visual realism in
    the chat panel); 0 means immediate. `env` is a free-form dict
    upstream uses to thread per-agent context (e.g. file refs);
    Phase 7 doesn't inspect it but preserves it through round-trips.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    actor_role: str
    role_division: PBLRoleDivision
    system_prompt: str
    default_mode: str
    delay_time: float = 0
    env: dict[str, Any] = {}
    is_user_role: bool
    is_active: bool
    is_system_agent: bool


# ── Issue (one milestone in the issueboard) ────────────────────────────


class PBLIssue(BaseModel):
    """A single sequenced milestone the student works through.

    `is_active` is set true on the current issue (only one at a time);
    `is_done` is flipped by the Judge agent on completion. The chat
    UI shows `generated_questions` as the Question Agent's welcome
    message when the issue activates.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str
    person_in_charge: str
    participants: list[str]
    notes: str
    parent_issue: str | None = None
    index: int
    is_done: bool
    is_active: bool
    generated_questions: str
    question_agent_name: str
    judge_agent_name: str


# ── Issueboard ─────────────────────────────────────────────────────────


class PBLIssueboard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_ids: list[str]
    issues: list[PBLIssue]
    current_issue_id: str | None = None


# ── Chat ───────────────────────────────────────────────────────────────


class PBLChatMessage(BaseModel):
    """One turn in the chat log. `read_by` carries agent_names that
    have already processed this message — used by upstream's read-
    receipt logic so an agent doesn't re-process the same message
    twice if the loop iterates."""

    model_config = ConfigDict(extra="forbid")

    id: str
    agent_name: str
    message: str
    timestamp: float
    read_by: list[str]


class PBLChat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[PBLChatMessage]


# ── Top-level config ───────────────────────────────────────────────────


class PBLProjectConfig(BaseModel):
    """The blob persisted in `MaicPBLSession.project_config`.

    Empty default-constructed shape == DRAFT state; design loop
    populates fields incrementally via the 13 MCP tools."""

    model_config = ConfigDict(extra="forbid")

    projectInfo: PBLProjectInfo
    agents: list[PBLAgent]
    issueboard: PBLIssueboard
    chat: PBLChat
    selectedRole: str | None = None


# ── MCP tool result (shared envelope) ──────────────────────────────────


class PBLToolResult(BaseModel):
    """Wrapping envelope every MCP tool returns. Mirrors upstream:
    success bool + optional error/message + free-form extras keyed
    in via `**extras` (preserved by Pydantic when extra='allow').

    Note: PBLToolResult is the ONE place we DON'T set extra='forbid'
    — tools attach result-specific fields (e.g. an `agent_id` from
    create_agent, an `issue_count` from list_issues) and we want
    those to flow through to the LLM's tool-result message verbatim.
    """

    model_config = ConfigDict(extra="allow")

    success: bool
    error: str | None = None
    message: str | None = None
