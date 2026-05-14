"""Tests for the PBL design-phase agentic loop (MAIC-703).

Uses a deterministic fake LangChain chat model that emits a pre-
scripted sequence of tool calls — production-real path through the
loop, real Pydantic models, real MCP mutations. The only synthetic
boundary is the LLM itself; that's a legitimate IO boundary fake
per the no-mocks rule (CLAUDE.md, 2026-05-03).

The fake model is a drop-in for what `resolve_chat_model` returns —
exposes `bind_tools(tools)` returning self + `ainvoke(messages)`
returning a scripted AIMessage sequence.
"""
from __future__ import annotations

from typing import Any, Iterator

import pytest
from langchain_core.messages import AIMessage, BaseMessage

from apps.maic_pbl.design_graph import (
    GeneratePBLConfig,
    GeneratePBLResult,
    generate_pbl_project,
)


# ── Fake chat model ───────────────────────────────────────────────────


class _ScriptedChatModel:
    """Drop-in for a LangChain BaseChatModel. `script` is a list of
    AIMessages (or AIMessage-like dicts) the model returns in order;
    extra calls return an empty AIMessage to terminate the loop."""

    def __init__(self, script: list[Any]):
        self._script: Iterator[Any] = iter(script)
        self.calls: list[list[BaseMessage]] = []

    def bind_tools(self, _tools: list[Any]) -> "_ScriptedChatModel":
        # We don't need to introspect the tools; the script is keyed
        # to which tools we expect the LLM to call.
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        # Capture the messages the loop is sending so tests can
        # assert tool-result feedback flows correctly.
        self.calls.append(list(messages))
        try:
            return next(self._script)
        except StopIteration:
            # Loop's stop condition kicks in (or step limit) — return
            # an empty no-tool response to terminate naturally.
            return AIMessage(content="done", tool_calls=[])


def _ai_with_tool_calls(*tcs: dict) -> AIMessage:
    """Build an AIMessage with tool_calls in the dict shape LangChain
    consumers (and our loop) read."""
    return AIMessage(
        content="",
        tool_calls=[
            {
                "id": tc.get("id", f"tc-{i}"),
                "name": tc["name"],
                "args": tc.get("args", {}),
                "type": "tool_call",
            }
            for i, tc in enumerate(tcs)
        ],
    )


def _config() -> GeneratePBLConfig:
    return GeneratePBLConfig(
        project_topic="Numerator and Denominator",
        project_description="Build a CLI fraction calculator.",
        target_skills=["Python", "TDD"],
        issue_count=2,
        language_directive="",
    )


# ── Happy path: full design loop ──────────────────────────────────────


@pytest.mark.asyncio
async def test_design_loop_produces_complete_project_config():
    """Real production path: scripted LLM walks through 4 modes and
    creates 2 issues. All MCPs mutate real state; final config has
    title, description, agents (1 dev + 4 system from 2 issues),
    issueboard with 2 issues + an active first issue + a generated
    welcome message."""
    script = [
        # project_info phase
        _ai_with_tool_calls(
            {"name": "set_mode", "args": {"mode": "project_info"}, "id": "1"},
        ),
        _ai_with_tool_calls(
            {"name": "update_title", "args": {"title": "Fraction Calculator"}, "id": "2"},
        ),
        _ai_with_tool_calls(
            {
                "name": "update_description",
                "args": {"description": "Build a CLI fraction calculator."},
                "id": "3",
            },
        ),
        # agent phase
        _ai_with_tool_calls({"name": "set_mode", "args": {"mode": "agent"}, "id": "4"}),
        _ai_with_tool_calls(
            {
                "name": "create_agent",
                "args": {
                    "name": "Developer",
                    "system_prompt": "Build the calculator.",
                    "default_mode": "chat",
                    "actor_role": "Software Engineer",
                    "role_division": "development",
                },
                "id": "5",
            },
        ),
        # issueboard phase
        _ai_with_tool_calls(
            {"name": "set_mode", "args": {"mode": "issueboard"}, "id": "6"},
        ),
        _ai_with_tool_calls(
            {
                "name": "create_issue",
                "args": {
                    "title": "Define API",
                    "description": "Sketch endpoints.",
                    "person_in_charge": "Developer",
                    "index": 0,
                },
                "id": "7",
            },
        ),
        _ai_with_tool_calls(
            {
                "name": "create_issue",
                "args": {
                    "title": "Implement Add",
                    "description": "Add two fractions.",
                    "person_in_charge": "Developer",
                    "index": 1,
                },
                "id": "8",
            },
        ),
        # finish
        _ai_with_tool_calls({"name": "set_mode", "args": {"mode": "idle"}, "id": "9"}),
        # Post-process LLM call returns a welcome message
        AIMessage(content="Welcome! 1) What's your first endpoint? 2) How will you handle errors?"),
    ]
    model = _ScriptedChatModel(script)
    progress: list[str] = []

    async def collect(msg: str) -> None:
        progress.append(msg)

    result = await generate_pbl_project(_config(), model, on_progress=collect)

    assert isinstance(result, GeneratePBLResult)
    assert result.error is None
    assert result.reached_idle is True
    assert result.welcome_message_generated is True

    cfg = result.project_config
    assert cfg["projectInfo"]["title"] == "Fraction Calculator"
    assert cfg["projectInfo"]["description"] == "Build a CLI fraction calculator."

    # 1 developer + 2 issues × (Question + Judge) = 5 agents
    agents_by_name = {a["name"]: a for a in cfg["agents"]}
    agent_names = set(agents_by_name)
    assert "Developer" in agent_names
    assert "Question Agent - issue_1" in agent_names
    assert "Judge Agent - issue_1" in agent_names
    assert "Question Agent - issue_2" in agent_names
    assert "Judge Agent - issue_2" in agent_names
    assert len(cfg["agents"]) == 5
    assert agents_by_name["Developer"]["is_user_role"] is True
    assert agents_by_name["Developer"]["is_system_agent"] is False
    assert agents_by_name["Question Agent - issue_1"]["is_user_role"] is False
    assert agents_by_name["Question Agent - issue_1"]["is_system_agent"] is True
    assert agents_by_name["Judge Agent - issue_1"]["is_user_role"] is False
    assert agents_by_name["Judge Agent - issue_1"]["is_system_agent"] is True

    assert len(cfg["issueboard"]["issues"]) == 2
    # First issue is active + has the generated welcome
    assert cfg["issueboard"]["issues"][0]["is_active"] is True
    assert cfg["issueboard"]["current_issue_id"] == "issue_1"
    assert "Welcome!" in cfg["issueboard"]["issues"][0]["generated_questions"]

    # Welcome message landed in chat
    assert len(cfg["chat"]["messages"]) == 1
    welcome = cfg["chat"]["messages"][0]
    assert welcome["agent_name"] == "Question Agent - issue_1"
    assert "Welcome!" in welcome["message"]

    # Progress callback fired meaningfully
    assert any("Starting" in p for p in progress)
    assert any("Activating first issue" in p for p in progress)
    assert any("complete" in p for p in progress)


# ── Mode gating ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tools_self_gate_on_mode():
    """Calling update_title from the agent mode returns a structured
    error from the gate wrapper — NOT a state mutation. Tests the
    upstream-parity safety check that prevents the LLM from going
    sideways."""
    script = [
        # Try to update title without entering project_info mode
        # (default mode is project_info, but we'll switch to agent first)
        _ai_with_tool_calls({"name": "set_mode", "args": {"mode": "agent"}, "id": "1"}),
        # Now wrong-mode call
        _ai_with_tool_calls(
            {"name": "update_title", "args": {"title": "should not apply"}, "id": "2"},
        ),
        _ai_with_tool_calls({"name": "set_mode", "args": {"mode": "idle"}, "id": "3"}),
        AIMessage(content="placeholder"),  # post-process call (no issues, will return early)
    ]
    model = _ScriptedChatModel(script)
    result = await generate_pbl_project(_config(), model)

    # Mode gate refused the title update
    assert result.project_config["projectInfo"]["title"] == ""
    assert result.reached_idle is True


# ── Step limit ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_loop_terminates_at_step_limit_without_idle():
    """If the LLM goes infinite without ever calling set_mode('idle'),
    the loop hits the 30-step ceiling and exits. reached_idle=False
    is the user-facing flag."""
    # 31 tool-calling responses; loop should stop at 30
    script = [
        _ai_with_tool_calls(
            {"name": "set_mode", "args": {"mode": "agent"}, "id": str(i)},
        )
        if i == 0
        else
        # Subsequent calls — alternate between modes that never reach idle
        _ai_with_tool_calls(
            {
                "name": "set_mode",
                "args": {"mode": "project_info" if i % 2 else "agent"},
                "id": str(i),
            },
        )
        for i in range(35)
    ]
    model = _ScriptedChatModel(script)
    result = await generate_pbl_project(_config(), model)

    assert result.reached_idle is False
    assert result.steps_taken == 30  # _MAX_STEPS upper bound


# ── No-tool-calls termination ────────────────────────────────────────


@pytest.mark.asyncio
async def test_loop_terminates_when_llm_returns_no_tool_calls():
    """LLM may decide it's done without calling set_mode('idle') —
    we still terminate and return whatever state we have."""
    script = [
        _ai_with_tool_calls(
            {"name": "update_title", "args": {"title": "Half-done"}, "id": "1"},
        ),
        AIMessage(content="I'm finished.", tool_calls=[]),  # natural termination
    ]
    model = _ScriptedChatModel(script)
    result = await generate_pbl_project(_config(), model)

    assert result.steps_taken == 2
    assert result.reached_idle is False  # never called set_mode('idle')
    assert result.project_config["projectInfo"]["title"] == "Half-done"


# ── Empty issues → post-process skips welcome ────────────────────────


@pytest.mark.asyncio
async def test_post_process_skipped_when_no_issues_created():
    """If the design loop never created an issue, post-processing
    can't generate a welcome — gracefully skip without erroring."""
    script = [
        _ai_with_tool_calls(
            {"name": "update_title", "args": {"title": "Bare"}, "id": "1"},
        ),
        _ai_with_tool_calls({"name": "set_mode", "args": {"mode": "idle"}, "id": "2"}),
        # No post-process call follows because issues is empty
    ]
    model = _ScriptedChatModel(script)
    result = await generate_pbl_project(_config(), model)

    assert result.welcome_message_generated is False
    assert result.project_config["chat"]["messages"] == []


# ── Loop error path ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_loop_records_error_when_model_raises():
    """If the model raises, the error is recorded but the function
    still returns whatever partial state was reached. Caller decides
    whether to persist the partial config."""

    class _RaisingModel:
        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, _messages):
            raise RuntimeError("simulated 5xx")

    result = await generate_pbl_project(_config(), _RaisingModel())
    assert result.error is not None
    assert "design loop failed" in result.error
    assert result.reached_idle is False
    # State stayed at the empty default
    assert result.project_config["projectInfo"]["title"] == ""


# ── language_directive flows through to system prompt + Q+J prompts ──


@pytest.mark.asyncio
async def test_language_directive_propagates_to_system_prompt():
    """The system prompt builder interpolates language_directive; we
    don't re-test build_pbl_system_prompt here (covered in tests_types
    + the prompt_loader infra) — instead assert the FIRST message the
    LLM sees has the directive embedded."""
    script = [_ai_with_tool_calls({"name": "set_mode", "args": {"mode": "idle"}, "id": "1"})]
    model = _ScriptedChatModel(script)
    cfg = GeneratePBLConfig(
        project_topic="x",
        project_description="x",
        target_skills=[],
        issue_count=1,
        language_directive="MUST_TEST_DIRECTIVE",
    )
    await generate_pbl_project(cfg, model)
    # First call: messages[0] is the SystemMessage built from pbl-design template
    first_call = model.calls[0]
    assert first_call[0].__class__.__name__ == "SystemMessage"
    assert "MUST_TEST_DIRECTIVE" in first_call[0].content


@pytest.mark.asyncio
async def test_teacher_context_propagates_to_system_prompt():
    script = [_ai_with_tool_calls({"name": "set_mode", "args": {"mode": "idle"}, "id": "1"})]
    model = _ScriptedChatModel(script)
    cfg = GeneratePBLConfig(
        project_topic="x",
        project_description="x",
        target_skills=[],
        issue_count=1,
        teacher_context="Grade 6 guide: roles, evidence log, success criteria.",
    )

    await generate_pbl_project(cfg, model)

    first_call = model.calls[0]
    assert "Private Teacher Planning Context" in first_call[0].content
    assert "Grade 6 guide" in first_call[0].content
    assert "success criteria" in first_call[0].content


# ── Tool-result feedback loop ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_issue_via_tool_does_not_clobber_parent_issue():
    """Regression test for the LangChain-StructuredTool /
    Pydantic-default interaction: when the LLM calls update_issue
    with title only, parent_issue must NOT be silently cleared.
    set_issue_parent is the dedicated tool for FK changes (see
    issueboard_mcp.py docstring on update_issue)."""
    script = [
        # Create parent + child via direct MCP-tool calls
        _ai_with_tool_calls({"name": "set_mode", "args": {"mode": "issueboard"}, "id": "1"}),
        _ai_with_tool_calls(
            {
                "name": "create_issue",
                "args": {"title": "Parent", "description": "p", "person_in_charge": "dev"},
                "id": "2",
            }
        ),
        _ai_with_tool_calls(
            {
                "name": "create_issue",
                "args": {
                    "title": "Child",
                    "description": "c",
                    "person_in_charge": "dev",
                    "parent_issue": "issue_1",
                },
                "id": "3",
            }
        ),
        # NOW the failing case: LLM patches title only via update_issue
        _ai_with_tool_calls(
            {
                "name": "update_issue",
                "args": {"issue_id": "issue_2", "title": "Renamed Child"},
                "id": "4",
            }
        ),
        _ai_with_tool_calls({"name": "set_mode", "args": {"mode": "idle"}, "id": "5"}),
        AIMessage(content="welcome"),
    ]
    model = _ScriptedChatModel(script)
    result = await generate_pbl_project(_config(), model)

    issues = result.project_config["issueboard"]["issues"]
    child = next(i for i in issues if i["id"] == "issue_2")
    assert child["title"] == "Renamed Child"
    # The load-bearing assertion: parent_issue NOT silently cleared
    assert child["parent_issue"] == "issue_1"


@pytest.mark.asyncio
async def test_tool_exception_surfaces_as_tool_message_not_loop_kill():
    """Regression test: if a single tool raises, the loop must NOT
    abort. The LLM gets a ToolMessage with the error and can adapt
    on the next step."""
    # Force a tool exception by passing args that fail Pydantic validation
    # at the StructuredTool layer (StructuredTool.ainvoke handles this
    # by raising — we verify the loop catches it).
    script = [
        # Try to call update_title with no args (missing required `title`)
        _ai_with_tool_calls({"name": "update_title", "args": {}, "id": "1"}),
        # Loop should continue and the LLM can call set_mode('idle')
        _ai_with_tool_calls({"name": "set_mode", "args": {"mode": "idle"}, "id": "2"}),
    ]
    model = _ScriptedChatModel(script)
    result = await generate_pbl_project(_config(), model)

    # The loop continued past the failing tool call → reached_idle
    assert result.reached_idle is True
    # And no loop-killing error was recorded
    assert result.error is None or "schema validation" in result.error


@pytest.mark.asyncio
async def test_tool_results_appended_as_tool_messages():
    """After each tool call, a ToolMessage is appended to the
    conversation so the next LLM step sees what happened. This is
    the load-bearing invariant for multi-step tool-calling."""
    script = [
        _ai_with_tool_calls(
            {"name": "update_title", "args": {"title": "X"}, "id": "tc1"},
        ),
        _ai_with_tool_calls({"name": "set_mode", "args": {"mode": "idle"}, "id": "tc2"}),
    ]
    model = _ScriptedChatModel(script)
    await generate_pbl_project(_config(), model)

    # Second call's messages should include the AIMessage from first
    # call + the ToolMessage with result for tc1
    second_call = model.calls[1]
    types_in_order = [m.__class__.__name__ for m in second_call]
    assert types_in_order[-2] == "AIMessage"
    assert types_in_order[-1] == "ToolMessage"
    assert second_call[-1].tool_call_id == "tc1"
