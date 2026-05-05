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
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from apps.maic_pbl.mcp import (
    AgentMCP,
    IssueboardMCP,
    ModeMCP,
    ProjectMCP,
)
from apps.maic_pbl.system_prompt import (
    PBLSystemPromptConfig,
    build_pbl_system_prompt,
)
from apps.maic_pbl.types import (
    MODE_AGENT,
    MODE_IDLE,
    MODE_ISSUEBOARD,
    MODE_PROJECT_INFO,
    PBLProjectConfig,
    PBLToolResult,
)

_logger = logging.getLogger(__name__)


_MAX_STEPS: int = 30  # upstream: stepCountIs(30)

_LOOP_KICKOFF_USER_PROMPT: str = (
    "Design a PBL project. Start in project_info mode by setting the "
    "project title and description."
)


# ── Tool argument schemas ─────────────────────────────────────────────


class _NoArgs(BaseModel):
    """Shared empty-args schema for the 5 zero-input tools.
    Single class avoids the title-collision risk that bare BaseModel
    triggers in some LangChain/provider serializers."""

    model_config = ConfigDict(extra="forbid")


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
    """No parent_issue here — see set_issue_parent for FK changes.
    update_issue can't safely accept parent_issue because the
    LangChain StructuredTool layer can't tell the LLM "I omitted
    this field" from "I set this field to null" (Pydantic's
    model_dump fills defaults). update_issue would always silently
    clear the parent."""

    issue_id: str
    title: str | None = None
    description: str | None = None
    person_in_charge: str | None = None
    participants: list[str] | None = None
    notes: str | None = None
    index: int | None = None


class _SetIssueParentArgs(BaseModel):
    issue_id: str = Field(..., description="The issue to mutate.")
    parent_issue: str | None = Field(
        ...,
        description=(
            "ID of the parent issue (sub-issue relation), OR null to "
            "clear. Required field — pass null explicitly to clear."
        ),
    )


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
    """Output of generate_pbl_project."""

    project_config: dict[str, Any]
    steps_taken: int
    reached_idle: bool
    welcome_message_generated: bool
    error: str | None = None
    schema_valid: bool = False


async def generate_pbl_project(
    config: GeneratePBLConfig,
    model: Any,
    *,
    on_progress: Callable[[str], Awaitable[None]] | None = None,
) -> GeneratePBLResult:
    """Run the design-phase agentic loop and post-processing."""
    project_config: dict[str, Any] = {
        "projectInfo": {"title": "", "description": ""},
        "agents": [],
        "issueboard": {"agent_ids": [], "issues": [], "current_issue_id": None},
        "chat": {"messages": []},
    }

    mode_mcp = ModeMCP(
        [MODE_PROJECT_INFO, MODE_AGENT, MODE_ISSUEBOARD, MODE_IDLE],
        MODE_PROJECT_INFO,
    )
    project_mcp = ProjectMCP(project_config)
    agent_mcp = AgentMCP(project_config)
    issueboard_mcp = IssueboardMCP(
        project_config, agent_mcp, config.language_directive,
    )

    if on_progress:
        await on_progress("Starting PBL project generation...")

    tools = _build_tools(mode_mcp, project_mcp, agent_mcp, issueboard_mcp)
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

    for step in range(_MAX_STEPS):
        steps_taken += 1
        try:
            response: AIMessage = await model_with_tools.ainvoke(messages)
        except Exception as exc:  # noqa: BLE001 — model call IS an IO boundary
            _logger.exception("PBL design loop: model.ainvoke failed at step %d", step)
            loop_error = f"design loop failed at step {step}: {exc}"
            break

        messages.append(response)

        tool_calls = getattr(response, "tool_calls", None) or []
        if on_progress and response.content:
            await on_progress(f"Thinking: {str(response.content)[:100]}...")

        if not tool_calls:
            break

        for i, tc in enumerate(tool_calls):
            name = tc.get("name") if isinstance(tc, dict) else tc.name
            args = tc.get("args", {}) if isinstance(tc, dict) else tc.args
            tc_id = (
                tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
            ) or f"tc_{steps_taken}_{i}"

            if on_progress:
                await on_progress(f"Tool: {name}")

            try:
                if name not in tools_by_name:
                    result = PBLToolResult(success=False, error=f"Unknown tool {name!r}")
                else:
                    result = await tools_by_name[name].ainvoke(args)
            except Exception as exc:  # noqa: BLE001 — surface to LLM, don't kill loop
                _logger.warning(
                    "PBL tool %r raised at step %d: %s", name, step, exc,
                )
                result = PBLToolResult(
                    success=False,
                    error=f"Tool {name!r} raised: {exc}",
                )

            messages.append(
                ToolMessage(
                    content=json.dumps(result.model_dump()),
                    tool_call_id=tc_id,
                )
            )

        if mode_mcp.get_current_mode() == MODE_IDLE:
            break

    reached_idle = mode_mcp.get_current_mode() == MODE_IDLE
    if not reached_idle and on_progress:
        await on_progress(
            "Warning: Generation did not reach idle mode. Project may be incomplete."
        )

    if on_progress:
        await on_progress("Running post-processing...")

    welcome_generated = await _post_process(
        project_config, model, config.language_directive, on_progress
    )

    schema_valid = False
    try:
        PBLProjectConfig.model_validate(project_config)
        schema_valid = True
    except ValidationError as exc:
        _logger.warning("PBL final config failed schema validation: %s", exc)
        if loop_error is None:
            loop_error = f"output failed schema validation: {exc.errors()[:2]}"

    if on_progress:
        await on_progress("PBL project generation complete!")

    return GeneratePBLResult(
        project_config=project_config,
        steps_taken=steps_taken,
        reached_idle=reached_idle,
        welcome_message_generated=welcome_generated,
        error=loop_error,
        schema_valid=schema_valid,
    )


# ── Post-processing ───────────────────────────────────────────────────


async def _post_process(
    config: dict[str, Any],
    model: Any,
    language_directive: str,
    on_progress: Callable[[str], Awaitable[None]] | None,
) -> bool:
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
    except Exception as exc:  # noqa: BLE001 — model call is an IO boundary
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
    """Wrap the 4 MCPs into 17 LangChain StructuredTools (16 from
    upstream + set_issue_parent split-out per ADR-002a fix).

    Each tool self-gates on `mode_mcp.get_current_mode()` so out-of-
    order calls return a structured error rather than mutating the
    wrong slice. Tool functions are named module-level closures (not
    lambdas) so LangSmith spans + retry logs surface real names.
    """

    def _gate(required_mode: str, fn: Callable[..., PBLToolResult]):
        """Returns a wrapper that returns a mode-error if the current
        mode doesn't match, else delegates to fn. Sync only — if a
        future MCP method is async, this wrapper needs an async twin
        (assert at registration time below)."""
        import inspect

        if inspect.iscoroutinefunction(fn):
            raise TypeError(
                f"_gate({required_mode!r}, ...) given async fn {fn!r}; "
                "wrapper is sync — add an async twin if needed."
            )

        def wrapped(**kwargs) -> PBLToolResult:
            if mode_mcp.get_current_mode() != required_mode:
                return PBLToolResult(
                    success=False,
                    error=f"Must be in {required_mode} mode.",
                )
            return fn(**kwargs)

        wrapped.__name__ = f"_gated_{required_mode}_{getattr(fn, '__name__', 'fn')}"
        return wrapped

    # Named impl functions (not lambdas) so tracing labels are useful.
    def _set_mode_impl(mode: str) -> PBLToolResult:
        return mode_mcp.set_mode(mode)  # type: ignore[arg-type]

    def _get_project_info_impl() -> PBLToolResult:
        return project_mcp.get_project_info()

    def _list_agents_impl() -> PBLToolResult:
        return agent_mcp.list_agents()

    def _delete_agent_impl(name: str) -> PBLToolResult:
        return agent_mcp.delete_agent(name)

    def _create_issueboard_impl() -> PBLToolResult:
        return issueboard_mcp.create_issueboard()

    def _get_issueboard_impl() -> PBLToolResult:
        return issueboard_mcp.get_issueboard()

    def _list_issues_impl() -> PBLToolResult:
        return issueboard_mcp.list_issues()

    def _delete_issue_impl(issue_id: str) -> PBLToolResult:
        return issueboard_mcp.delete_issue(issue_id)

    # Table-driven registration. Each row: (name, gated_mode-or-None,
    # impl, args_schema, description).
    table: list[tuple[str, str | None, Callable[..., PBLToolResult], type[BaseModel], str]] = [
        ("set_mode", None, _set_mode_impl, _SetModeArgs,
         "Switch the current working mode. Available: project_info, "
         "agent, issueboard, idle. Setting idle ends the design loop."),
        ("get_project_info", MODE_PROJECT_INFO, _get_project_info_impl, _NoArgs,
         "Get current project title + description. Requires project_info mode."),
        ("update_title", MODE_PROJECT_INFO, project_mcp.update_title, _UpdateTitleArgs,
         "Update the project title. Requires project_info mode."),
        ("update_description", MODE_PROJECT_INFO, project_mcp.update_description, _UpdateDescriptionArgs,
         "Update the project description. Requires project_info mode."),
        ("list_project_agents", MODE_AGENT, _list_agents_impl, _NoArgs,
         "List all agents on the project. Requires agent mode."),
        ("create_agent", MODE_AGENT, agent_mcp.create_agent, _CreateAgentArgs,
         "Create a new agent role for the project. Requires agent mode."),
        ("update_agent", MODE_AGENT, agent_mcp.update_agent, _UpdateAgentArgs,
         "Update an agent's properties. Requires agent mode."),
        ("delete_agent", MODE_AGENT, _delete_agent_impl, _DeleteAgentArgs,
         "Delete an agent role. Requires agent mode."),
        ("create_issueboard", MODE_ISSUEBOARD, _create_issueboard_impl, _NoArgs,
         "Create or reset the issueboard. Requires issueboard mode."),
        ("get_issueboard", MODE_ISSUEBOARD, _get_issueboard_impl, _NoArgs,
         "Read the current issueboard. Requires issueboard mode."),
        ("update_issueboard_agents", MODE_ISSUEBOARD,
         issueboard_mcp.update_issueboard_agents, _UpdateIssueboardAgentsArgs,
         "Set agent_ids on the issueboard. Requires issueboard mode."),
        ("create_issue", MODE_ISSUEBOARD, issueboard_mcp.create_issue, _CreateIssueArgs,
         "Create a new issue. Auto-spawns Question and Judge agents "
         "per upstream pattern. Requires issueboard mode."),
        ("list_issues", MODE_ISSUEBOARD, _list_issues_impl, _NoArgs,
         "List all issues. Requires issueboard mode."),
        ("update_issue", MODE_ISSUEBOARD, issueboard_mcp.update_issue, _UpdateIssueArgs,
         "Update an issue's fields (NOT parent_issue — use "
         "set_issue_parent for that). Requires issueboard mode."),
        ("set_issue_parent", MODE_ISSUEBOARD, issueboard_mcp.set_issue_parent, _SetIssueParentArgs,
         "Set or clear an issue's parent_issue FK. Pass null to clear, "
         "string to set. Requires issueboard mode."),
        ("delete_issue", MODE_ISSUEBOARD, _delete_issue_impl, _DeleteIssueArgs,
         "Delete an issue and any sub-issues. Requires issueboard mode."),
        ("reorder_issues", MODE_ISSUEBOARD, issueboard_mcp.reorder_issues, _ReorderIssuesArgs,
         "Reorder issues. Requires issueboard mode."),
    ]

    return [
        StructuredTool.from_function(
            func=(impl if mode is None else _gate(mode, impl)),
            name=name,
            description=desc,
            args_schema=schema,
        )
        for name, mode, impl, schema, desc in table
    ]


__all__ = [
    "GeneratePBLConfig",
    "GeneratePBLResult",
    "generate_pbl_project",
]
