"""PBL design-loop system prompt builder.

Source: THU-MAIC/OpenMAIC lib/pbl/pbl-system-prompt.ts (30 lines)
        Lifted under ADR-001a.

Thin adapter over `apps.maic.generation.prompt_loader.load_generation_prompt`
that fills in the 5 placeholders in `pbl-design/system.md`:
projectTopic, projectDescription, targetSkills, issueCount,
languageDirective.

Returns just the system string — the design loop's user prompt is a
fixed kickoff message ("Design a PBL project. Start in project_info
mode by setting the project title and description.") set at the
loop level, so we don't need a paired user.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from apps.maic.generation.prompt_loader import load_generation_prompt


@dataclass(frozen=True)
class PBLSystemPromptConfig:
    """Inputs the design-loop's system prompt template needs filled in.

    `project_topic` + `project_description` come from the API caller
    (POST /api/maic/v2/pbl/projects/). `target_skills` is a list of
    learning-outcome keywords; the loader joins it with ", " before
    interpolation. `issue_count` defaults to 3 (upstream's default;
    see generate-pbl.ts line 23). `language_directive` is the same
    multi-language string used elsewhere in the prompt library.
    """

    project_topic: str
    project_description: str
    target_skills: list[str] = field(default_factory=list)
    issue_count: int = 3
    language_directive: str = ""


def build_pbl_system_prompt(config: PBLSystemPromptConfig) -> str:
    """Render the pbl-design template with config interpolated.

    Raises:
        MaicConfigError: template directory or system.md is missing
            (load_generation_prompt's contract — see prompt_loader.py).
    """
    built = load_generation_prompt(
        "pbl-design",
        {
            "projectTopic": config.project_topic,
            "projectDescription": config.project_description,
            "targetSkills": ", ".join(config.target_skills),
            "issueCount": config.issue_count,
            "languageDirective": config.language_directive,
        },
    )
    return built.system
