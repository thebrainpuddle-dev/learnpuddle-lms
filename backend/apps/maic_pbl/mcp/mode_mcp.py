"""ModeMCP — current loop-state mutator for the PBL design phase.

Source: THU-MAIC/OpenMAIC lib/pbl/mcp/mode-mcp.ts (39 lines)
        Lifted under ADR-001a (full OpenMAIC license ownership).

The PBL design loop iterates between four modes — `project_info`,
`agent`, `issueboard`, `idle`. The LLM calls `set_mode(mode)` to
switch between them; the loop terminates when mode reaches `idle` or
the step counter hits 30 (whichever comes first).

This class is the single source of truth for the loop's state; it
also enforces the "no-op same-mode switch" guard from upstream so
the LLM doesn't burn steps re-entering the same mode.
"""
from __future__ import annotations

from apps.maic_pbl.types import PBLMode, PBLToolResult


class ModeMCP:
    """Owns the loop's current mode + the set of legal modes for
    this design session.

    Construct with the full set of legal modes + the starting mode
    (`project_info` per upstream's typical entry point). Mutations
    are guarded against unknown modes and same-mode no-ops.
    """

    def __init__(self, available_modes: list[PBLMode], default_mode: PBLMode):
        if default_mode not in available_modes:
            raise ValueError(
                f"default_mode {default_mode!r} not in available_modes "
                f"{available_modes!r}"
            )
        self._available_modes: list[PBLMode] = list(available_modes)
        self._current_mode: PBLMode = default_mode

    def set_mode(self, mode: PBLMode) -> PBLToolResult:
        """Switch to a new mode.

        Returns success=False with `error` when:
          - `mode` is not in the configured available_modes
          - `mode` is already the current mode (per upstream guard)
        """
        if mode not in self._available_modes:
            return PBLToolResult(
                success=False,
                error=(
                    f'Mode "{mode}" not available. '
                    f"Available: {', '.join(self._available_modes)}"
                ),
            )
        if mode == self._current_mode:
            return PBLToolResult(
                success=False,
                error=f'Already in "{mode}" mode.',
            )
        self._current_mode = mode
        return PBLToolResult(
            success=True,
            message=f'Switched to "{mode}" mode.',
        )

    def get_current_mode(self) -> PBLMode:
        """Return the currently-active loop mode."""
        return self._current_mode

    def get_available_modes(self) -> list[PBLMode]:
        """Return a copy of the legal-modes list (mutation-safe)."""
        return list(self._available_modes)
