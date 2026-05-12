"""AgentMCP — agents-list mutator (Question, Judge, dev roles).

Source: THU-MAIC/OpenMAIC lib/pbl/mcp/agent-mcp.ts (132 lines)
        Lifted under ADR-001a.

Owns config["agents"] on the shared PBLProjectConfig dict. The design
loop calls these tools during the `agent` mode (set by ModeMCP) to
populate the project's roster — typically 2-4 development agents
(picked by the LLM based on the project topic) plus the auto-spawned
Question and Judge system agents.

API surface mirrors upstream byte-for-byte:
  list_agents              — read all
  get_agent_info(name)     — read one
  create_agent(...)        — append (rejects duplicate names)
  update_agent(...)        — patch one (rejects rename collisions)
  delete_agent(name)       — remove

Name uniqueness is enforced — the chat protocol uses `@<name>` to
route messages, and a duplicate would create routing ambiguity.
"""
from __future__ import annotations

from typing import Any

from apps.maic_pbl.types import PBLToolResult, ROLE_DIVISION_DEVELOPMENT


def _is_selectable_user_role(role_division: str, is_system_agent: bool) -> bool:
    return role_division == ROLE_DIVISION_DEVELOPMENT and not is_system_agent


class AgentMCP:
    """Owns config['agents'] on the shared dict."""

    def __init__(self, config: dict[str, Any]):
        config.setdefault("agents", [])
        self._config = config

    def list_agents(self) -> PBLToolResult:
        """Return all agents (deep-copied so mutation by the caller
        doesn't poison our state)."""
        agents = self._config["agents"]
        return PBLToolResult(
            success=True,
            agents=[dict(a) for a in agents],
            message="No agents found." if not agents else None,
        )

    def get_agent_info(self, name: str) -> PBLToolResult:
        """Read one agent by name."""
        for a in self._config["agents"]:
            if a["name"] == name:
                return PBLToolResult(success=True, agent=dict(a))
        return PBLToolResult(success=False, error=f'Agent "{name}" not found.')

    def create_agent(
        self,
        *,
        name: str,
        system_prompt: str,
        default_mode: str,
        delay_time: float = 0,
        actor_role: str | None = "",
        role_division: str | None = ROLE_DIVISION_DEVELOPMENT,
        is_system_agent: bool = False,
    ) -> PBLToolResult:
        """Append a new agent. Rejects:
        - empty name
        - empty system_prompt
        - duplicate name
        """
        if not name or not name.strip():
            return PBLToolResult(success=False, error="Agent name cannot be empty.")
        if not system_prompt or not system_prompt.strip():
            return PBLToolResult(
                success=False,
                error="System prompt cannot be empty.",
            )
        if any(a["name"] == name for a in self._config["agents"]):
            return PBLToolResult(
                success=False,
                error=f'Agent "{name}" already exists.',
            )

        resolved_role_division = (
            role_division if role_division is not None else ROLE_DIVISION_DEVELOPMENT
        )
        resolved_actor_role = actor_role if actor_role is not None else ""
        is_user_role = _is_selectable_user_role(
            resolved_role_division,
            is_system_agent,
        )

        new_agent: dict[str, Any] = {
            "name": name,
            "actor_role": resolved_actor_role,
            "role_division": resolved_role_division,
            "system_prompt": system_prompt,
            "default_mode": default_mode,
            "delay_time": delay_time,
            "env": {
                # Upstream wires per-agent chat env here; we mirror the
                # shape verbatim. The chat consumer (MAIC-704) reads
                # env.chat.system_prompt as the per-message prompt.
                "chat": {
                    "max_tokens": 4096,
                    "system_prompt": system_prompt,
                },
            },
            "is_user_role": is_user_role,
            "is_active": False,
            "is_system_agent": is_system_agent,
        }
        self._config["agents"].append(new_agent)
        return PBLToolResult(
            success=True,
            message=f'Agent "{name}" created successfully.',
        )

    def update_agent(
        self,
        *,
        name: str,
        new_name: str | None = None,
        system_prompt: str | None = None,
        default_mode: str | None = None,
        delay_time: float | None = None,
        actor_role: str | None = None,
        role_division: str | None = None,
    ) -> PBLToolResult:
        """Patch an agent by name. Optional fields stay unchanged when
        omitted. Rejects rename to an already-taken name."""
        agent = next(
            (a for a in self._config["agents"] if a["name"] == name),
            None,
        )
        if agent is None:
            return PBLToolResult(success=False, error=f'Agent "{name}" not found.')

        # Rename collision check
        if (
            new_name is not None
            and new_name != name
            and any(a["name"] == new_name for a in self._config["agents"])
        ):
            return PBLToolResult(
                success=False,
                error=f'Agent "{new_name}" already exists.',
            )

        if new_name is not None:
            agent["name"] = new_name
        if system_prompt is not None:
            agent["system_prompt"] = system_prompt
            chat_env = agent.get("env", {}).get("chat")
            if isinstance(chat_env, dict):
                chat_env["system_prompt"] = system_prompt
        if default_mode is not None:
            agent["default_mode"] = default_mode
        if delay_time is not None:
            agent["delay_time"] = delay_time
        if actor_role is not None:
            agent["actor_role"] = actor_role
        if role_division is not None:
            agent["role_division"] = role_division
            agent["is_user_role"] = _is_selectable_user_role(
                role_division,
                agent.get("is_system_agent", False),
            )

        return PBLToolResult(success=True, message="Agent updated successfully.")

    def delete_agent(self, name: str) -> PBLToolResult:
        """Remove an agent by name."""
        agents = self._config["agents"]
        for i, a in enumerate(agents):
            if a["name"] == name:
                agents.pop(i)
                return PBLToolResult(
                    success=True,
                    message="Agent deleted successfully.",
                )
        return PBLToolResult(success=False, error=f'Agent "{name}" not found.')
