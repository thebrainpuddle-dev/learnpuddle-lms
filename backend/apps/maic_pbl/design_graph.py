"""PBL design-phase agentic loop.

Source: THU-MAIC/OpenMAIC lib/pbl/generate-pbl.ts (430 lines)
        Lifted under ADR-001a.

Drives a multi-step LLM tool-calling conversation that produces a
complete PBLProjectConfig. The LLM is constrained to a state machine
of four modes (project_info | agent | issueboard | idle); each tool
self-gates on the current mode so out-of-order calls return a
structured error rather than mutating state.

Two phases:
  1. Agentic loop: LLM calls tools to set title/description, create
     agents, create issues. Stop conditions: set_mode('idle') OR
     step counter ≥ 30 (matches upstream stepCountIs(30)).
  2. Post-processing: activate the lowest-index issue + ask the
     Question agent to generate a welcome message via a single LLM
     call (no tools).

Why a hand-written loop instead of LangChain's full agent framework:
upstream's posture is a tight `generateText({stopWhen})` loop with a
custom `onStepFinish` callback for progress reporting. We mirror
that posture directly via `model.bind_tools()` + a simple `for step
in range(30)` loop. Cleaner control, easier diff-against-upstream,
no agent-framework dependency creep.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from apps.maic_pbl.mcp import (
    AgentMCP,
    IssueboardMCP,
    ModeMCP,
    ProjectMCP,
    get_question_agent_prompt,
)
from apps.maic_pbl.system_prompt import (
    PBLSystemPromptConfig,
    build_pbl_system_prompt,
)
from apps.maic_pbl.types import PBLToolResult

_logger = logging.getLogger(__name__)


# ── Loop config ───────────────────────────────────────────────────────


_MAX_STEPS: int = 30  # upstream: stepCountIs(30)

_LOOP_KICKOFF_USER_PROMPT: str = (
    "Design a PBL project. Start in project_info mode by setting the "
    "project title and description."
)


# ── Tool argument schemas (Pydantic — LangChain's StructuredTool form) ─


class _SetModeArgs(BaseModel):
    mode: str = Field(
        ...,
        description=(
            "One of: project_info, agent, issueboard, idle. The loop "
            "ends when mode is set to idle."
        ),
    )


class _UpdateTitleArgs(BaseModel):
    title: str = Field(..., description="The new project title.")


class _UpdateDescriptionArgs(BaseModel):
    description: str = Field(..., description="The new project description.")


class _CreateAgentArgs(BaseModel):
    name: str = Field(..., description="Agent name (e.g. 'Frontend Dev').")
    system_prompt: str = Field(
        ..., description="System prompt describing responsibilities."
    )
    default_mode: str = Field(
        ..., description="Default environment mode (typically 'chat')."
    )
    actor_role: str | None = Field(default=None, description="Role label.")
    role_division: str | None = Field(
        default=None,
        description="'management' or 'development' (default development).",
    )


class _UpdateAgentArgs(BaseModel):
    name: str
    new_name: str | None = None
    system_prompt: str | None = None
    default_mode: str | None = None
    actor_role: str | None = None
    role_division: str | None = None


class _DeleteAgentArgs(BaseModel):
    name: str


class _UpdateIssueboardAgentsArgs(BaseModel):
    agent_ids: list[str] = Field(
        ..., description="Agent names to assign to the issueboard."
    )


class _CreateIssueArgs(BaseModel):
    title: str
    description: str
    person_in_charge: str
    participants: list[str] | None = None
    notes: str | None = None
    parent_issue: str | None = None
    index: int | None = None


class _UpdateIssueArgs(BaseModel):
    issue_id: str
    title: str | None = None
    description: str | None = None
    person_in_charge: str | None = None
    participants: list[str] | None = None
    notes: str | None = None
    parent_issue: str | None = None
    index: int | None = None


class _DeleteIssueArgs(BaseModel):
    issue_id: str


class _ReorderIssuesArgs(BaseModel):
    issue_ids: list[str]


# ── Public API ────────────────────────────────────────────────────────


@dataclass
class GeneratePBLConfig:
    """Inputs to generate_pbl_project. Mirrors upstream's
    GeneratePBLConfig interface (generate-pbl.ts:24-30)."""

    project_topic: str
    project_description: str
    target_skills: list[str] = field(default_factory=list)
    issue_count: int = 3
    language_directive: str = ""


@dataclass
class GeneratePBLResult:
    """Output of generate_pbl_project. Carries the populated config
    plus diagnostic counters the API endpoint logs / returns."""

    project_config: dict[str, Any]
    steps_taken: int
    reached_idle: bool
    welcome_message_generated: bool
    error: str | None = None


async def generate_pbl_project(
    config: GeneratePBLConfig,
    model: Any,
    *,
    on_progress: Callable[[str], Awaitable[None]] | None = None,
) -> GeneratePBLResult:
    """Run the design-phase agentic loop and post-processing.

    Args:
        config: project topic, description, target skills, issue count,
            language directive.
        model: a LangChain BaseChatModel (already resolved by caller —
            typically via apps.maic.orchestration.ai_adapter
            .resolve_chat_model). Must support bind_tools().
        on_progress: optional async callback invoked with
            human-readable status messages — mirrors upstream's
            onProgress callback. Use for WS streaming during the
            generation API.

    Returns:
        GeneratePBLResult with the populated project_config.

    The function does NOT raise on LLM/tool errors — they're recorded
    in result.error and result.project_config still reflects whatever
    state the loop reached. Callers (the generation endpoint) decide
    whether partial results are acceptable.
    """
    project_config: dict[str, Any] = {
        "projectInfo": {"title": "", "description": ""},
        "agents": [],
        "issueboard": {"agent_ids": [], "issues": [], "current_issue_id": None},
        "chat": {"messages": []},
    }

    mode_mcp = ModeMCP(
        ["project_info", "agent", "issueboard", "idle"],
        "project_info",
    )
    project_mcp = ProjectMCP(project_config)
    agent_mcp = AgentMCP(project_config)
    issueboard_mcp = IssueboardMCP(
        project_config, agent_mcp, config.language_directive,
    )

    if on_progress:
        await on_progress("Starting PBL project generation...")

    tools = _build_tools(mode_mcp, project_mcp, agent_mcp, issueboard_mcp)

    # Bind tools to the model. LangChain's bind_tools returns a new
    # runnable that includes the tool schemas in every invocation.
    model_with_tools = model.bind_tools(tools)

    system_prompt = build_pbl_system_prompt(
        PBLSystemPromptConfig(
            project_topic=config.project_topic,
            project_description=config.project_description,
            target_skills=list(config.target_skills),
            issue_count=config.issue_count,
            language_directive=config.language_directive,
        )
    )

    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=_LOOP_KICKOFF_USER_PROMPT),
    ]

    tools_by_name = {t.name: t for t in tools}
    steps_taken = 0
    loop_error: str | None = None

    try:
        for _ in range(_MAX_STEPS):
            steps_taken += 1
            response: AIMessage = await model_with_tools.ainvoke(messages)
            messages.append(response)

            tool_calls = getattr(response, "tool_calls", None) or []
            if on_progress and response.content:
                await on_progress(
                    f"Thinking: {str(response.content)[:100]}..."
                )

            if not tool_calls:
                # LLM returned no tool calls — loop terminates whether
                # or not we hit idle (upstream behavior; the warning
                # check is at the post-loop assertion below).
                break

            for tc in tool_calls:
                name = tc.get("name") if isinstance(tc, dict) else tc.name
                args = tc.get("args", {}) if isinstance(tc, dict) else tc.args
                tc_id = (
                    tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                )

                if on_progress:
                    await on_progress(f"Tool: {name}")

                if name not in tools_by_name:
                    result = PBLToolResult(
                        success=False,
                        error=f"Unknown tool {name!r}",
                    )
                else:
                    result = await tools_by_name[name].ainvoke(args)

                # Append tool result so the next LLM step sees what
                # happened (success / error / state-mutation message).
                messages.append(
                    ToolMessage(
                        content=json.dumps(result.model_dump()),
                        tool_call_id=tc_id or "",
                    )
                )

            # Stop condition: mode just got switched to idle.
            if mode_mcp.get_current_mode() == "idle":
                break
    except Exception as exc:  # noqa: BLE001 — record + return
        _logger.exception("PBL design loop failed")
        loop_error = f"design loop failed: {exc}"

    reached_idle = mode_mcp.get_current_mode() == "idle"
    if not reached_idle and on_progress:
        await on_progress(
            "Warning: Generation did not reach idle mode. Project may be incomplete."
        )

    if on_progress:
        await on_progress("Running post-processing...")

    welcome_generated = await _post_process(
        project_config, model, config.language_directive, on_progress
    )

    if on_progress:
        await on_progress("PBL project generation complete!")

    return GeneratePBLResult(
        project_config=project_config,
        steps_taken=steps_taken,
        reached_idle=reached_idle,
        welcome_message_generated=welcome_generated,
        error=loop_error,
    )


# ── Post-processing ───────────────────────────────────────────────────


async def _post_process(
    config: dict[str, Any],
    model: Any,
    language_directive: str,
    on_progress: Callable[[str], Awaitable[None]] | None,
) -> bool:
    """Activate the first issue + ask the Question agent to generate
    its welcome message. Returns True iff a welcome was generated."""
    issues = config["issueboard"]["issues"]
    if not issues:
        if on_progress:
            await on_progress("No issues created — skipping post-process.")
        return False

    sorted_issues = sorted(issues, key=lambda i: i.get("index", 0))
    first = sorted_issues[0]
    first["is_active"] = True
    config["issueboard"]["current_issue_id"] = first["id"]

    if on_progress:
        await on_progress(f"Activating first issue: {first['title']}")

    question_agent = next(
        (a for a in config["agents"] if a["name"] == first["question_agent_name"]),
        None,
    )
    if question_agent is None:
        if on_progress:
            await on_progress(
                "Warning: Question agent not found for first issue."
            )
        return False

    context = f"""## Issue Information

**Title**: {first["title"]}
**Description**: {first["description"]}
**Person in Charge**: {first["person_in_charge"]}
{f"**Participants**: {', '.join(first['participants'])}" if first['participants'] else ""}
{f"**Notes**: {first['notes']}" if first['notes'] else ""}

## Your Task

Generate a welcome message for the student working on this issue. The message should:
1. Start with a friendly greeting introducing yourself as the guiding assistant for this issue (use a natural, localized title — do NOT use the English term "Question Agent" directly in non-English contexts)
2. Present 1-3 specific, actionable guiding questions based on the issue information above, each question should:
   - Guide students toward key learning objectives
   - Be specific and actionable
   - Help break down the problem
   - Encourage critical thinking
3. End by encouraging the student to type `@question` anytime for help (keep the literal `@question` as-is since it triggers the agent system)

Format the questions as a numbered list."""

    try:
        if on_progress:
            await on_progress("Generating welcome message...")
        response = await model.ainvoke(
            [
                SystemMessage(content=question_agent["system_prompt"]),
                HumanMessage(content=context),
            ]
        )
        welcome_text = response.content if isinstance(response.content, str) else str(
            response.content
        )
    except Exception as exc:  # noqa: BLE001
        _logger.warning("PBL welcome-message generation failed: %s", exc)
        if on_progress:
            await on_progress(f"Warning: welcome generation failed: {exc}")
        return False

    first["generated_questions"] = welcome_text
    config["chat"]["messages"].append(
        {
            "id": f"msg_welcome_{uuid.uuid4().hex[:8]}",
            "agent_name": first["question_agent_name"],
            "message": welcome_text,
            "timestamp": time.time(),
            "read_by": [],
        }
    )
    if on_progress:
        await on_progress("Welcome message added to chat.")
    return True


# ── Tool factory ──────────────────────────────────────────────────────


def _build_tools(
    mode_mcp: ModeMCP,
    project_mcp: ProjectMCP,
    agent_mcp: AgentMCP,
    issueboard_mcp: IssueboardMCP,
) -> list[StructuredTool]:
    """Wrap the 4 MCPs into 16 LangChain StructuredTools. Each tool
    self-gates on `mode_mcp.get_current_mode()` so out-of-order calls
    return a structured error rather than mutating the wrong slice
    (matches upstream byte-for-byte; cf. generate-pbl.ts:88-282).
    """

    def _gate(required_mode: str, fn: Callable[..., PBLToolResult]):
        """Returns a wrapper that returns a mode-error if the current
        mode doesn't match, else delegates to fn."""

        def wrapped(**kwargs) -> PBLToolResult:
            if mode_mcp.get_current_mode() != required_mode:
                return PBLToolResult(
                    success=False,
                    error=f"Must be in {required_mode} mode.",
                )
            return fn(**kwargs)

        return wrapped

    return [
        # ── Mode ───────────────────────────────────────────────────
        StructuredTool.from_function(
            func=lambda mode: mode_mcp.set_mode(mode),
            name="set_mode",
            description=(
                "Switch the current working mode. Available modes: "
                "project_info, agent, issueboard, idle. Setting idle "
                "ends the design loop."
            ),
            args_schema=_SetModeArgs,
        ),
        # ── Project info (gated to project_info mode) ──────────────
        StructuredTool.from_function(
            func=_gate(
                "project_info",
                lambda: project_mcp.get_project_info(),
            ),
            name="get_project_info",
            description=(
                "Get current project title + description. Requires "
                "project_info mode."
            ),
            args_schema=BaseModel,
        ),
        StructuredTool.from_function(
            func=_gate("project_info", project_mcp.update_title),
            name="update_title",
            description="Update the project title. Requires project_info mode.",
            args_schema=_UpdateTitleArgs,
        ),
        StructuredTool.from_function(
            func=_gate("project_info", project_mcp.update_description),
            name="update_description",
            description=(
                "Update the project description. Requires project_info mode."
            ),
            args_schema=_UpdateDescriptionArgs,
        ),
        # ── Agent (gated to agent mode) ────────────────────────────
        StructuredTool.from_function(
            func=_gate("agent", lambda: agent_mcp.list_agents()),
            name="list_project_agents",
            description="List all agents on the project. Requires agent mode.",
            args_schema=BaseModel,
        ),
        StructuredTool.from_function(
            func=_gate("agent", agent_mcp.create_agent),
            name="create_agent",
            description=(
                "Create a new agent role for the project. Requires agent mode."
            ),
            args_schema=_CreateAgentArgs,
        ),
        StructuredTool.from_function(
            func=_gate("agent", agent_mcp.update_agent),
            name="update_agent",
            description="Update an agent's properties. Requires agent mode.",
            args_schema=_UpdateAgentArgs,
        ),
        StructuredTool.from_function(
            func=_gate(
                "agent",
                lambda name: agent_mcp.delete_agent(name),
            ),
            name="delete_agent",
            description="Delete an agent role. Requires agent mode.",
            args_schema=_DeleteAgentArgs,
        ),
        # ── Issueboard (gated to issueboard mode) ──────────────────
        StructuredTool.from_function(
            func=_gate("issueboard", lambda: issueboard_mcp.create_issueboard()),
            name="create_issueboard",
            description=(
                "Create or reset the issueboard. Requires issueboard mode."
            ),
            args_schema=BaseModel,
        ),
        StructuredTool.from_function(
            func=_gate("issueboard", lambda: issueboard_mcp.get_issueboard()),
            name="get_issueboard",
            description="Read the current issueboard. Requires issueboard mode.",
            args_schema=BaseModel,
        ),
        StructuredTool.from_function(
            func=_gate("issueboard", issueboard_mcp.update_issueboard_agents),
            name="update_issueboard_agents",
            description=(
                "Set agent_ids on the issueboard. Requires issueboard mode."
            ),
            args_schema=_UpdateIssueboardAgentsArgs,
        ),
        StructuredTool.from_function(
            func=_gate("issueboard", issueboard_mcp.create_issue),
            name="create_issue",
            description=(
                "Create a new issue. Auto-spawns Question and Judge "
                "agents per upstream pattern. Requires issueboard mode."
            ),
            args_schema=_CreateIssueArgs,
        ),
        StructuredTool.from_function(
            func=_gate("issueboard", lambda: issueboard_mcp.list_issues()),
            name="list_issues",
            description="List all issues. Requires issueboard mode.",
            args_schema=BaseModel,
        ),
        StructuredTool.from_function(
            func=_gate(
                "issueboard",
                lambda **kw: issueboard_mcp.update_issue(
                    parent_issue_set=("parent_issue" in kw), **kw
                ),
            ),
            name="update_issue",
            description="Update an issue. Requires issueboard mode.",
            args_schema=_UpdateIssueArgs,
        ),
        StructuredTool.from_function(
            func=_gate(
                "issueboard",
                lambda issue_id: issueboard_mcp.delete_issue(issue_id),
            ),
            name="delete_issue",
            description=(
                "Delete an issue and any sub-issues. Requires issueboard mode."
            ),
            args_schema=_DeleteIssueArgs,
        ),
        StructuredTool.from_function(
            func=_gate("issueboard", issueboard_mcp.reorder_issues),
            name="reorder_issues",
            description="Reorder issues. Requires issueboard mode.",
            args_schema=_ReorderIssuesArgs,
        ),
    ]


# Re-export for convenience
__all__ = [
    "GeneratePBLConfig",
    "GeneratePBLResult",
    "generate_pbl_project",
]
